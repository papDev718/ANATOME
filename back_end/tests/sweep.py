"""Systematic sweeps on top of the hand-written scenarios.

1. Localizer sweep: a simulated tap on every visible structure in the model
   (outward from the body), checking which area the tap lands in and whether
   the intended structure is ranked first / in the top 3.
2. Phrase battery: symptom, negation, onset and blood phrasings.
3. Random patients: 600 random combinations of area, severity, pain type and
   symptom phrases, checked against safety invariants that must always hold.

    venv/bin/python -m tests.sweep
"""

import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from care_guide import select_tips  # noqa: E402
from ml.body_map import SIMPLE_AREAS, area_at, body_map, localize  # noqa: E402
from ml.inference import analyze_intake  # noqa: E402
from ml.text_signals import onset_from_text, symptoms_from_text  # noqa: E402
from tests.scenarios import SHEET, simulate_tap  # noqa: E402


def localizer_sweep():
    data = body_map()
    per_area = defaultdict(lambda: {"n": 0, "landed": 0, "top1": 0, "top3": 0, "occluded": 0})
    misses = []
    for s in data["structures"]:
        if SHEET.search(s["name"]):
            continue
        point, hit = simulate_tap(s["name"], None)
        stats = per_area[s["area"]]
        stats["n"] += 1
        if hit != s["name"]:
            # Something else is on top of it from the outside: a patient
            # cannot tap this structure directly from this side.
            stats["occluded"] += 1
        area, side = area_at(hit or s["name"], point)
        stats["landed"] += area == s["area"]
        names = [c["name"] for c in localize(area, side, point)["candidates"][:3]]
        stats["top1"] += bool(names) and names[0] == s["name"]
        stats["top3"] += s["name"] in names
        if s["name"] not in names and hit == s["name"]:
            misses.append((s["name"], area, names))
    total = {k: sum(v[k] for v in per_area.values()) for k in ("n", "landed", "top1", "top3", "occluded")}
    return dict(per_area), total, misses


PHRASES = [
    # (text, must contain, must not contain)
    ("I threw up three times", {"nausea_vomiting"}, set()),
    ("no vomiting at all", set(), {"nausea_vomiting"}),
    ("I haven't thrown up but I feel sick", {"nausea_vomiting"}, set()),
    ("I'm not short of breath", set(), {"breathless"}),
    ("I can't catch my breath when I walk", {"breathless"}, set()),
    ("I've had chills and a fever", {"fever"}, set()),
    ("no fever or chills", set(), {"fever"}),
    ("never had a fever", set(), {"fever"}),
    ("I'm sweating a lot and clammy", {"sweating"}, set()),
    ("I fainted in class", {"dizziness"}, set()),
    ("I feel lightheaded when I stand", {"dizziness"}, set()),
    ("my heart is racing", {"palpitations"}, set()),
    ("I fell off my bike", {"injury"}, set()),
    ("I didn't fall or hit anything", set(), {"injury"}),
    ("my leg feels weak and gave way", {"weakness"}, set()),
    ("my foot is numb", {"numbness"}, set()),
    ("pins and needles in my fingers", {"numbness"}, set()),
    ("I can't pee and my groin is numb", {"bladder_bowel", "numbness"}, set()),
    ("there was blood in my stool", {"blood"}, set()),
    ("my poo was black today", {"blood"}, set()),
    ("I vomited blood", {"blood", "nausea_vomiting"}, set()),
    ("no blood in my urine", set(), {"blood"}),
    ("stool looked normal, not black", set(), {"blood"}),
    ("I'm not dizzy but my head hurts", set(), {"dizziness"}),
    ("it doesn't make me sweat", set(), {"sweating"}),
    ("no swelling, no numbness, no weakness", set(), {"numbness", "weakness"}),
]

ONSETS = [
    ("it started 20 minutes ago", "Within the last hour"),
    ("since this morning", "Today"),
    ("since yesterday", "1–3 days ago"),
    ("two days ago", "1–3 days ago"),
    ("about a week ago", "4–7 days ago"),
    ("for three weeks", "1–4 weeks ago"),
    ("for months now", "More than one month ago"),
    ("for years", "More than one month ago"),
]


def phrase_battery():
    failures = []
    for text, must, must_not in PHRASES:
        found = set(symptoms_from_text(text))
        if not must <= found or found & must_not:
            failures.append({"text": text, "found": sorted(found), "expected": sorted(must), "forbidden": sorted(must_not)})
    for text, expected in ONSETS:
        got = onset_from_text(text)
        if got != expected:
            failures.append({"text": text, "onset": got, "expected": expected})
    return len(PHRASES) + len(ONSETS), failures


AREA_TARGETS = {
    "head": "Frontalis muscle.l", "face_jaw": "Superficial part of masseter.r", "neck": "Splenius capitis muscle.r",
    "shoulder": "Acromial part of deltoid muscle.l", "chest": "Sternocostal head of pectoralis major muscle.l",
    "abdomen": "Rectus abdominis muscle.r", "upper_back": "Rhomboid major muscle.l", "lower_back": "Multifidus lumborum muscle.l",
    "upper_arm": "Long head of biceps brachii.r", "forearm_hand": "Extensor carpi radialis brevis.l", "hip": "Gluteus medius muscle.l",
    "thigh": "Vastus lateralis muscle.r", "knee": "Subcutaneous prepatellar bursa.l", "lower_leg": "Medial head of gastrocnemius.l",
    "ankle_foot": "Calcaneal tendon.r",
}
SYMPTOM_SNIPPETS = ["", "I threw up.", "I have a fever.", "I'm short of breath.", "I'm sweating a lot.", "I fell yesterday.",
                    "My leg feels weak.", "No fever, no vomiting.", "It's swollen and warm.", "I feel dizzy.",
                    "There was blood in my stool.", "Pins and needles down my arm.", "I can't sleep and feel hopeless."]
