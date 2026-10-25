"""Shared clinical concept vocabulary.

The triage model is trained on CDC NHAMCS emergency-department visits, where
the patient's complaint is coded with the NCHS Reason-for-Visit (RFV)
classification. ANATOME collects the same information differently: as
muscles clicked on a 3D body, questionnaire answers and free text.

This module is the bridge. Both sides are translated into one set of binary
concepts ("pain in the low back", "shortness of breath", ...). Training uses
``concepts_from_rfv_labels``; inference uses ``concepts_from_intake``.
"""

import re

REGION_CONCEPTS = [
    "head", "face_jaw", "neck", "shoulder", "arm", "hand_wrist", "chest",
    "abdomen", "flank", "back", "hip_pelvis", "leg",
    "knee", "ankle_foot",
]

SYMPTOM_CONCEPTS = [
    "nausea_vomiting", "breathless", "fever", "sweating", "numbness",
    "weakness", "dizziness", "palpitations", "swelling", "injury",
]

CONCEPTS = REGION_CONCEPTS + SYMPTOM_CONCEPTS

CONCEPT_NAMES = {
    "head": "Head pain", "face_jaw": "Face / jaw pain", "neck": "Neck pain",
    "shoulder": "Shoulder pain", "arm": "Arm / elbow pain",
    "hand_wrist": "Hand / wrist pain", "chest": "Chest pain",
    "abdomen": "Abdominal pain", "flank": "Flank pain",
    "back": "Back pain",
    "hip_pelvis": "Hip / pelvic pain", "leg": "Leg pain", "knee": "Knee pain",
    "ankle_foot": "Ankle / foot pain", "nausea_vomiting": "Nausea / vomiting",
    "breathless": "Shortness of breath", "fever": "Fever", "sweating": "Sweating",
    "numbness": "Numbness / tingling", "weakness": "Weakness",
    "dizziness": "Dizziness / fainting", "palpitations": "Palpitations",
    "swelling": "Swelling", "injury": "Injury / trauma",
}

# Regexes applied to lower-cased RFV labels. Order does not matter: a label
# may switch on several concepts ("injury of lower back" -> injury, low_back).
RFV_PATTERNS = {
    "head": r"headache|pain in head|migraine|\bhead\b(?!.*cold)|skull|scalp",
    "face_jaw": r"\bface\b|facial|\bjaw\b|toothache|\bmouth\b|\bcheek",
    "neck": r"\bneck\b|cervical spine",
    "shoulder": r"shoulder|clavicle|scapula",
    "arm": r"\barm\b|upper extremity|elbow|forearm",
    "hand_wrist": r"\bhand\b|finger|thumb|wrist",
    "chest": r"chest|\bribs?\b|breast(?!feed)",
    "abdomen": r"abdom|stomach|epigastr|umbilic",
    "flank": r"flank|side pain|kidney (pain|infection|symptoms)",
    "back": r"\bback\b|lumbar|thoracic spine|sacral|coccyx|tailbone|sciatica",
    "hip_pelvis": r"\bhip\b|pelvi|groin|buttock|inguinal",
    "leg": r"\bleg\b|thigh|lower extremity|calf|\bshin",
    "knee": r"\bknee",
    "ankle_foot": r"ankle|\bfoot\b|\bfeet\b|\btoes?\b|heel",
    "nausea_vomiting": r"nausea|vomit",
    "breathless": r"shortness of breath|dyspnea|labored or difficult breathing|breathing problems|wheez",
    "fever": r"(?<!hay )fever|chills",
    "sweating": r"sweat",
    "numbness": r"numbness|tingling|loss of feeling|anesthesia|disturbances of sensation|paresthesia",
    "weakness": r"weakness",
    "dizziness": r"dizz|vertigo|fainting|syncope|lightheaded",
    "palpitations": r"palpitation|pulsations|heart racing|tachycardia",
    "swelling": r"swelling|edema|\blump|\bmass\b",
    "injury": r"injur|fracture|sprain|strain|laceration|contusion|dislocation|accident|fall|burn(?! sensation)|wound|bite",
}
_COMPILED = {key: re.compile(pattern) for key, pattern in RFV_PATTERNS.items()}


def concepts_from_rfv_labels(labels: list[str]) -> dict[str, int]:
    found = {key: 0 for key in CONCEPTS}
    for label in labels:
        text = label.lower()
        for key, pattern in _COMPILED.items():
            if pattern.search(text):
                found[key] = 1
    return found


# ANATOME questionnaire answers -> symptom concepts.
QUESTIONNAIRE_SYMPTOMS = {
    "Nausea": "nausea_vomiting",
    "Sweating": "sweating",
    "Shortness of breath": "breathless",
    "Fever": "fever",
}

# PainBERT labels -> symptom concepts (free-text notes can add evidence).
NLP_TO_CONCEPT = {
    "numbness": "numbness",
    "tingling": "numbness",
    "weakness": "weakness",
    "swelling": "swelling",
    "trauma": "injury",
    "fever": "fever",
}


def concepts_from_intake(
    body_regions: list[str],
    questionnaire: dict,
    nlp_labels: set[str] | None = None,
) -> dict[str, int]:
    found = {key: 0 for key in CONCEPTS}
    for region in body_regions:
        if region in found:
            found[region] = 1
    for answer in questionnaire.get("symptoms", []) or []:
        concept = QUESTIONNAIRE_SYMPTOMS.get(answer)
        if concept:
            found[concept] = 1
    if questionnaire.get("trigger") == "After a fall or injury":
        found["injury"] = 1
    for label in nlp_labels or ():
        concept = NLP_TO_CONCEPT.get(label)
        if concept:
            found[concept] = 1
    return found
