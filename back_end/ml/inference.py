"""Runtime for all ANATOME models.

Loads each trained artifact once and exposes ``analyze_intake`` (the full
decision-support pipeline) and ``tag_text`` (PainBERT on one note).
Every model is optional: if an artifact is missing the corresponding part of
the response is ``None`` and the rest still works.
"""

import json
import re
from functools import lru_cache
from pathlib import Path
from time import perf_counter

import numpy as np

from .anatomy import analyse_pain_map
from .body_map import SIMPLE_AREAS, localize
from .concepts import CONCEPT_NAMES, REGION_CONCEPTS, SYMPTOM_CONCEPTS, concepts_from_intake
from .nlp.labels import DN4_KEYS, LABEL_BY_KEY
from .red_flags import LEVELS, evaluate_red_flags
from .text_signals import corroborate, onset_from_text, sudden_onset, symptoms_from_text, trend_from_text

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"

HISTORY_OPTIONS = {
    "Heart disease": "hx_heart",
    "High blood pressure": "hx_hypertension",
    "Diabetes": "hx_diabetes",
    "Lung disease (asthma or COPD)": "hx_lung",
    "Cancer": "hx_cancer",
    "Kidney disease": "hx_kidney",
    "Stroke": "hx_stroke",
}


# --------------------------------------------------------------------------
# PainBERT
# --------------------------------------------------------------------------

class PainBERTRuntime:
    def __init__(self, directory: Path):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        meta = json.loads((directory / "meta.json").read_text())
        self.labels: list[str] = meta["labels"]
        self.thresholds = np.array(meta["thresholds"], dtype=np.float32)
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(meta["max_len"])
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        # Prefer the int8-quantized model (see ml/nlp/quantize.py).
        model_path = directory / "painbert.int8.onnx"
        if not model_path.exists():
            model_path = directory / "painbert.onnx"
        self.session = ort.InferenceSession(str(model_path), options, providers=["CPUExecutionProvider"])

    def proba(self, texts: list[str]) -> np.ndarray:
        encodings = self.tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in encodings], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        logits = self.session.run(["logits"], {"input_ids": ids, "attention_mask": mask})[0]
        return 1 / (1 + np.exp(-logits))

    def tag(self, text: str, explain: bool = True) -> dict:
        text = (text or "").strip()
        if not text:
            return {"labels": [], "highlights": [], "dn4": dn4_summary(set())}
        started = perf_counter()
        words = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)][:80]
        variants = [text]
        if explain and len(words) > 1:
            # Occlusion: drop one word at a time and see which detected
            # labels lose confidence. All variants run in one ONNX batch.
            variants += [(text[:s] + text[e:]).strip() for s, e in words]
        probs = self.proba(variants)
        full = probs[0]
        detected = [i for i, p in enumerate(full) if p >= self.thresholds[i]]
        labels = [{
            "key": self.labels[i],
            "name": LABEL_BY_KEY[self.labels[i]].name,
            "group": LABEL_BY_KEY[self.labels[i]].group,
            "probability": round(float(full[i]), 4),
            "dn4": LABEL_BY_KEY[self.labels[i]].dn4,
        } for i in sorted(detected, key=lambda i: -full[i])]

        highlights = []
        if explain and detected and len(variants) > 1:
            drops = full[detected][None, :] - probs[1:, detected]
            for w, (start, end) in enumerate(words):
                j = int(np.argmax(drops[w]))
                if drops[w, j] >= 0.12:
                    highlights.append({
                        "start": start, "end": end, "label": self.labels[detected[j]],
                        "weight": round(float(min(drops[w, j], 1.0)), 3),
                    })
        keys = {label["key"] for label in labels}
        return {"labels": labels, "highlights": highlights, "dn4": dn4_summary(keys),
                "latency_ms": round((perf_counter() - started) * 1000, 1)}


def dn4_summary(keys: set[str]) -> dict:
    items = [{"key": k, "name": LABEL_BY_KEY[k].name, "present": k in keys} for k in DN4_KEYS]
    score = sum(item["present"] for item in items)
    return {
        "score": score, "max": len(DN4_KEYS), "items": items,
        "flag": score >= 3,
        "note": "Three or more neuropathic descriptors (based on the DN4 interview items) suggest nerve-related pain features worth discussing with a clinician." if score >= 3 else None,
    }


# --------------------------------------------------------------------------
# Triage-GBM
# --------------------------------------------------------------------------