PAIN_TYPES = ["Sharp", "Dull", "Aching", "Burning", "Throbbing", "Shooting", "Cramping", "Pressure", "Tingling", "Numb"]
ONSET_CHOICES = ["Within the last hour", "Today", "1–3 days ago", "4–7 days ago", "1–4 weeks ago", "More than one month ago"]
DOSE = re.compile(r"\d+\s?(mg|ml|tablet|pill)", re.I)


def random_patients(n=600, seed=11):
    rng = random.Random(seed)
    violations = []
    level_counts = defaultdict(int)
    for i in range(n):
        areas = rng.sample(sorted(AREA_TARGETS), rng.choice([1, 1, 1, 2, 3]))
        snippets = rng.sample(SYMPTOM_SNIPPETS, rng.choice([1, 1, 2]))
        text = f"My {SIMPLE_AREAS[areas[0]][0].lower()} hurts. " + " ".join(snippets)
        regions = {}
        for j, area in enumerate(areas):
            point, hit = simulate_tap(AREA_TARGETS[area], None)
            key, side = area_at(hit or AREA_TARGETS[area], point)
            regions[f"s{j}"] = {
                "mode": "area", "areaKey": key, "areaLabel": SIMPLE_AREAS[key][0], "regionName": SIMPLE_AREAS[key][0], "side": side,
                "severity": rng.randint(1, 10), "painType": rng.choice(PAIN_TYPES), "frequency": "Constant",
                "onset": rng.choice(ONSET_CHOICES), "notes": "", "clickPosition": " ".join(map(str, point)),
            }
        payload = {"age": rng.randint(5, 95), "questionnaire": {"patient_description": text}, "pain_regions": regions}
        analysis = analyze_intake(payload)
        selection = select_tips(analysis, text)
        level = (analysis.get("care_level") or {}).get("level")
        level_counts[level] += 1
        flags = {f["id"] for f in analysis["red_flags"]}
        severities = [r["severity"] for r in regions.values()]
        problems = []
        if level == "emergency" and selection["tips"]:
            problems.append("self-care offered in an emergency")
        if "chest" in areas and {"I'm short of breath.", "I'm sweating a lot."} & set(snippets) and level != "emergency":
            problems.append("chest pain + breathlessness/sweating not an emergency")
        if "There was blood in my stool." in snippets and level != "emergency":
            problems.append("blood in stool not an emergency")
        if "No fever, no vomiting." in snippets and len(snippets) == 1 and ({"hot_joint", "spinal_infection"} & flags):
            problems.append("negated fever triggered an infection flag")
        if max(severities) >= 7 and level == "routine":
            problems.append("severe pain (>=7) marked routine")
        if "abdomen" in areas and any(t == "nerve_positions" for t in selection["tips"]) and not ({"Burning", "Shooting", "Tingling", "Numb"} & {r["painType"] for r in regions.values()} or "Pins and needles down my arm." in snippets):
            problems.append("nerve tips without any nerve-type descriptor")
        if any(DOSE.search(t) for t in selection["tips"]):
            problems.append("dose in tips")
        if level is None:
            problems.append("no care level")
        if problems:
            violations.append({"i": i, "text": text, "areas": areas, "severities": severities, "level": level, "flags": sorted(flags), "problems": problems})
    return n, dict(level_counts), violations


if __name__ == "__main__":
    per_area, total, misses = localizer_sweep()
    print("LOCALIZER SWEEP (tap on every visible structure)")
    print(f"{'area':<14}{'n':>5}{'landed':>9}{'top1':>7}{'top3':>7}{'covered':>9}")
    for area, v in sorted(per_area.items()):
        print(f"{area:<14}{v['n']:>5}{v['landed'] / v['n']:>9.0%}{v['top1'] / v['n']:>7.0%}{v['top3'] / v['n']:>7.0%}{v['occluded'] / v['n']:>9.0%}")
    t = total
    print(f"{'ALL':<14}{t['n']:>5}{t['landed'] / t['n']:>9.0%}{t['top1'] / t['n']:>7.0%}{t['top3'] / t['n']:>7.0%}{t['occluded'] / t['n']:>9.0%}")
    reachable = t["n"] - t["occluded"]
    print(f"directly tappable structures: {reachable}; of those, intended structure in top 3: {reachable - len(misses)}/{reachable}")
    for m in misses[:15]:
        print("   miss:", m)

    n, failures = phrase_battery()
    print(f"\nPHRASE BATTERY: {n - len(failures)}/{n} pass")
    for f in failures:
        print("   ", f)

    n, levels, violations = random_patients()
    print(f"\nRANDOM PATIENTS: {n - len(violations)}/{n} satisfy every invariant; care levels {levels}")
    for v in violations[:15]:
        print("   ", json.dumps(v))
    Path(__file__).with_name("sweep_results.json").write_text(json.dumps(
        {"localizer": {"per_area": per_area, "total": total, "misses": misses}, "phrase_failures": failures,
         "random": {"n": n, "levels": levels, "violations": violations}}, indent=1, default=str))
