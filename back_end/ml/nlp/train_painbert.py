"""Fine-tune PainBERT: a multi-label pain-descriptor tagger for patient notes.

Backbone: BAAI/bge-small-en-v1.5 (33M-parameter BERT encoder), mean-pooled,
with a 21-way sigmoid head trained with binary cross-entropy. Per-label
decision thresholds are tuned on a validation split, then the model is
exported to ONNX so the API can run it with onnxruntime (no PyTorch needed).

Evaluation uses data the model never trained on:
  * a test set written by a *different* LLM (Qwen) than the training set
    (GPT-OSS), and
  * a hand-written challenge set of negations, slang and metaphors.
Both are compared against a keyword lexicon and a TF-IDF + logistic
regression baseline.

Usage:  python -m ml.nlp.train_painbert
"""

import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.multiclass import OneVsRestClassifier
from torch import nn
from transformers import AutoModel, AutoTokenizer

from .labels import LABEL_BY_KEY, LABEL_KEYS

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "nlp"
ARTIFACTS = ROOT / "artifacts" / "painbert"
BACKBONE = "BAAI/bge-small-en-v1.5"
MAX_LEN = 128
SEED = 13
TEST_VERSION = "v2"

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
DEVICE = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"


# Keyword baseline built mechanically from the label definitions in
# labels.py (each content word, prefix-matched), so it never sees test data.
_STOP = {"pain", "that", "the", "or", "and", "a", "an", "to", "of", "with", "by", "at", "in", "on", "feels",
         "like", "sensation", "another", "area", "patient", "especially", "site", "from", "is", "it", "be",
         "began", "worse", "new", "control", "problems", "up", "down", "self", "care", "because", "trouble",
         "staying", "falling", "stops", "limits", "type", "the"}


def _lexicon() -> dict[str, str]:
    lexicon = {}
    for key in LABEL_KEYS:
        words = {w for w in re.findall(r"[a-z]+", LABEL_BY_KEY[key].definition.lower()) if w not in _STOP and len(w) > 2}
        lexicon[key] = r"\b(" + "|".join(sorted(w[:5] for w in words)) + ")"
    return lexicon


LEXICON = _lexicon()


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:  # a line still being written by the generator
            continue
        labels = row.get("labels", row.get("positives", []))
        rows.append({"text": row["text"], "labels": [k for k in labels if k in LABEL_KEYS]})
    return rows


def to_matrix(rows: list[dict]) -> np.ndarray:
    y = np.zeros((len(rows), len(LABEL_KEYS)), dtype=np.float32)
    for i, row in enumerate(rows):
        for key in row["labels"]:
            y[i, LABEL_KEYS.index(key)] = 1
    return y


class PainBERT(nn.Module):
    def __init__(self, backbone: str, n_labels: int):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(backbone)
        hidden = self.encoder.config.hidden_size
        self.dropout = nn.Dropout(0.1)
        self.head = nn.Linear(hidden, n_labels)

    def forward(self, input_ids, attention_mask):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
        mask = attention_mask.unsqueeze(-1).to(out.dtype)
        pooled = (out * mask).sum(1) / mask.sum(1).clamp(min=1e-6)
        return self.head(self.dropout(pooled))


def predict_proba(model, tokenizer, texts: list[str], batch: int = 64) -> np.ndarray:
    model.eval()
    outputs = []
    with torch.no_grad():
        for start in range(0, len(texts), batch):
            enc = tokenizer(texts[start:start + batch], padding=True, truncation=True, max_length=MAX_LEN, return_tensors="pt").to(DEVICE)
            outputs.append(torch.sigmoid(model(enc["input_ids"], enc["attention_mask"])).cpu().numpy())
    return np.concatenate(outputs)


