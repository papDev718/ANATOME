# ANATOME decision-support models

ANATOME runs four engines on every analysis request (`POST /api/analyze`)
and on every report (`POST /api/reports`). Their outputs are combined into a
care level and passed to the clinician-report writer.

| Engine | Kind | Trained on | Artifact |
|---|---|---|---|
| **Triage-GBM** | Gradient-boosted trees (scikit-learn) | CDC NHAMCS emergency-department visits, 2015–2022 | `artifacts/triage.joblib` |
| **PainBERT** | Fine-tuned transformer (BGE-small, 33M params) | Specification-first synthetic patient notes | `artifacts/painbert/painbert.int8.onnx` |
| **Anatomy engine** | Knowledge graph (rules) | Standard anatomy references | `anatomy.py` |
| **Red-flag rules** | Deterministic rules | Published clinical guidance | `red_flags.py` |

Model cards (all metrics, fairness audit, limitations) are written next to
the artifacts as JSON and served at `GET /api/models`.

## Layout

```
ml/
  concepts.py            shared vocabulary: CDC reason-for-visit codes <-> ANATOME inputs
  anatomy.py             structure -> region, WPI area, nerve, spinal roots; pattern analysis
  red_flags.py           guideline warning-sign rules
  inference.py           loads artifacts, runs the full pipeline
  triage/train_triage.py
  nlp/labels.py          the 21 PainBERT labels (6 are DN4 interview items)
  nlp/generate_data.py   LLM data generation (Groq)
  nlp/train_painbert.py  fine-tune, evaluate, export ONNX
  nlp/quantize.py        int8 quantization + accuracy check
  nlp/challenge_set.jsonl  hand-written evaluation notes
  artifacts/             trained models and model cards (committed)
  data/                  raw and generated data (not committed)
```

## Reproducing

All commands run from `back_end/` with the training requirements installed:

```bash
pip install -r requirements-train.txt
```

### Triage-GBM

1. Download the NHAMCS emergency-department Stata files for 2015–2022 from
   <https://ftp.cdc.gov/pub/Health_Statistics/NCHS/dataset_documentation/NHAMCS/stata/>
   (`ED2015-stata.zip` … `ed2022-stata.zip`) and unzip them into `ml/data/raw/`.
2. `python -m ml.triage.train_triage` (about one minute on a laptop).

What it does:

* keeps visits with a nurse triage level 1–5, a valid 0–10 pain score and at
  least one coded reason for visit (75,383 visits);
* turns the reason-for-visit labels into 14 body-region and 10 symptom
  concepts with the regexes in `concepts.py`, plus age, sex, pain score and
  7 self-reportable medical-history items;
* splits by year: train 2015–2020, tune and calibrate on 2021, test once on 2022;
* trains with the CDC survey weights (`PATWT`) so results represent all U.S.
  ED visits, picks hyper-parameters by validation log-loss, then fits a
  temperature for calibration;
* reports AUROC, log-loss, Brier, calibration error, a confusion matrix,
  permutation importance, a safety-net threshold (85% sensitivity for
  emergent visits) and a fairness audit by sex, age and race/ethnicity;
* also trains an admission model and builds the "visits like yours"
  population table.

Results on the unseen 2022 year: macro AUROC 0.741 (pain score alone 0.536,
logistic regression 0.726), emergent calibration error 0.017, admission
AUROC 0.808.

### PainBERT

1. Put a `GROQ_API_KEY` in `back_end/.env`.
2. Generate notes. Each Groq model has its own rate limit, so run them in parallel:
   ```bash
   python -m ml.nlp.generate_data --split train --n 2000
   python -m ml.nlp.generate_data --split train --model openai/gpt-oss-20b --n 1600
   python -m ml.nlp.generate_data --split test --n 600
   ```
3. `python -m ml.nlp.train_painbert` (a few minutes on Apple silicon via MPS).
4. `python -m ml.nlp.quantize`

The data are *specification-first*: for each note the label set (and a few
explicitly denied labels) is sampled before the text exists, then an LLM
writes a note expressing exactly that. The test set is written by a
different model family (Qwen) than the training set (GPT-OSS), and a
hand-written challenge set of negations, slang and metaphors is held out
entirely. Baselines: a keyword lexicon and TF-IDF + logistic regression.

## Tests

`python -m unittest discover -s tests`

## Safety

Every number shown to a patient is framed as decision support. The red-flag
rules always take precedence over the models' estimates, the models never
produce a diagnosis, and the only external AI call that sees intake data (the
report writer) never receives the patient's name.

## Body areas, structure localizer and the patient care guide (Oct 2026)

* **Body areas** (`ml/body_map.py`). The 659 GLB structures are grouped into 15 everyday areas
  ("Stomach / belly", "Lower back", "Knee (left)", ...). For back and leg structures the area of a
  tap comes from its height, because long muscles cross borders (latissimus over the lower back,
  the quadriceps tendon over the knee). `python -m ml.body_map` rebuilds
  `artifacts/body_map.json` (voxel-sampled surface points per structure) and
  `front_end/src/data/bodyAreas.json` from the GLB.
* **Structure localizer.** For a body-area spot, ranks the structures under the tap: Gaussian
  weight on distance to each structure's nearest surface point (sigma 2.5 cm), times a tissue prior
  from the patient's words, with neighbouring-area structures down-weighted. It is a transparent
  scoring rule, not a trained model. Sweep over every structure (`python -m tests.sweep`): 86% of
  structures are covered by other layers and cannot be tapped directly; for the 84 that can, the
  intended structure is in the top 3 for 82. On the hand-written scenarios: 19/19 top-3, 56/57
  with taps 1.5 cm off target.
* **Model label fix.** The GLB swaps "Ascending" and "Descending part of trapezius" relative to the
  meshes' positions; `MODEL_LABEL_FIXES` in `ml/anatomy.py` (and `anatomyName.js`) corrects it.
* **Text signals** (`ml/text_signals.py`). Symptoms, onset and trend from the spoken description,
  with a negation window, plus a corroboration gate on PainBERT: labels that change rules or advice
  (trauma, bladder/bowel, tingling, ...) need p >= 0.9 or a supporting, non-negated word.
* **Care guide** (`care_guide.py`, `POST /api/care-guide`). Tips are selected deterministically
  from a vetted, cited library; emergencies get no self-care. An LLM (Groq) only rewords the
  selected tips; a validator drops any line adding a medicine, dose, diagnosis or exercise not in
  the source tips, and falls back to the vetted text on any failure.
* **Tests.** `python -m tests.scenarios [--llm N]` (41 patient scenarios), `python -m tests.sweep`
  (every-structure sweep, 34 phrases, 600 random patients vs. safety invariants), and
  `tests/test_scenarios.py` runs them under unittest.
