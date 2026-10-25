"""Dynamic int8 quantization of PainBERT, with an accuracy check.

Shrinks the ONNX model about 4x (small enough for GitHub and a cheap server)
and records the F1 change in the model card so the trade-off is documented.

Usage:  python -m ml.nlp.quantize
"""

import json
import time
from pathlib import Path

import numpy as np
from onnxruntime.quantization import QuantType, quantize_dynamic

from .train_painbert import ARTIFACTS, DATA, TEST_VERSION, evaluate, load_jsonl, to_matrix

CARD = ARTIFACTS.parent / "painbert_card.json"


def predict(path: Path, texts: list[str]) -> tuple[np.ndarray, float]:
    import onnxruntime as ort
    from tokenizers import Tokenizer

    meta = json.loads((ARTIFACTS / "meta.json").read_text())
    tok = Tokenizer.from_file(str(ARTIFACTS / "tokenizer.json"))
    tok.enable_truncation(meta["max_len"])
    tok.enable_padding(pad_id=0, pad_token="[PAD]")
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    out, started = [], time.perf_counter()
    for text in texts:  # one at a time, like the live API
        enc = tok.encode_batch([text])
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
        out.append(session.run(["logits"], {"input_ids": ids, "attention_mask": mask})[0][0])
    latency = (time.perf_counter() - started) / len(texts) * 1000
    return 1 / (1 + np.exp(-np.array(out))), latency


def main() -> None:
    fp32, int8 = ARTIFACTS / "painbert.onnx", ARTIFACTS / "painbert.int8.onnx"
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)
    thresholds = np.array(json.loads((ARTIFACTS / "meta.json").read_text())["thresholds"])

    report = {
        "method": "onnxruntime dynamic quantization, int8 weights (QInt8)",
        "size_mb_fp32": round(fp32.stat().st_size / 1e6, 1),
        "size_mb_int8": round(int8.stat().st_size / 1e6, 1),
    }
    for name, path in (("challenge_handwritten", Path(__file__).with_name("challenge_set.jsonl")),
                       ("test_cross_generator", None)):
        rows = load_jsonl(path) if path else [
            row for test in sorted(DATA.glob(f"test_generated_{TEST_VERSION}_*.jsonl")) for row in load_jsonl(test)]
        y = to_matrix(rows)
        texts = [r["text"] for r in rows]
        p32, ms32 = predict(fp32, texts)
        p8, ms8 = predict(int8, texts)
        report[name] = {
            "micro_f1_fp32": evaluate(y, (p32 >= thresholds).astype(np.float32))["micro_f1"],
            "micro_f1_int8": evaluate(y, (p8 >= thresholds).astype(np.float32))["micro_f1"],
            "max_probability_diff": float(np.abs(p32 - p8).max()),
            "latency_ms_fp32": round(ms32, 2),
            "latency_ms_int8": round(ms8, 2),
        }
    card = json.loads(CARD.read_text())
    card["quantization"] = report
    card["architecture"]["runtime"] = "ONNX (opset 17), int8 dynamic quantization, onnxruntime CPU"
    CARD.write_text(json.dumps(card, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