class TriageRuntime:
    def __init__(self, path: Path, population_path: Path):
        import joblib
        from scipy.special import softmax

        self._softmax = softmax
        bundle = joblib.load(path)
        self.features: list[str] = bundle["features"]
        self.classes: list[str] = bundle["classes"]
        self.class_names: dict = bundle["class_names"]
        self.model = bundle["acuity"]["model"]
        self.temperature = bundle["acuity"]["temperature"]
        self.threshold = bundle["acuity"]["threshold"]
        self.admission = bundle["admission"]["model"]
        self.reference = bundle["reference"]
        self.population = json.loads(population_path.read_text()) if population_path.exists() else None

    def _acuity(self, X: np.ndarray) -> np.ndarray:
        logits = np.log(np.clip(self.model.predict_proba(X), 1e-9, 1))
        return self._softmax(logits / self.temperature, axis=1)

    def predict(self, row: dict) -> dict:
        # OpenMP thread start-up dominates on single-row batches; one thread
        # is ~25x faster here.
        from threadpoolctl import threadpool_limits

        with threadpool_limits(1):
            return self._predict(row)

    def _predict(self, row: dict) -> dict:
        import pandas as pd

        X = pd.DataFrame([[row.get(f, np.nan) for f in self.features]], columns=self.features, dtype=float)
        proba = self._acuity(X)[0]
        admission = float(self.admission.predict_proba(X)[0, 1])

        # Local attribution: re-score with each active feature reset to its
        # reference value ("what if this were absent"). One batched call.
        active = [f for f in self.features if not _same(row.get(f), self.reference.get(f)) and not f.startswith("n_")]
        attributions = []
        if active:
            variants = pd.concat([X] * len(active), ignore_index=True)
            for i, f in enumerate(active):
                variants.loc[i, f] = self.reference.get(f, 0.0)
                if f in REGION_CONCEPTS:
                    variants.loc[i, "n_regions"] = X["n_regions"][0] - 1
                elif f in SYMPTOM_CONCEPTS:
                    variants.loc[i, "n_symptoms"] = X["n_symptoms"][0] - 1
                elif f.startswith("hx_"):
                    variants.loc[i, "n_history"] = X["n_history"][0] - 1
            alt = self._acuity(variants)
            score = lambda p: p[..., 1] * 0.5 + p[..., 2]  # noqa: E731  (expected acuity, 0-1.5)
            for i, f in enumerate(active):
                attributions.append({
                    "feature": f, "label": _feature_label(f, row.get(f)),
                    "delta_emergent": round(float(proba[2] - alt[i, 2]), 4),
                    "delta_score": round(float(score(proba) - score(alt[i])), 4),
                })
            attributions.sort(key=lambda a: -abs(a["delta_emergent"]))

        return {
            "probabilities": [{"key": c, "label": self.class_names[c], "p": round(float(p), 4)} for c, p in zip(self.classes, proba)],
            "predicted": self.classes[int(np.argmax(proba))],
            "p_emergent": round(float(proba[2]), 4),
            "safety_net_flag": bool(proba[2] >= self.threshold),
            "safety_net_threshold": round(self.threshold, 4),
            "p_admission": round(admission, 4),
            "attributions": attributions[:8],
        }

    def population_context(self, regions: list[str], pain: float, age: float | None) -> list[dict]:
        if not self.population:
            return []
        pain_band = "0-3" if pain <= 3 else "4-6" if pain <= 6 else "7-10"
        age_band = None if age is None else "0-17" if age < 18 else "18-44" if age < 45 else "45-64" if age < 65 else "65+"
        out = []
        for region in regions:
            entry = self.population["by_concept"].get(region)
            if not entry:
                continue
            cell = entry["cells"].get(f"{pain_band}|{age_band}") if age_band else None
            stats, scope = (cell, f"pain {pain_band}, age {age_band}") if cell else (entry["all"], "all ages and pain levels")
            out.append({"concept": region, "label": CONCEPT_NAMES[region], "scope": scope, **stats})
        return out


def _same(a, b) -> bool:
    if a is None or (isinstance(a, float) and np.isnan(a)):
        return b is None or (isinstance(b, float) and np.isnan(b))
    return b is not None and not (isinstance(b, float) and np.isnan(b)) and float(a) == float(b)


def _feature_label(feature: str, value) -> str:
    if feature == "age":
        return "Age not given" if value is None or np.isnan(value) else f"Age {int(value)}"
    if feature == "pain":
        return f"Pain {int(value)}/10"
    if feature == "sex_female":
        return "Sex: female" if value == 1 else "Sex: male"
    if feature.startswith("hx_"):
        name = next((k for k, v in HISTORY_OPTIONS.items() if v == feature), feature)
        return f"History: {name.lower()}"
    return CONCEPT_NAMES.get(feature, feature)


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

