"""Deterministic red-flag rules.

The ML models estimate risk from population data; these rules encode
well-known warning-sign combinations from clinical guidance and always take
precedence over a model's estimate. Each rule cites where it comes from.
"""

from dataclasses import asdict, dataclass

LEVELS = ["support", "review", "urgent", "emergency"]


@dataclass
class RedFlag:
    id: str
    level: str
    title: str
    detail: str
    source: str
    evidence: list[str]


def evaluate_red_flags(ctx: dict) -> list[dict]:
    """``ctx`` keys: regions (set), symptoms (set of concepts), nlp (set of
    PainBERT labels), max_severity, age, onset, history (set), trend."""
    regions, symptoms, nlp = ctx["regions"], ctx["symptoms"], ctx["nlp"]
    severity, age = ctx["max_severity"], ctx.get("age")
    onset, history, trend = ctx.get("onset"), ctx["history"], ctx.get("trend")
    flags: list[RedFlag] = []

    def add(*args):
        flags.append(RedFlag(*args))

    cardiac_companions = symptoms & {"breathless", "sweating", "nausea_vomiting", "dizziness"}
    if "chest" in regions and cardiac_companions:
        add("chest_plus", "emergency", "Chest pain with breathing difficulty, sweating or nausea",
            "This combination is a recognised warning sign of a heart or lung emergency. Call 911 or go to the nearest emergency department now.",
            "American Heart Association: warning signs of heart attack",
            ["Chest wall marked"] + sorted(cardiac_companions))

    if "chest" in regions and not cardiac_companions and nlp & {"pressure", "radiating"} and "injury" not in symptoms:
        add("chest_pressure", "emergency", "Chest pain that feels tight, heavy or spreads",
            "Chest pain that feels tight, heavy or squeezing, or that spreads to the arm, neck, jaw or back, needs emergency assessment. Call 911.",
            "NHS: chest pain (call 999 if it feels tight, heavy or spreads)", ["Chest marked"] + sorted(nlp & {"pressure", "radiating"}))
    elif "chest" in regions and not cardiac_companions and "injury" not in symptoms:
        add("chest_any", "urgent", "Chest pain without a clear injury",
            "Chest pain that did not start with an injury or strain should be checked by a clinician the same day, even if it seems mild.",
            "NHS: chest pain (get help from 111 or a GP urgently)", ["Chest marked", "No injury reported"])

    if "blood" in symptoms:
        add("bleeding", "emergency", "Blood in vomit, stool or urine",
            "Vomiting blood, or black or bloody stools, needs emergency assessment.",
            "NHS: vomiting blood and rectal bleeding (call 999 / go to A&E)", ["Blood reported"])

    if "dizziness" in symptoms and "chest" not in regions:
        add("dizzy", "urgent", "Dizziness or fainting with pain",
            "Fainting, or feeling faint, together with pain should be checked the same day.",
            "NHS 111 urgent-symptom guidance", ["Dizziness / fainting"])

    if "back" in regions and ("bladder_bowel" in nlp):
        add("cauda_equina", "emergency", "Back pain with bladder/bowel change or saddle numbness",
            "New loss of bladder or bowel control, or numbness around the groin, together with back pain needs emergency assessment.",
            "NICE guideline NG59 and cauda equina syndrome red flags", ["Back pain", "Bladder/bowel or saddle symptoms in notes"])

    if "head" in regions and ((severity >= 9 and onset in ("Within the last hour", "Today")) or (ctx.get("sudden") and severity >= 7)):
        add("thunderclap", "emergency", "Sudden, severe head pain",
            "A sudden, very severe headache can be a sign of bleeding in or around the brain and needs emergency evaluation.",
            "American College of Emergency Physicians: thunderclap headache", [f"Head pain {severity}/10", f"Onset: {onset or 'sudden'}"])

    if "breathless" in symptoms and "chest" not in regions:
        add("breathless", "urgent", "Shortness of breath",
            "Shortness of breath alongside pain should be checked promptly, the same day.",
            "NHS 111 urgent-symptom guidance", ["Shortness of breath"])

    if "back" in regions and "fever" in symptoms:
        add("spinal_infection", "urgent", "Back pain with fever",
            "Fever together with back pain can signal an infection and should be assessed the same day.",
            "NICE NG59 red flags for serious spinal pathology", ["Back pain", "Fever"])

    if "swelling" in nlp and "fever" in symptoms:
        add("hot_joint", "urgent", "Swelling with fever",
            "A swollen, warm area together with fever can be a sign of infection and needs same-day assessment.",
            "British Society for Rheumatology: hot swollen joint guidance", ["Swelling", "Fever"])

    if "leg" in regions and "swelling" in nlp and "trauma" not in nlp:
        add("dvt", "urgent", "Leg pain with swelling and no injury",
            "One-sided calf or leg pain with swelling but no injury can be a sign of a blood clot and should be checked promptly.",
            "CDC: signs and symptoms of deep vein thrombosis", ["Leg pain", "Swelling", "No injury reported"])

    if "weakness" in nlp or "weakness" in symptoms:
        add("weakness", "urgent", "New weakness",
            "New muscle weakness (a limb giving way, dropping things, foot drop) should be assessed promptly.",
            "NICE NG59 / neurological red flags", ["Weakness described"])

    if "injury" in symptoms and ((age is not None and age >= 65) or severity >= 8):
        add("trauma_risk", "urgent", "Injury with high pain or older age",
            "Severe pain after an injury, or any significant injury in someone 65 or older, warrants imaging and examination to rule out a fracture.",
            "Ottawa ankle/knee rules and Canadian C-spine rule (age 65+ high risk)",
            ["Injury reported"] + ([f"Age {age}"] if age is not None and age >= 65 else []) + ([f"Pain {severity}/10"] if severity >= 8 else []))

    if "abdomen" in regions and (severity >= 9 or (severity >= 7 and symptoms & {"fever", "nausea_vomiting"})):
        add("abdomen_severe", "urgent", "Severe abdominal pain" + (" with fever or vomiting" if symptoms & {"fever", "nausea_vomiting"} else ""),
            "Severe belly pain, especially with fever or vomiting, should be evaluated the same day. Go to the emergency department if it is unbearable, the belly is hard to the touch, or you cannot keep fluids down.",
            "American College of Emergency Physicians: abdominal pain warning signs", [f"Abdominal pain {severity}/10"] + sorted(symptoms & {"fever", "nausea_vomiting"}))

    if "back" in regions and "cancer" in history and ("night_pain" in nlp or (age or 0) >= 50):
        add("malignancy", "review", "Back pain with a history of cancer",
            "Back pain in someone with a history of cancer should be reviewed by a clinician soon.",
            "NICE NG59 red flags for serious spinal pathology", ["Back pain", "History of cancer"])

    if trend == "It is getting worse" and severity >= 7:
        add("worsening", "review", "Severe pain that is getting worse",
            "Pain that keeps getting worse should be reviewed by a clinician, even without other warning signs.",
            "General practice safety-netting guidance", [f"Pain {severity}/10", "Getting worse"])

    yellow = nlp & {"distress", "sleep_loss", "function_loss"}
    if len(yellow) >= 2:
        add("yellow_flags", "review", "Pain is affecting mood, sleep or daily life",
            "These 'yellow flags' predict pain lasting longer. Mentioning them helps a clinician offer support beyond medication.",
            "Kendall et al., Guide to Assessing Psychosocial Yellow Flags in Acute Low Back Pain", sorted(yellow))

    if "distress" in nlp:
        add("support", "support", "Support is available",
            "Living with pain can be overwhelming. If you ever feel hopeless or unsafe, you can call or text 988 (Suicide & Crisis Lifeline) any time.",
            "988 Suicide & Crisis Lifeline", ["Distress described"])

    flags.sort(key=lambda flag: -LEVELS.index(flag.level))
    return [asdict(flag) for flag in flags]
