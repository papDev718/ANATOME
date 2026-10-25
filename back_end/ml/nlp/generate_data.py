"""Generate a labelled corpus of patient pain descriptions with an LLM.

This is "specification-first" synthetic data: the label set for every
example is sampled *before* the text is written, and the LLM is only asked
to write a realistic patient note that expresses exactly those labels (and
explicitly denies a few others). Labels therefore come from the sampler, not
from the LLM's own judgement, which keeps them consistent.

Two different generator models are used so that the held-out test set is
written by a different model than the training set; this checks that
PainBERT learned the descriptors, not one generator's writing habits.

Usage:
    python -m ml.nlp.generate_data --split train --n 6000
    python -m ml.nlp.generate_data --split test --n 800
"""

import argparse
import json
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

from .labels import LABEL_BY_KEY, LABEL_KEYS, PHRASINGS

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
OUT_DIR = ROOT / "ml" / "data" / "nlp"

GENERATORS = {
    "train": "openai/gpt-oss-120b",
    "test": "qwen/qwen3.8-27b",
}
BATCH = 20

SITES = [
    "lower back", "neck", "left shoulder", "right shoulder", "right knee", "left knee",
    "left hip", "right hip", "right wrist", "left hand", "fingers", "both feet",
    "left heel", "right ankle", "calf", "thigh", "hamstring", "groin", "upper back",
    "between the shoulder blades", "jaw", "temple", "elbow", "forearm", "buttock",
    "chest wall", "ribs", "shin", "arch of the foot", "big toe", "whole leg",
    "down the back of the leg", "lower belly", "side of the stomach", "tailbone",
]

PERSONAS = [
    "a 15-year-old athlete texting casually",
    "a 72-year-old retiree who writes formally",
    "a 34-year-old nurse who uses some medical words",
    "a 45-year-old construction worker who writes briefly",
    "a 28-year-old office worker who rambles a bit",
    "a 60-year-old with diabetes",
    "a 19-year-old college student who uses slang",
    "a 52-year-old non-native English speaker with simple grammar",
    "a 38-year-old parent writing quickly with a few typos",
    "an 81-year-old who describes things with comparisons",
    "a 25-year-old runner",
    "a 66-year-old who is worried and wordy",
]

LENGTHS = ["a fragment of a few words", "one short sentence", "one short sentence", "one or two sentences", "two to four sentences"]
VERSION = "v2"

SYSTEM = (
    "You write realistic, varied free-text notes that patients type into a "
    "pain intake form. Write in the patient's own voice. Never use the label "
    "names verbatim unless natural; prefer the everyday words, comparisons, "
    "and slang a real patient would use. Express EVERY required feature, "
    "clearly deny EVERY denied feature, and do not mention any other "
    "feature from this list: " + ", ".join(
        f"{k} ({LABEL_BY_KEY[k].definition})" for k in LABEL_KEYS
    )
)

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "notes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["id", "text"],
            },
        }
    },
    "required": ["notes"],
}


def sample_spec(rng: random.Random, counts: dict[str, int]) -> dict:
    # Inverse-frequency sampling keeps rare labels (e.g. bladder_bowel)
    # from being drowned out by common ones.
    weights = [1.0 / (1 + counts[k]) ** 0.8 for k in LABEL_KEYS]
    n_pos = rng.choices([0, 1, 2, 3, 4], weights=[0.05, 0.3, 0.33, 0.22, 0.1])[0]
    positives: list[str] = []
    while len(positives) < n_pos:
        key = rng.choices(LABEL_KEYS, weights=weights)[0]
        if key not in positives:
            positives.append(key)
    remaining = [k for k in LABEL_KEYS if k not in positives]
    n_neg = rng.choices([0, 1, 2], weights=[0.45, 0.4, 0.15])[0]
    negated = rng.sample(remaining, n_neg)
    for key in positives:
        counts[key] += 1
    # Lexical diversity: name a phrasing for each label and often forbid the
    # label's own name, so notes don't just repeat "throbbing", "pressure"...
    hints, banned = {}, []
    for key in positives + negated:
        word = LABEL_BY_KEY[key].name.split(" ")[0].lower()
        allowed = [p for p in PHRASINGS[key] if word not in p]
        if key in positives and allowed and rng.random() < 0.5:
            banned.append(word)
            hints[key] = rng.choice(allowed)
        else:
            hints[key] = rng.choice(PHRASINGS[key])
    return {
        "positives": positives,
        "negated": negated,
        "hints": hints,
        "banned": banned,
        "site": rng.choice(SITES),
        "persona": rng.choice(PERSONAS),
        "length": rng.choice(LENGTHS),
    }