def tune_thresholds(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    # Validation notes come from the training generators, where the model is
    # over-confident; a narrow range keeps thresholds from over-fitting them.
    grid = np.linspace(0.3, 0.6, 13)
    best = []
    for j in range(y.shape[1]):
        scores = [f1_score(y[:, j], p[:, j] >= t, zero_division=0) for t in grid]
        best.append(float(grid[int(np.argmax(scores))]))
    return np.array(best)


def evaluate(y: np.ndarray, pred: np.ndarray) -> dict:
    per_label = {}
    for j, key in enumerate(LABEL_KEYS):
        per_label[key] = {
            "precision": float(precision_score(y[:, j], pred[:, j], zero_division=0)),
            "recall": float(recall_score(y[:, j], pred[:, j], zero_division=0)),
            "f1": float(f1_score(y[:, j], pred[:, j], zero_division=0)),
            "support": int(y[:, j].sum()),
        }
    return {
        "micro_f1": float(f1_score(y, pred, average="micro", zero_division=0)),
        "macro_f1": float(f1_score(y, pred, average="macro", zero_division=0)),
        "exact_match": float((y == pred).all(axis=1).mean()),
        "per_label": per_label,
    }


def lexicon_predict(texts: list[str]) -> np.ndarray:
    pred = np.zeros((len(texts), len(LABEL_KEYS)), dtype=np.float32)
    for i, text in enumerate(texts):
        lower = text.lower()
        for j, key in enumerate(LABEL_KEYS):
            if re.search(LEXICON[key], lower):
                pred[i, j] = 1
    return pred


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    rows = [row for path in sorted(DATA.glob("train_generated*.jsonl")) for row in load_jsonl(path)]
    seen, unique = set(), []
    for row in rows:
        key = row["text"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(row)
    random.shuffle(unique)
    n_valid = max(300, len(unique) // 10)
    valid, train = unique[:n_valid], unique[n_valid:]
    test = [row for path in sorted(DATA.glob(f"test_generated_{TEST_VERSION}_*.jsonl")) for row in load_jsonl(path)]
    challenge = load_jsonl(Path(__file__).with_name("challenge_set.jsonl"))
    print(f"train={len(train)} valid={len(valid)} test={len(test)} challenge={len(challenge)} device={DEVICE}", flush=True)

    ytr, yva, yte, ych = map(to_matrix, (train, valid, test, challenge))
    texts = lambda rs: [r["text"] for r in rs]  # noqa: E731

    tokenizer = AutoTokenizer.from_pretrained(BACKBONE)
    model = PainBERT(BACKBONE, len(LABEL_KEYS)).to(DEVICE)

    # Rare labels get a larger positive weight so the loss does not ignore them.
    pos = ytr.sum(0)
    pos_weight = torch.tensor(np.clip((len(ytr) - pos) / np.maximum(pos, 1), 1, 12) ** 0.5, device=DEVICE)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    epochs, batch_size = 6, 32
    optimizer = torch.optim.AdamW([
        {"params": model.encoder.parameters(), "lr": 4e-5},
        {"params": model.head.parameters(), "lr": 1e-3},
    ], weight_decay=0.01)
    steps = epochs * ((len(train) + batch_size - 1) // batch_size)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=[4e-5, 1e-3], total_steps=steps, pct_start=0.1)

    history = []
    best_state, best_f1 = None, -1.0
    train_texts = texts(train)
    for epoch in range(epochs):
        model.train()
        order = np.random.permutation(len(train))
        total = 0.0
        for start in range(0, len(order), batch_size):
            idx = order[start:start + batch_size]
            enc = tokenizer([train_texts[i] for i in idx], padding=True, truncation=True, max_length=MAX_LEN, return_tensors="pt").to(DEVICE)
            logits = model(enc["input_ids"], enc["attention_mask"])
            loss = loss_fn(logits, torch.tensor(ytr[idx], device=DEVICE))
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            total += loss.item() * len(idx)
        pva = predict_proba(model, tokenizer, texts(valid))
        f1 = f1_score(yva, pva >= 0.5, average="micro", zero_division=0)
        history.append({"epoch": epoch + 1, "train_loss": total / len(train), "valid_micro_f1": float(f1)})
        print(history[-1], flush=True)
        if f1 > best_f1:
            best_f1 = f1
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)

    thresholds = tune_thresholds(yva, predict_proba(model, tokenizer, texts(valid)))
    results = {}
    for name, rows_, y in (("test_cross_generator", test, yte), ("challenge_handwritten", challenge, ych)):
        p = predict_proba(model, tokenizer, texts(rows_))
        results[name] = {"PainBERT (fine-tuned transformer)": evaluate(y, (p >= thresholds).astype(np.float32))}
        results[name]["Keyword lexicon"] = evaluate(y, lexicon_predict(texts(rows_)))

    # TF-IDF + logistic regression baseline
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    Xtr = vec.fit_transform(train_texts)
    keep = ytr.sum(0) > 0
    clf = OneVsRestClassifier(LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced")).fit(Xtr, ytr[:, keep])
    for name, rows_, y in (("test_cross_generator", test, yte), ("challenge_handwritten", challenge, ych)):
        pred = np.zeros_like(y)
        pred[:, keep] = clf.predict(vec.transform(texts(rows_)))
        results[name]["TF-IDF + logistic regression"] = evaluate(y, pred)

    # Export to ONNX ---------------------------------------------------------
    model = model.to("cpu").eval()
    sample = tokenizer(["my back burns"], return_tensors="pt")
    torch.onnx.export(
        model, (sample["input_ids"], sample["attention_mask"]), str(ARTIFACTS / "painbert.onnx"),
        input_names=["input_ids", "attention_mask"], output_names=["logits"],
        dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"}, "logits": {0: "batch"}},
        opset_version=17, dynamo=False,
    )
    tokenizer.save_pretrained(ARTIFACTS)

    # Parity check: ONNX output must match PyTorch
    session = ort.InferenceSession(str(ARTIFACTS / "painbert.onnx"), providers=["CPUExecutionProvider"])
    enc = tokenizer(texts(challenge)[:16], padding=True, return_tensors="np")
    onnx_logits = session.run(["logits"], {"input_ids": enc["input_ids"].astype(np.int64), "attention_mask": enc["attention_mask"].astype(np.int64)})[0]
    with torch.no_grad():
        torch_logits = model(torch.tensor(enc["input_ids"]), torch.tensor(enc["attention_mask"])).numpy()
    parity = float(np.abs(onnx_logits - torch_logits).max())
    print("onnx max abs diff", parity, flush=True)

    meta = {"labels": LABEL_KEYS, "thresholds": thresholds.round(3).tolist(), "max_len": MAX_LEN, "backbone": BACKBONE}
    (ARTIFACTS / "meta.json").write_text(json.dumps(meta, indent=2))

    label_counts = {k: int(v) for k, v in zip(LABEL_KEYS, ytr.sum(0))}
    card = {
        "name": "PainBERT",
        "version": "1.0",
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task": "Multi-label tagging of 21 clinical pain descriptors in a patient's own free-text description.",
        "architecture": {
            "backbone": BACKBONE,
            "parameters_millions": round(sum(p.numel() for p in model.parameters()) / 1e6, 1),
            "head": "Mean pooling -> dropout(0.1) -> linear(384 -> 21) -> sigmoid",
            "loss": "Binary cross-entropy with square-root inverse-frequency positive weights",
            "optimizer": "AdamW, one-cycle schedule (encoder 4e-5, head 1e-3), 6 epochs, batch 32",
            "runtime": "ONNX (opset 17) on onnxruntime CPU",
            "onnx_parity_max_abs_logit_diff": parity,
        },
        "labels": [{"key": k, "name": LABEL_BY_KEY[k].name, "group": LABEL_BY_KEY[k].group,
                    "definition": LABEL_BY_KEY[k].definition, "dn4": LABEL_BY_KEY[k].dn4,
                    "threshold": float(t), "train_positives": label_counts[k]}
                   for k, t in zip(LABEL_KEYS, thresholds)],
        "data": {
            "method": "Specification-first synthetic generation: label sets are sampled first (inverse-frequency balanced, with explicit negations), each label gets a sampled everyday phrasing and the label's own name is often banned, then an LLM writes a patient note expressing exactly those labels.",
            "lexical_diversity_note": "Version 1 of the data let generators reuse label names ('throbbing', 'pressure'); the word 'cramp' never appeared in 2,508 notes. Version 2 added phrasing hints and word bans; both versions are used for training, only version 2 for testing.",
            "train_generator": "openai/gpt-oss-120b and openai/gpt-oss-20b",
            "test_generator": "qwen/qwen3.8-27b, version 2 prompts (different model family, never seen in training)",
            "n_train": len(train), "n_valid": len(valid), "n_test": len(test), "n_challenge": len(challenge),
            "challenge_set": "Hand-written notes with negation ('no tingling'), slang, metaphor ('ants crawling') and label-free distractors, written before any model was trained.",
        },
        "training_history": history,
        "results": results,
        "limitations": [
            "Training text is synthetic; real patient notes may contain spelling, dialects and topics not represented.",
            "English only. Spanish and other languages are handled upstream by speech translation.",
            "Descriptors are not diagnoses: neuropathic-sounding words raise a screening flag only.",
        ],
    }
    (ROOT / "artifacts" / "painbert_card.json").write_text(json.dumps(card, indent=2))
    summary = {split: {m: {"micro_f1": round(r["micro_f1"], 3), "macro_f1": round(r["macro_f1"], 3)} for m, r in res.items()} for split, res in results.items()}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
