"""Train the ANATOME triage-acuity and admission models on CDC NHAMCS data.

Data: National Hospital Ambulatory Medical Care Survey (NHAMCS), emergency
department public-use files 2015-2022, published by the CDC National Center
for Health Statistics. Each row is one real (de-identified) U.S. ED visit,
with a survey weight (PATWT) that says how many national visits it represents.

Task: from what a patient can self-report before seeing anyone (age, sex,
0-10 pain score, where it hurts, associated symptoms), estimate
  1. the triage acuity a nurse assigned (3 classes, from the 5-level ESI-style
     IMMEDR scale), and
  2. whether the visit ended in hospital admission.

Validation is temporal: train on 2015-2020, tune and calibrate on 2021,
report final numbers once on 2022 (a year the model never saw).

Usage:  python -m ml.triage.train_triage
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from scipy.optimize import minimize_scalar
from scipy.special import softmax
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    brier_score_loss, confusion_matrix, log_loss, roc_auc_score, roc_curve,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ml.concepts import CONCEPT_NAMES, CONCEPTS, REGION_CONCEPTS, SYMPTOM_CONCEPTS, concepts_from_rfv_labels

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
ARTIFACTS = ROOT / "artifacts"

COLUMNS = ["AGE", "SEX", "PAINSCALE", "IMMEDR", "RFV1", "RFV2", "RFV3", "RFV4", "RFV5",
           "ADMITHOS", "WAITTIME", "LOS", "PATWT", "RACERETH", "YEAR",
           "CAD", "CHF", "HTN", "DIABTYP0", "DIABTYP1", "DIABTYP2", "COPD", "ASTHMA",
           "CANCER", "CKD", "ESRD", "CEBVD"]
# Self-reportable medical history, mirrored by the ANATOME "history" question.
HISTORY = {
    "hx_heart": ["CAD", "CHF"],
    "hx_hypertension": ["HTN"],
    "hx_diabetes": ["DIABTYP0", "DIABTYP1", "DIABTYP2"],
    "hx_lung": ["COPD", "ASTHMA"],
    "hx_cancer": ["CANCER"],
    "hx_kidney": ["CKD", "ESRD"],
    "hx_stroke": ["CEBVD"],
}
FEATURES = (["age", "sex_female", "pain", "n_regions", "n_symptoms", "n_history"]
            + CONCEPTS + list(HISTORY))
CLASSES = ["less_urgent", "urgent", "emergent"]
CLASS_NAMES = {
    "less_urgent": "Less urgent (ESI 4-5)",
    "urgent": "Urgent (ESI 3)",
    "emergent": "Emergent (ESI 1-2)",
}
RACE = {1: "Non-Hispanic White", 2: "Non-Hispanic Black", 3: "Hispanic", 4: "Non-Hispanic Other"}
RNG = np.random.default_rng(42)


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def load_year(path: Path) -> pd.DataFrame:
    reader = pd.io.stata.StataReader(path)
    df = reader.read(convert_categoricals=False, columns=[c for c in COLUMNS if c != "LOS"] +
                     (["LOS"] if "LOS" in reader.variable_labels() else []))
    labels = reader.value_labels()["RFVF"]
    rfv_text = df[[f"RFV{i}" for i in range(1, 6)]].apply(
        lambda row: [labels.get(int(code), "") for code in row if code > 0], axis=1)
    concepts = pd.DataFrame(list(rfv_text.map(concepts_from_rfv_labels)), index=df.index)
    df = pd.concat([df, concepts], axis=1)
    df["n_rfv"] = rfv_text.map(len)
    if "LOS" not in df:
        df["LOS"] = np.nan
    return df


def build_dataset() -> pd.DataFrame:
    frames = [load_year(path) for path in sorted(RAW.glob("*.dta"))]
    df = pd.concat(frames, ignore_index=True)
    df = df[df["IMMEDR"].isin([1, 2, 3, 4, 5]) & df["PAINSCALE"].between(0, 10) & (df["n_rfv"] > 0)].copy()
    df["age"] = df["AGE"].astype(float)
    df["sex_female"] = (df["SEX"] == 1).astype(float)
    df["pain"] = df["PAINSCALE"].astype(float)
    df["n_regions"] = df[REGION_CONCEPTS].sum(axis=1)
    df["n_symptoms"] = df[SYMPTOM_CONCEPTS].sum(axis=1)
    for feature, source in HISTORY.items():
        df[feature] = (df[source] == 1).any(axis=1).astype(float)
    df["n_history"] = df[list(HISTORY)].sum(axis=1)
    df["acuity"] = df["IMMEDR"].map({1: 2, 2: 2, 3: 1, 4: 0, 5: 0}).astype(int)
    df["admitted"] = (df["ADMITHOS"] == 1).astype(int)
    df["weight"] = df["PATWT"].astype(float)
    return df


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def expected_calibration_error(y: np.ndarray, p: np.ndarray, w: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    total, ece = w.sum(), 0.0
    for b in range(bins):
        mask = idx == b
        if mask.any():
            ece += w[mask].sum() / total * abs(np.average(y[mask], weights=w[mask]) - np.average(p[mask], weights=w[mask]))
    return float(ece)


def calibration_bins(y, p, w, bins: int = 10) -> list[dict]:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    out = []
    for b in range(bins):
        mask = idx == b
        if mask.sum() >= 20:
            out.append({
                "predicted": round(float(np.average(p[mask], weights=w[mask])), 4),
                "observed": round(float(np.average(y[mask], weights=w[mask])), 4),
                "n": int(mask.sum()),
            })
    return out


def roc_points(y, p, w, n: int = 60) -> list[list[float]]:
    fpr, tpr, _ = roc_curve(y, p, sample_weight=w)
    keep = np.unique(np.linspace(0, len(fpr) - 1, n).astype(int))
    return [[round(float(fpr[i]), 4), round(float(tpr[i]), 4)] for i in keep]


def multiclass_report(y, proba, w) -> dict:
    onehot = np.eye(3)[y]
    per_class = {c: float(roc_auc_score(onehot[:, i], proba[:, i], sample_weight=w)) for i, c in enumerate(CLASSES)}
    return {
        "macro_auroc": float(np.mean(list(per_class.values()))),
        "auroc_by_class": per_class,
        "log_loss": float(log_loss(y, proba, sample_weight=w, labels=[0, 1, 2])),
        "brier_emergent": float(brier_score_loss(onehot[:, 2], proba[:, 2], sample_weight=w)),
        "ece_emergent": expected_calibration_error(onehot[:, 2], proba[:, 2], w),
        "accuracy": float(np.average(proba.argmax(1) == y, weights=w)),
    }


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------

def augment_missing_sex(X: pd.DataFrame) -> pd.DataFrame:
    # Sex is optional in the ANATOME intake. Masking it for a slice of the
    # training rows teaches the trees where to route missing values.
    X = X.copy()
    X.loc[RNG.random(len(X)) < 0.15, "sex_female"] = np.nan
    return X


def fit_temperature(logits: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    def nll(t):
        return log_loss(y, softmax(logits / t, axis=1), sample_weight=w, labels=[0, 1, 2])
    return float(minimize_scalar(nll, bounds=(0.5, 3.0), method="bounded").x)


def hgb_logits(model, X) -> np.ndarray:
    return np.log(np.clip(model.predict_proba(X), 1e-9, 1))


def train_acuity(train, valid, test) -> tuple[dict, dict]:
    Xtr, ytr, wtr = augment_missing_sex(train[FEATURES]), train["acuity"].to_numpy(), train["weight"].to_numpy()
    Xva, yva, wva = valid[FEATURES], valid["acuity"].to_numpy(), valid["weight"].to_numpy()
    Xte, yte, wte = test[FEATURES], test["acuity"].to_numpy(), test["weight"].to_numpy()
    wtr_norm = wtr / wtr.mean()

    # Baselines -----------------------------------------------------------
    baselines = {}
    pain_only = LogisticRegression(max_iter=2000).fit(train[["pain"]], ytr, sample_weight=wtr_norm)
    baselines["Pain score only (logistic)"] = multiclass_report(yte, pain_only.predict_proba(test[["pain"]]), wte)
    lin = make_pipeline(StandardScaler(), LogisticRegression(max_iter=4000, C=0.5))
    lin.fit(train[FEATURES], ytr, logisticregression__sample_weight=wtr_norm)
    baselines["All features (logistic)"] = multiclass_report(yte, lin.predict_proba(Xte), wte)

    # Gradient-boosted trees: small grid, selected on the 2021 validation year
    search = []
    best = None
    for lr in (0.05, 0.1):
        for leaves in (15, 31):
            for l2 in (0.0, 1.0):
                model = HistGradientBoostingClassifier(
                    learning_rate=lr, max_leaf_nodes=leaves, l2_regularization=l2,
                    max_iter=600, early_stopping=True, validation_fraction=0.1,
                    n_iter_no_change=30, random_state=0,
                )
                model.fit(Xtr, ytr, sample_weight=wtr_norm)
                score = multiclass_report(yva, model.predict_proba(Xva), wva)
                search.append({"learning_rate": lr, "max_leaf_nodes": leaves, "l2_regularization": l2,
                               "iterations": int(model.n_iter_), "valid_macro_auroc": score["macro_auroc"],
                               "valid_log_loss": score["log_loss"]})
                print("grid", search[-1], flush=True)
                if best is None or score["log_loss"] < best[1]:
                    best = (model, score["log_loss"], search[-1])
    model, _, chosen = best

    temperature = fit_temperature(hgb_logits(model, Xva), yva, wva)
    proba_te = softmax(hgb_logits(model, Xte) / temperature, axis=1)
    report = multiclass_report(yte, proba_te, wte)
    report_uncal = multiclass_report(yte, model.predict_proba(Xte), wte)

    # Safety-net threshold: catch 85% of emergent visits on the validation year
    p_va = softmax(hgb_logits(model, Xva) / temperature, axis=1)[:, 2]
    order = np.argsort(-p_va)
    cum = np.cumsum(wva[order] * (yva[order] == 2)) / (wva * (yva == 2)).sum()
    threshold = float(p_va[order][np.searchsorted(cum, 0.85)])
    flag = proba_te[:, 2] >= threshold
    is_em = yte == 2
    safety = {
        "target_sensitivity": 0.85,
        "threshold": threshold,
        "test_sensitivity": float(np.average(flag[is_em], weights=wte[is_em])),
        "test_specificity": float(np.average(~flag[~is_em], weights=wte[~is_em])),
        "test_ppv": float(np.average(is_em[flag], weights=wte[flag])) if flag.any() else None,
        "test_flag_rate": float(np.average(flag, weights=wte)),
    }

    # Permutation importance (drop in macro AUROC), on a test subsample
    sample = test.sample(min(6000, len(test)), random_state=1)
    base = multiclass_report(sample["acuity"].to_numpy(), softmax(hgb_logits(model, sample[FEATURES]) / temperature, axis=1), sample["weight"].to_numpy())["macro_auroc"]
    importance = []
    for feature in FEATURES:
        drops = []
        for seed in range(3):
            shuffled = sample[FEATURES].copy()
            shuffled[feature] = np.random.default_rng(seed).permutation(shuffled[feature].to_numpy())
            p = softmax(hgb_logits(model, shuffled) / temperature, axis=1)
            drops.append(base - multiclass_report(sample["acuity"].to_numpy(), p, sample["weight"].to_numpy())["macro_auroc"])
        importance.append({"feature": feature, "label": feature_label(feature), "auroc_drop": float(np.mean(drops))})
    importance.sort(key=lambda item: -item["auroc_drop"])

    # Fairness audit: emergent-vs-rest AUROC and calibration by subgroup
    onehot_em = (yte == 2).astype(int)
    groups = {
        "Sex": {"Female": test["SEX"] == 1, "Male": test["SEX"] == 2},
        "Age": {"Under 18": test["age"] < 18, "18-44": test["age"].between(18, 44),
                "45-64": test["age"].between(45, 64), "65+": test["age"] >= 65},
        "Race / ethnicity": {name: test["RACERETH"] == code for code, name in RACE.items()},
    }
    fairness = []
    for axis, members in groups.items():
        for name, mask in members.items():
            m = mask.to_numpy()
            if m.sum() < 200 or onehot_em[m].sum() < 20:
                continue
            fairness.append({
                "axis": axis, "group": name, "n": int(m.sum()),
                "auroc_emergent": float(roc_auc_score(onehot_em[m], proba_te[m, 2], sample_weight=wte[m])),
                "observed_emergent_rate": float(np.average(onehot_em[m], weights=wte[m])),
                "predicted_emergent_rate": float(np.average(proba_te[m, 2], weights=wte[m])),
                "sensitivity_at_threshold": float(np.average(flag[m & is_em], weights=wte[m & is_em])),
            })

    cm = confusion_matrix(yte, proba_te.argmax(1), labels=[0, 1, 2], sample_weight=wte)
    cm = (cm / cm.sum(axis=1, keepdims=True)).round(4).tolist()

    card = {
        "model": "HistGradientBoostingClassifier + temperature scaling",
        "chosen_hyperparameters": chosen,
        "grid_search": search,
        "temperature": temperature,
        "test": report,
        "test_uncalibrated": report_uncal,
        "baselines_test": baselines,
        "safety_net": safety,
        "confusion_matrix_row_normalised": cm,
        "roc_emergent": roc_points(onehot_em, proba_te[:, 2], wte),
        "calibration_emergent": calibration_bins(onehot_em, proba_te[:, 2], wte),
        "permutation_importance": importance,
        "fairness": fairness,
    }
    bundle = {"model": model, "temperature": temperature, "threshold": threshold}
    return bundle, card


def train_admission(train, valid, test) -> tuple[dict, dict]:
    Xtr, ytr = augment_missing_sex(train[FEATURES]), train["admitted"].to_numpy()
    wtr = train["weight"].to_numpy() / train["weight"].mean()
    model = HistGradientBoostingClassifier(learning_rate=0.05, max_leaf_nodes=15, max_iter=600,
                                           early_stopping=True, n_iter_no_change=30, random_state=0)
    model.fit(Xtr, ytr, sample_weight=wtr)
    yte, wte = test["admitted"].to_numpy(), test["weight"].to_numpy()
    p = model.predict_proba(test[FEATURES])[:, 1]
    card = {
        "model": "HistGradientBoostingClassifier",
        "test_auroc": float(roc_auc_score(yte, p, sample_weight=wte)),
        "test_brier": float(brier_score_loss(yte, p, sample_weight=wte)),
        "test_ece": expected_calibration_error(yte, p, wte),
        "base_rate": float(np.average(yte, weights=wte)),
        "roc": roc_points(yte, p, wte),
        "calibration": calibration_bins(yte, p, wte),
    }
    return {"model": model}, card


# --------------------------------------------------------------------------
# Population reference table ("visits like yours")
# --------------------------------------------------------------------------

def weighted_median(values: np.ndarray, weights: np.ndarray) -> float | None:
    mask = values >= 0
    if mask.sum() < 10:
        return None
    v, w = values[mask], weights[mask]
    order = np.argsort(v)
    cum = np.cumsum(w[order])
    return float(v[order][np.searchsorted(cum, cum[-1] / 2)])


def population_table(df: pd.DataFrame) -> dict:
    years = df["YEAR"].nunique()
    df = df.copy()
    df["pain_band"] = pd.cut(df["pain"], [-1, 3, 6, 10], labels=["0-3", "4-6", "7-10"]).astype(str)
    df["age_band"] = pd.cut(df["age"], [-1, 17, 44, 64, 200], labels=["0-17", "18-44", "45-64", "65+"]).astype(str)

    def stats(group: pd.DataFrame) -> dict:
        w = group["weight"].to_numpy()
        return {
            "n_visits_sampled": int(len(group)),
            "national_visits_per_year": int(w.sum() / years),
            "pct_emergent": round(float(np.average(group["acuity"] == 2, weights=w)), 4),
            "pct_admitted": round(float(np.average(group["admitted"], weights=w)), 4),
            "median_wait_min": weighted_median(group["WAITTIME"].to_numpy(float), w),
            "median_hospital_days_if_admitted": weighted_median(
                group.loc[group["admitted"] == 1, "LOS"].fillna(-1).to_numpy(float),
                group.loc[group["admitted"] == 1, "weight"].to_numpy()),
        }

    table = {"overall": stats(df), "by_concept": {}}
    for concept in REGION_CONCEPTS:
        sub = df[df[concept] == 1]
        if len(sub) < 100:
            continue
        entry = {"all": stats(sub), "cells": {}}
        for (pain_band, age_band), cell in sub.groupby(["pain_band", "age_band"]):
            if len(cell) >= 40:
                entry["cells"][f"{pain_band}|{age_band}"] = stats(cell)
        table["by_concept"][concept] = entry
    return table


def feature_label(feature: str) -> str:
    return {
        "age": "Age", "sex_female": "Sex (female)", "pain": "Pain score (0-10)",
        "n_regions": "Number of pain regions", "n_symptoms": "Number of associated symptoms",
        "n_history": "Number of chronic conditions", "hx_heart": "History: heart disease",
        "hx_hypertension": "History: high blood pressure", "hx_diabetes": "History: diabetes",
        "hx_lung": "History: lung disease", "hx_cancer": "History: cancer",
        "hx_kidney": "History: kidney disease", "hx_stroke": "History: stroke",
    }.get(feature, CONCEPT_NAMES.get(feature, feature))


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    df = build_dataset()
    print("dataset", df.shape, df.groupby("YEAR").size().to_dict(), flush=True)
    train = df[df["YEAR"] <= 2020]
    valid = df[df["YEAR"] == 2021]
    test = df[df["YEAR"] == 2022]

    acuity_bundle, acuity_card = train_acuity(train, valid, test)
    admission_bundle, admission_card = train_admission(train, valid, test)

    # Per-feature reference values used for local "what if this were absent"
    # attributions at inference time.
    reference = {f: 0.0 for f in FEATURES}
    reference.update({"age": float(np.median(train["age"])), "sex_female": np.nan, "pain": 0.0})

    joblib.dump({
        "features": FEATURES,
        "classes": CLASSES,
        "class_names": CLASS_NAMES,
        "acuity": acuity_bundle,
        "admission": admission_bundle,
        "reference": reference,
        "sklearn_version": sklearn.__version__,
    }, ARTIFACTS / "triage.joblib", compress=3)

    weights = df["weight"]
    card = {
        "name": "ANATOME Triage-GBM",
        "version": "1.0",
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task": "Estimate the emergency-department triage acuity (ESI-style) and admission likelihood from self-reportable intake information only (no vital signs).",
        "data": {
            "source": "CDC / NCHS National Hospital Ambulatory Medical Care Survey (NHAMCS), Emergency Department public-use files",
            "url": "https://www.cdc.gov/nchs/ahcd/",
            "years": sorted(int(y) for y in df["YEAR"].unique()),
            "inclusion": "Visits with a recorded triage level (1-5), a valid 0-10 pain score and at least one coded reason for visit.",
            "n_total": int(len(df)),
            "n_train": int(len(train)), "n_valid": int(len(valid)), "n_test": int(len(test)),
            "national_visits_represented_per_year": int(weights.sum() / df["YEAR"].nunique()),
            "class_balance_weighted": {c: float(np.average(df["acuity"] == i, weights=weights)) for i, c in enumerate(CLASSES)},
            "split": "Temporal: train 2015-2020, validate/calibrate 2021, test 2022.",
        },
        "features": [{"key": f, "label": feature_label(f)} for f in FEATURES],
        "classes": [{"key": c, "label": CLASS_NAMES[c]} for c in CLASSES],
        "acuity": acuity_card,
        "admission": admission_card,
        "limitations": [
            "Triage nurses use vital signs and appearance; this model sees only self-reported information, so it is deliberately a screening aid, not a triage decision.",
            "NHAMCS describes patients who came to an emergency department; people who stayed home are not represented.",
            "Reason-for-visit codes are mapped to ANATOME body regions with keyword rules; some mismatch between survey coding and 3D-body selections is expected.",
            "Rule-based red-flag checks run alongside the model and always take precedence.",
        ],
    }
    (ARTIFACTS / "triage_card.json").write_text(json.dumps(card, indent=2))
    (ARTIFACTS / "population_stats.json").write_text(json.dumps(population_table(df), indent=2))
    print(json.dumps({"test": acuity_card["test"], "baselines": acuity_card["baselines_test"],
                      "safety": acuity_card["safety_net"], "admission_auroc": admission_card["test_auroc"]}, indent=2))


if __name__ == "__main__":
    main()