def describe(index: int, spec: dict) -> str:
    hint = lambda k: f"{k} (e.g. '{spec['hints'][k]}' or your own paraphrase)" if spec.get("hints") else k  # noqa: E731
    must = ", ".join(map(hint, spec["positives"])) or "no listed feature (just general discomfort or pain with no specific quality)"
    deny = ", ".join(map(hint, spec["negated"])) or "none"
    avoid = f"; do NOT use the words: {', '.join(spec['banned'])}" if spec.get("banned") else ""
    return (
        f"#{index}: site={spec['site']}; writer={spec['persona']}; "
        f"length={spec['length']}; REQUIRED={must}; DENIED={deny}{avoid}"
    )


def call_llm(client: OpenAI, model: str, specs: list[dict]) -> list[dict]:
    prompt = (
        "Write one patient note per spec below. Return JSON with a 'notes' "
        "array, one object per spec, using the same id.\n\n"
        + "\n".join(describe(i, s) for i, s in enumerate(specs))
    )
    for attempt in range(8):
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "notes", "strict": True, "schema": SCHEMA},
                } if "gpt-oss" in model else {"type": "json_object"},
                temperature=1.0,
                # Groq reserves max_completion_tokens against the per-minute
                # token budget, so keep it close to what 20 notes need.
                max_completion_tokens=3000,
                **({"reasoning_effort": "low"} if "gpt-oss" in model else {}),
            )
            content = completion.choices[0].message.content.strip()
            content = content.removeprefix("```json").removeprefix("```").removesuffix("```")
            notes = json.loads(content)["notes"]
            by_id = {}
            for position, note in enumerate(notes):
                if not note.get("text"):
                    continue
                try:
                    key = int(str(note.get("id", position)).lstrip("#"))
                except ValueError:
                    key = position
                by_id[key] = note["text"].strip()
            return [
                {**spec, "text": by_id[i]}
                for i, spec in enumerate(specs) if i in by_id
            ]
        except RateLimitError:
            print("rate limited, backing off", flush=True)
            time.sleep(min(60, 4 * 2 ** attempt))
        except Exception as exc:  # malformed JSON, timeouts: retry
            print("retry:", type(exc).__name__, str(exc)[:120], flush=True)
            time.sleep(2 + attempt)
    return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=list(GENERATORS), required=True)
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--model", help="Override the generator (each model has its own rate limit).")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model = args.model or GENERATORS[args.split]
    suffix = f"_{VERSION}_" + model.split("/")[-1]
    out_path = OUT_DIR / f"{args.split}_generated{suffix}.jsonl"
    existing = out_path.read_text().splitlines() if out_path.exists() else []
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"],
        timeout=120.0,
    )

    rng = random.Random((7 if args.split == "train" else 1234) + len(suffix) + len(existing))
    counts = {k: 0 for k in LABEL_KEYS}
    for line in existing:
        for key in json.loads(line)["positives"]:
            counts[key] += 1

    needed = args.n - len(existing)
    batches = []
    while needed > 0:
        size = min(BATCH, needed)
        batches.append([sample_spec(rng, counts) for _ in range(size)])
        needed -= size

    lock = threading.Lock()
    done = len(existing)

    def run(batch: list[dict]) -> None:
        nonlocal done
        rows = call_llm(client, model, batch)
        with lock, out_path.open("a") as handle:
            for row in rows:
                row["generator"] = model
                handle.write(json.dumps(row) + "\n")
            done += len(rows)
            print(f"{done}/{args.n}", flush=True)

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(run, batches))


if __name__ == "__main__":
    main()