@lru_cache(maxsize=1)
def painbert() -> PainBERTRuntime | None:
    directory = ARTIFACTS / "painbert"
    if not any((directory / name).exists() for name in ("painbert.int8.onnx", "painbert.onnx")):
        return None
    return PainBERTRuntime(directory)


@lru_cache(maxsize=1)
def triage() -> TriageRuntime | None:
    path = ARTIFACTS / "triage.joblib"
    if not path.exists():
        return None
    return TriageRuntime(path, ARTIFACTS / "population_stats.json")


def model_cards() -> dict:
    cards = {}
    for key, name in (("triage", "triage_card.json"), ("painbert", "painbert_card.json")):
        path = ARTIFACTS / name
        cards[key] = json.loads(path.read_text()) if path.exists() else None
    return cards


def tag_text(text: str) -> dict | None:
    runtime = painbert()
    return runtime.tag(text) if runtime else None


# --------------------------------------------------------------------------
# Full pipeline
# --------------------------------------------------------------------------

CARE_LEVELS = {
    "emergency": ("Emergency care now", "Call 911 or go to the nearest emergency department."),
    "urgent": ("Same-day medical evaluation", "Contact a clinician or urgent care today."),
    "soon": ("See a clinician within a few days", "Book an appointment with your doctor or a physical therapist."),
    "routine": ("Routine follow-up", "Mention this at your next appointment, sooner if it changes or worsens."),
}


def gated_tag(runtime: "PainBERTRuntime", text: str) -> dict:
    """PainBERT plus the corroboration gate (see text_signals.corroborate)."""
    tagged = runtime.tag(text)
    kept, dropped = corroborate(tagged["labels"], text)
    tagged["labels"], tagged["gated_out"] = kept, dropped
    tagged["dn4"] = dn4_summary({label["key"] for label in kept})
    return tagged


PILL_DESCRIPTORS = {"Burning": "burning", "Sharp": "sharp", "Throbbing": "throbbing", "Shooting": "electric",
                    "Aching": "aching", "Dull": "aching", "Cramping": "pressure", "Pressure": "pressure", "Tingling": "tingling", "Numb": "numbness"}
AREA_REGION = {key: value[2] for key, value in SIMPLE_AREAS.items()}
ONSET_ORDER = ["Within the last hour", "Today", "1–3 days ago", "4–7 days ago", "1–4 weeks ago", "More than one month ago"]


def intake_text(payload: dict) -> str:
    """The patient's own description: the voice/typed intake plus any extra note."""
    questionnaire = payload.get("questionnaire") or {}
    parts = [questionnaire.get("patient_description"), payload.get("global_note")]
    return "\n".join(p.strip() for p in parts if isinstance(p, str) and p.strip())


