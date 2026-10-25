"""Symptoms, onset and trend read from the patient's own description.

The intake is now a spoken or typed description instead of a checkbox
questionnaire, so the red-flag rules need the same facts pulled from text.
PainBERT covers pain quality and a few associated findings; this module adds
the symptoms PainBERT has no label for (nausea, breathlessness, sweating, ...)
with plain patterns and a short negation window ("no fever", "I haven't
vomited"). Patterns are deliberately literal so every hit can be explained.
"""

import re

SYMPTOM_PATTERNS = {
    "nausea_vomiting": r"nause|vomit|throw(ing|n)? up|threw up|puk(e|ing)|sick to my stomach|feel(ing)? sick",
    "breathless": r"short(ness)? of breath|can'?t (catch my )?breath|cannot breathe|can'?t breathe|hard to breathe|trouble breathing|difficulty breathing|breathless|out of breath|winded",
    "fever": r"fever|feverish|chills|high temperature|temperature of (10[0-9]|3[89])",
    "sweating": r"sweat|clammy",
    "dizziness": r"dizz|lightheaded|light-headed|faint(ed|ing)?|passed out|blacked out|vertigo",
    "palpitations": r"palpitation|heart (is )?(racing|pounding|fluttering)|racing heart",
    "injury": r"\bfell\b|\bfall\b|fell (off|down|over)|tripped|slipped|crash|accident|collision|got hit|was hit|tackled|twisted|rolled (my|it)|sprain|injur|hurt it (playing|lifting)",
    "weakness": r"\bweak(ness)?\b|gave way|giving way|can'?t (lift|grip|hold)|dropping things|foot drop",
    "numbness": r"numb|tingl|pins and needles",
    "bladder_bowel": r"can'?t (pee|urinate)|wet myself|lost control of (my )?(bladder|bowel)|incontinen|numb(ness)? (in|around) (my )?(groin|saddle|private)",
    "blood": r"blood in (my )?(stool|poo|poop|urine|pee|vomit)|vomit(ing|ed)? blood|threw up blood|bloody (stool|poo|poop|vomit|urine|pee)"
             r"|(black|tarry) (stool|poo|poop)|(stool|poo|poop|pee|urine)s? (was|were|is|are|looked|looks|has been|have been|came out) (black|bloody|red|tarry)"
             r"|blood when i (wipe|poo|poop|pee)|coughing (up )?blood|peeing blood",
}
_SYMPTOMS = {k: re.compile(v) for k, v in SYMPTOM_PATTERNS.items()}
NEGATION = re.compile(r"\b(no|not|without|never|denies|deny|haven'?t|hasn'?t|didn'?t|don'?t|doesn'?t|does not|do not|did not|is not|isn'?t|wasn'?t|aren'?t|won'?t|nor)\b")

ONSET_PATTERNS = [
    ("Within the last hour", r"(just now|minutes ago|an hour ago|in the last hour|half an hour|30 minutes|suddenly just)"),
    ("Today", r"\b(today|this morning|this afternoon|this evening|tonight|few hours ago|couple (of )?hours)\b"),
    ("1–3 days ago", r"\b(yesterday|last night|(one|two|three|1|2|3|a couple of|couple|few) days? ago)\b"),
    ("4–7 days ago", r"\b((four|five|six|4|5|6) days ago|last week|a week ago|this week)\b"),
    ("1–4 weeks ago", r"\b((two|three|four|2|3|4|few|couple of) weeks?( ago)?|past (two|few|couple of) weeks)\b"),
    ("More than one month ago", r"\b(months?|years?|since (last|i was)|for ages|chronic|long time)\b"),
]
_ONSET = [(label, re.compile(p)) for label, p in ONSET_PATTERNS]

TREND_PATTERNS = {
    "It is getting worse": r"getting worse|worse and worse|worsening|more painful (each|every)|keeps getting worse",
    "It is getting better": r"getting better|improving|easing off|less painful now",
}
SUDDEN = re.compile(r"sudden(ly)?|out of nowhere|came on (all at once|fast)|worst (headache|pain) (of|in) my life|thunderclap")


def _negated(text: str, start: int) -> bool:
    # Look back to the start of the clause, at most six words.
    clause = re.split(r"[.;!?]|\bbut\b|\bhowever\b", text[:start])[-1]
    window = " ".join(clause.split()[-6:])
    return bool(NEGATION.search(window))


def symptoms_from_text(text: str) -> dict[str, str]:
    """Return {symptom: matched phrase} for non-negated mentions."""
    lower = (text or "").lower()
    found: dict[str, str] = {}
    for key, pattern in _SYMPTOMS.items():
        for match in pattern.finditer(lower):
            if not _negated(lower, match.start()):
                found[key] = match.group(0)
                break
    return found


def onset_from_text(text: str) -> str | None:
    lower = (text or "").lower()
    for label, pattern in _ONSET:
        match = pattern.search(lower)
        if match and not _negated(lower, match.start()):
            return label
    return None


def trend_from_text(text: str) -> str | None:
    lower = (text or "").lower()
    for label, pattern in TREND_PATTERNS.items():
        match = re.search(pattern, lower)
        if match and not _negated(lower, match.start()):
            return label
    return None


def sudden_onset(text: str) -> bool:
    return bool(SUDDEN.search((text or "").lower()))


# --------------------------------------------------------------------------
# PainBERT corroboration gate
# --------------------------------------------------------------------------
# PainBERT was trained on generated notes. On real descriptions it sometimes
# fires on unrelated words (scenario tests: "trauma" 0.83 for "moved to the
# lower right", "tingling" 0.72 for "fainted", "bladder_bowel" 0.38 for
# period cramps). The labels below change red-flag rules or self-care advice,
# so each one is kept only if the model is very sure, or a word that carries
# the meaning appears in the text and is not negated.
GATE_PROBABILITY = 0.9
CORROBORATION = {
    "trauma": r"fell|fall|trip|slip|accident|crash|\bhit\b|tackl|twist|rolled|sprain|\bpop|injur|lift|pull|strain|gym|bench|landing|landed|collision|kick|bump|knock|tore|tear",
    "bladder_bowel": r"pee|urin|bladder|bowel|toilet|incontinen|leak|wet myself|saddle|between my legs|groin.{0,20}numb|numb.{0,20}groin",
    "tingling": r"tingl|pins and needles|prickl|buzz|fizz|crawl|vibrat",
    "numbness": r"numb|no feeling|can'?t feel|dead|asleep|wooden|rubbery",
    "electric": r"electric|shock|zap|jolt|shoot|lightning|zing",
    "burning": r"burn|sear|scald|on fire|hot poker|sunburn|sting",
    "fever": r"fever|chill|temperature|sweat|shiver|hot and cold",
    "weakness": r"weak|gives? way|gave way|buckl|can'?t (grip|lift|hold)|dropping|drag|jelly",
    "swelling": r"swell|swollen|puff|bloat|\bred\b|redness|warm|inflam|bigger|lump",
}
_CORROBORATION = {k: re.compile(v) for k, v in CORROBORATION.items()}


def corroborate(labels: list[dict], text: str) -> tuple[list[dict], list[dict]]:
    """Split PainBERT labels into (kept, dropped) using the gate above."""
    lower = (text or "").lower()
    kept, dropped = [], []
    for label in labels:
        pattern = _CORROBORATION.get(label["key"])
        if pattern is None or label["probability"] >= GATE_PROBABILITY:
            kept.append(label)
            continue
        supported = any(not _negated(lower, m.start()) for m in pattern.finditer(lower))
        (kept if supported else dropped).append(label)
    return kept, dropped
