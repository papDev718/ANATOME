"""Label taxonomy for the ANATOME pain-language model (PainBERT).

Each label is a clinically recognised descriptor that a clinician would want
pulled out of a patient's free-text note. The sensory labels follow the
McGill Pain Questionnaire descriptor classes; the six labels flagged
``dn4=True`` are the patient-interview items of the DN4 neuropathic-pain
screening questionnaire (Bouhassira et al., Pain 2005), with "tingling" and
"pins and needles" merged into one label.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PainLabel:
    key: str
    name: str
    group: str
    definition: str
    dn4: bool = False


LABELS: list[PainLabel] = [
    # Sensory quality: neuropathic-type descriptors (DN4 interview items)
    PainLabel("burning", "Burning", "quality",
              "Burning, hot, scalding or searing sensation.", dn4=True),
    PainLabel("electric", "Electric / shooting", "quality",
              "Electric-shock, zapping, lightning-like or shooting jolts.", dn4=True),
    PainLabel("tingling", "Tingling / pins and needles", "quality",
              "Tingling, pins and needles, prickling, crawling or buzzing.", dn4=True),
    PainLabel("numbness", "Numbness", "quality",
              "Numbness, reduced or lost feeling, 'dead' or asleep sensation.", dn4=True),
    PainLabel("itching", "Itching", "quality",
              "Itching or itchy sensation in the painful area.", dn4=True),
    PainLabel("cold_pain", "Painful cold", "quality",
              "Pain that feels freezing/icy, or is triggered by cold.", dn4=True),
    # Sensory quality: nociceptive-type descriptors (McGill classes)
    PainLabel("sharp", "Sharp / stabbing", "quality",
              "Sharp, stabbing, knife-like, cutting or piercing pain."),
    PainLabel("throbbing", "Throbbing / pulsing", "quality",
              "Throbbing, pounding, pulsing or beating pain."),
    PainLabel("aching", "Dull / aching", "quality",
              "Dull, aching, sore, heavy or nagging pain."),
    PainLabel("pressure", "Pressure / cramping", "quality",
              "Pressure, squeezing, tightness, cramping or crushing pain."),
    # Spatial and temporal pattern
    PainLabel("radiating", "Radiating", "pattern",
              "Pain that spreads, travels or radiates to another area."),
    PainLabel("night_pain", "Night pain", "pattern",
              "Pain that is worse at night or wakes the patient up."),
    PainLabel("stiffness", "Stiffness", "pattern",
              "Stiffness, especially morning stiffness or difficulty loosening up."),
    # Associated findings
    PainLabel("weakness", "Weakness", "associated",
              "Muscle weakness, limb giving way, dropping things, foot drop."),
    PainLabel("swelling", "Swelling / redness", "associated",
              "Swelling, puffiness, redness or warmth at the site."),
    PainLabel("trauma", "Injury / trauma", "associated",
              "Pain that began with a fall, accident, impact, sports injury or a pop."),
    PainLabel("fever", "Fever / chills", "associated",
              "Fever, chills, night sweats or feeling feverish."),
    PainLabel("bladder_bowel", "Bladder / bowel change", "associated",
              "New bladder or bowel control problems or numbness in the saddle/groin area."),
    # Impact and psychosocial ("yellow flags")
    PainLabel("sleep_loss", "Sleep disruption", "impact",
              "Trouble falling or staying asleep because of the pain."),
    PainLabel("function_loss", "Functional limitation", "impact",
              "Pain stops or limits walking, work, school, sport, chores or self-care."),
    PainLabel("distress", "Emotional distress", "impact",
              "Worry, fear, low mood, frustration, hopelessness or not coping."),
]

LABEL_KEYS = [label.key for label in LABELS]
LABEL_BY_KEY = {label.key: label for label in LABELS}
DN4_KEYS = [label.key for label in LABELS if label.dn4]


# Everyday phrasings per label, drawn from the McGill Pain Questionnaire
# descriptor lists and common lay terms. The data generator asks for one of
# these (or its own paraphrase) so the model learns meanings, not label names.
PHRASINGS: dict[str, list[str]] = {
    "burning": ["burning", "hot", "scalding", "searing", "on fire", "like a hot poker", "like a bad sunburn", "stinging heat"],
    "electric": ["electric shocks", "zapping", "jolts", "shooting", "lightning bolts", "like touching a live wire", "sudden zings"],
    "tingling": ["pins and needles", "prickling", "buzzing", "fizzing", "crawling feeling", "vibrating", "like a limb waking up"],
    "numbness": ["numb", "no feeling", "can't feel it", "wooden", "like after a dentist injection", "rubbery", "half asleep"],
    "itching": ["itchy", "itch", "wants scratching", "prickly itch", "irritated skin that itches"],
    "cold_pain": ["icy", "freezing", "like ice water", "a cold burn", "frostbite-like", "aches when cold air hits it"],
    "sharp": ["sharp", "stabbing", "knife-like", "cutting", "piercing", "jabbing", "like a needle", "like a nail driven in"],
    "throbbing": ["throbbing", "pounding", "pulsing", "beating", "in time with my pulse", "like a drum", "hammering"],
    "aching": ["aching", "sore", "dull", "nagging", "heavy", "bruised feeling", "tender", "worn out"],
    "pressure": ["pressure", "squeezing", "tight", "cramping", "crushing", "spasm", "a knot", "vice-like", "clenched"],
    "radiating": ["spreads", "travels", "runs down", "shoots into", "moves up to", "goes all the way to", "radiates"],
    "night_pain": ["worse at night", "wakes me up", "worst at bedtime", "in the middle of the night", "can't lie on it at night"],
    "stiffness": ["stiff", "rigid", "hard to bend", "locked up", "needs time to loosen up", "creaky in the morning"],
    "weakness": ["weak", "gives way", "buckles", "can't grip", "dropping things", "foot drags", "legs like jelly"],
    "swelling": ["swollen", "puffy", "bloated", "red", "warm to touch", "inflamed", "bigger than the other side"],
    "trauma": ["fell", "car accident", "got hit", "twisted it", "sports injury", "heard a pop", "felt something go while lifting"],
    "fever": ["fever", "chills", "running a temperature", "hot and cold spells", "night sweats", "shivering", "feverish"],
    "bladder_bowel": ["can't control my bladder", "leaking urine", "trouble starting to pee", "bowel accident", "numb between my legs", "can't feel when I need the toilet"],
    "sleep_loss": ["can't sleep", "insomnia", "up all night", "sleep is wrecked", "only sleeping a few hours", "can't get comfortable in bed"],
    "function_loss": ["can't walk far", "missing work", "can't do chores", "had to stop sports", "can't climb stairs", "can't get dressed", "can't pick up my kid"],
    "distress": ["worried", "scared", "anxious", "depressed", "frustrated", "hopeless", "stressed out", "at the end of my rope"],
}