def analyze_intake(payload: dict) -> dict:
    started = perf_counter()
    questionnaire = dict(payload.get("questionnaire") or {})
    raw_spots = payload.get("pain_regions") or {}
    age = payload.get("age")
    age = float(age) if age not in (None, "") else None
    sex = payload.get("sex")
    history = [h for h in (questionnaire.get("history") or []) if h in HISTORY_OPTIONS]
    description = intake_text(payload)
    max_severity = max([float(s.get("severity") or 0) for s in raw_spots.values()], default=0.0)

    # PainBERT on every spot's note plus the patient's description
    runtime = painbert()
    notes = []
    nlp_keys: set[str] = set()
    spot_keys: dict[str, set[str]] = {}
    if runtime:
        for spot_id, spot in raw_spots.items():
            if (spot.get("notes") or "").strip():
                tagged = gated_tag(runtime, spot["notes"])
                notes.append({"spot_id": spot_id, "region": spot.get("regionName"), "text": spot["notes"], **tagged})
                spot_keys[spot_id] = {label["key"] for label in tagged["labels"]}
                nlp_keys |= spot_keys[spot_id]
        if description:
            tagged = gated_tag(runtime, description)
            notes.append({"spot_id": None, "region": None, "text": description, **tagged})
            nlp_keys |= {label["key"] for label in tagged["labels"]}
    # The per-spot pain-type pill is an explicit descriptor too.
    for spot_id, spot in raw_spots.items():
        if spot.get("painType") in PILL_DESCRIPTORS:
            spot_keys.setdefault(spot_id, set()).add(PILL_DESCRIPTORS[spot["painType"]])
            nlp_keys.add(PILL_DESCRIPTORS[spot["painType"]])

    # Body-area spots ("my stomach"): find the structures under the spot.
    localization = {}
    spots = []
    for spot_id, spot in raw_spots.items():
        spot = dict(spot)
        if spot.get("mode") == "area" and spot.get("areaKey"):
            text = " ".join(filter(None, [spot.get("notes"), description]))
            result = localize(spot["areaKey"], spot.get("side"), spot.get("clickPosition"), spot_keys.get(spot_id, set()) | nlp_keys, text)
            result["area"] = spot.get("areaLabel") or spot["areaKey"]
            localization[spot_id] = result
            if result["candidates"]:
                spot["structureName"] = result["candidates"][0]["name"]
                spot["inferredStructure"] = result["confidence"] != "high"
            spot["areaRegion"] = AREA_REGION.get(spot["areaKey"])
        spots.append(spot)

    anatomy = analyse_pain_map(spots)
    regions = sorted({s["region"] for s in anatomy["structures"]})

    # Facts the old checkbox questionnaire used to collect, read from text
    text_symptoms = symptoms_from_text(" ".join(filter(None, [description] + [s.get("notes") for s in spots])))
    spot_onsets = [s.get("onset") for s in spots if s.get("onset") in ONSET_ORDER]
    if not questionnaire.get("onset"):
        questionnaire["onset"] = min(spot_onsets, key=ONSET_ORDER.index) if spot_onsets else onset_from_text(description)
    if not questionnaire.get("trend"):
        questionnaire["trend"] = trend_from_text(description)
    for key in ("weakness", "numbness", "bladder_bowel"):
        if key in text_symptoms:
            nlp_keys.add(key)
    if "fever" in text_symptoms:
        nlp_keys.add("fever")

    concepts = concepts_from_intake(regions, questionnaire, nlp_keys)
    for key in text_symptoms:
        if key in concepts:
            concepts[key] = 1
    symptoms = {k for k, v in concepts.items() if v and k not in REGION_CONCEPTS}
    if "blood" in text_symptoms:
        symptoms.add("blood")

    triage_out = None
    population = []
    model = triage()
    if model and spots:
        row = {
            "age": age if age is not None else np.nan,
            "sex_female": 1.0 if sex == "Female" else 0.0 if sex == "Male" else np.nan,
            "pain": max_severity,
            **{k: float(v) for k, v in concepts.items()},
        }
        row["n_regions"] = float(sum(concepts[k] for k in REGION_CONCEPTS))
        row["n_symptoms"] = float(len(symptoms))
        for option, feature in HISTORY_OPTIONS.items():
            row[feature] = 1.0 if option in history else 0.0
        row["n_history"] = float(len(history))
        triage_out = model.predict(row)
        population = model.population_context([r for r in regions if concepts.get(r)], max_severity, age)

    flags = evaluate_red_flags({
        "regions": set(regions), "symptoms": symptoms, "nlp": nlp_keys,
        "max_severity": max_severity, "age": age, "onset": questionnaire.get("onset"),
        "history": {HISTORY_OPTIONS[h].removeprefix("hx_") for h in history},
        "trend": questionnaire.get("trend"), "sudden": sudden_onset(description),
    })

    # Care level: rules first, then the model's estimate.
    top_flag = flags[0]["level"] if flags else None
    if top_flag in ("emergency", "urgent"):
        level, basis = top_flag, "red_flag_rule"
    elif triage_out and triage_out["p_emergent"] >= 0.30:
        level, basis = "urgent", "model"
    elif triage_out and triage_out["p_emergent"] >= 0.15:
        level, basis = "soon", "model"
    elif top_flag == "review":
        level, basis = "soon", "review_rule"
    elif max_severity >= 7:
        level, basis = "soon", "severity"
    elif spots:
        level, basis = "routine", "model" if triage_out else "severity"
    else:
        level, basis = None, None

    dn4 = dn4_summary(nlp_keys)
    return {
        "care_level": None if level is None else {
            "level": level, "title": CARE_LEVELS[level][0], "action": CARE_LEVELS[level][1], "basis": basis,
            "rank": ["routine", "soon", "urgent", "emergency"].index(level),
        },
        "red_flags": flags,
        "triage": triage_out,
        "population": population,
        "anatomy": anatomy,
        "localization": localization,
        "text_findings": {"symptoms": text_symptoms, "onset": questionnaire.get("onset"), "trend": questionnaire.get("trend")},
        "language": {"notes": notes, "descriptors": sorted(nlp_keys), "dn4": dn4},
        "concepts": [{"key": k, "label": CONCEPT_NAMES[k]} for k, v in concepts.items() if v],
        "models": {"painbert": runtime is not None, "triage": model is not None},
        "latency_ms": round((perf_counter() - started) * 1000, 1),
        "levels": LEVELS,
    }
