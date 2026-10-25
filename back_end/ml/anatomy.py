"""ANATOME anatomical knowledge graph.

Turns the Z-Anatomy structure names in the 3D model (for example
"Acromial part of deltoid muscle.l") into clinical facts:

* side and body region,
* the ACR 2016 Widespread Pain Index region (Wolfe et al., Semin Arthritis
  Rheum 2016), used to score how widespread the pain map is,
* motor nerve and spinal root levels (standard textbook innervation,
  e.g. Moore's Clinically Oriented Anatomy), used to look for spots that
  share one nerve or one spinal segment.

Rules are ordered regexes: the first match wins, so specific names
(e.g. "short head of biceps femoris") must precede general ones.
"""

import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass

ROOT_ORDER = (
    [f"C{i}" for i in range(1, 9)] + [f"T{i}" for i in range(1, 13)]
    + [f"L{i}" for i in range(1, 6)] + [f"S{i}" for i in range(1, 6)]
)


def root_range(spec: str) -> list[str]:
    """'C5-C7' -> ['C5', 'C6', 'C7'];  'L5-S2' -> ['L5', 'S1', 'S2']."""
    if not spec:
        return []
    if "-" not in spec:
        return [spec]
    start, end = spec.split("-")
    return ROOT_ORDER[ROOT_ORDER.index(start):ROOT_ORDER.index(end) + 1]


# (pattern, nerve, roots). Cranial nerves have no spinal roots.
INNERVATION: list[tuple[str, str, str]] = [
    # Head: muscles of mastication, extra-ocular, facial expression, tongue
    (r"masset|temporalis muscle|pterygoid|anterior belly of digastric|mylohyoid", "Mandibular nerve (CN V3)", ""),
    (r"superior oblique|trochlea", "Trochlear nerve (CN IV)", ""),
    (r"lateral rectus", "Abducens nerve (CN VI)", ""),
    (r"rectus muscle|inferior oblique|levator palpebrae", "Oculomotor nerve (CN III)", ""),
    (r"posterior belly of digastric|stylohyoid|platysma|frontalis|occipitalis|temporoparietalis|orbicularis|zygomaticus"
     r"|levator labii|levator anguli|levator nasolabialis|depressor|risorius|mentalis|nasalis|procerus|corrugator|bucinator|buccinator",
     "Facial nerve (CN VII)", ""),
    (r"genioglossus|hyoglossus", "Hypoglossal nerve (CN XII)", ""),
    (r"stylopharyngeus", "Glossopharyngeal nerve (CN IX)", ""),
    (r"pharyngeal constrictor|palatopharyngeus|arytenoid|cricothyroid|epiglottic", "Vagus nerve (CN X)", ""),
    # Neck
    (r"geniohyoid|thyrohyoid", "C1 via hypoglossal nerve", "C1"),
    (r"sternohyoid|sternothyroid|omohyoid", "Ansa cervicalis", "C1-C3"),
    (r"sternocleidomastoid", "Accessory nerve (CN XI) + cervical plexus", "C2-C3"),
    (r"trapezius", "Accessory nerve (CN XI) + cervical plexus", "C3-C4"),
    (r"rectus posterior|obliquus (inferior|superior) capitis", "Suboccipital nerve", "C1"),
    (r"rectus (anterior|lateralis) capitis|longus capitis", "Cervical ventral rami", "C1-C3"),
    (r"longus colli", "Cervical ventral rami", "C2-C6"),
    (r"scalenus anterior", "Cervical ventral rami", "C4-C6"),
    (r"scalenus medius", "Cervical ventral rami", "C3-C8"),
    (r"scalenus posterior", "Cervical ventral rami", "C6-C8"),
    (r"levator scapulae", "Dorsal scapular nerve + cervical plexus", "C3-C5"),
    (r"splenius|semispinalis colli|multifidus colli|interspinales colli|longissimus (capitis|colli)|iliocostalis colli|spinalis (capitis|colli)",
     "Cervical dorsal rami", "C1-C8"),
    # Shoulder girdle
    (r"rhomboid", "Dorsal scapular nerve", "C4-C5"),
    (r"deltoid|teres minor", "Axillary nerve", "C5-C6"),
    (r"supraspinatus|infraspinatus", "Suprascapular nerve", "C5-C6"),
    (r"subscapularis", "Upper and lower subscapular nerves", "C5-C6"),
    (r"teres major", "Lower subscapular nerve", "C5-C6"),
    (r"latissimus dorsi", "Thoracodorsal nerve", "C6-C8"),
    (r"serratus anterior", "Long thoracic nerve", "C5-C7"),
    (r"subclavius", "Nerve to subclavius", "C5-C6"),
    (r"clavicular head of pectoralis major", "Lateral pectoral nerve", "C5-C7"),
    (r"pectoralis major", "Medial and lateral pectoral nerves", "C7-T1"),
    (r"pectoralis minor", "Medial pectoral nerve", "C8-T1"),
    # Arm
    (r"coracobrachialis", "Musculocutaneous nerve", "C5-C7"),
    (r"biceps brachii|brachialis muscle", "Musculocutaneous nerve", "C5-C6"),
    (r"triceps brachii|anconeus", "Radial nerve", "C6-C8"),
    (r"brachioradialis", "Radial nerve", "C5-C6"),
    (r"extensor carpi radialis longus", "Radial nerve", "C6-C7"),
    (r"extensor carpi radialis brevis", "Deep branch of radial nerve", "C7-C8"),
    (r"supinator", "Posterior interosseous nerve", "C5-C6"),
    (r"extensor digitorum(?! (longus|brevis))|extensor (digiti minimi|indicis|pollicis)|extensor carpi ulnaris|abductor pollicis longus",
     "Posterior interosseous nerve", "C7-C8"),
    # Forearm flexors and hand
    (r"pronator teres|flexor carpi radialis", "Median nerve", "C6-C7"),
    (r"palmaris longus", "Median nerve", "C7-C8"),
    (r"flexor digitorum superficialis", "Median nerve", "C8-T1"),
    (r"flexor pollicis longus|pronator quadratus", "Anterior interosseous nerve", "C7-C8"),
    (r"flexor digitorum profundus", "Anterior interosseous + ulnar nerves", "C8-T1"),
    (r"flexor carpi ulnaris", "Ulnar nerve", "C7-T1"),
    (r"abductor pollicis brevis|opponens pollicis|superficial head of flexor pollicis brevis", "Recurrent branch of median nerve", "C8-T1"),
    (r"lumbrical muscles of hand", "Median and ulnar nerves", "C8-T1"),
    (r"deep head of flexor pollicis brevis|adductor pollicis|digiti minimi (muscle )?of hand|interossei muscles of hand|palmar interossei", "Deep branch of ulnar nerve", "C8-T1"),
    # Trunk
    (r"diaphragm(?!atic)", "Phrenic nerve", "C3-C5"),
    (r"serratus posterior superior", "Intercostal nerves", "T2-T5"),
    (r"serratus posterior inferior", "Intercostal nerves", "T9-T12"),
    (r"intercostal|transversus thoracis|levatores", "Intercostal nerves", "T1-T11"),
    (r"semispinalis thoracis|multifidus thoracis|interspinales thoracis|longissimus thoracis|iliocostalis thoracis|spinalis thoracis|rotatores",
     "Thoracic dorsal rami", "T1-T12"),
    (r"rectus abdominis|external abdominal oblique", "Thoraco-abdominal nerves", "T7-T12"),
    (r"internal abdominal oblique|transversus abdominis", "Thoraco-abdominal, iliohypogastric and ilioinguinal nerves", "T7-L1"),
    (r"pyramidalis", "Subcostal nerve", "T12"),
    (r"quadratus lumborum", "Subcostal nerve + L1-L4 ventral rami", "T12-L4"),
    (r"multifidus lumborum|interspinales lumborum|iliocostalis lumborum|intertransversarii", "Lumbar dorsal rami", "L1-L5"),
    (r"psoas major", "Lumbar plexus", "L1-L3"),
    (r"iliacus", "Femoral nerve", "L2-L3"),
    # Pelvic floor
    (r"pubococcygeus|iliococcygeus|pubo-analis|levator ani", "Nerve to levator ani + pudendal nerve", "S3-S4"),
    (r"coccygeus", "S4-S5 ventral rami", "S4-S5"),
    (r"external anal sphincter", "Inferior rectal (pudendal) nerve", "S2-S4"),
    # Hip and gluteal
    (r"gluteus maximus", "Inferior gluteal nerve", "L5-S2"),
    (r"gluteus medius|gluteus minimus|tensor fasciae latae", "Superior gluteal nerve", "L4-S1"),
    (r"piriformis", "Nerve to piriformis", "S1-S2"),
    (r"obturator internus|superior gemellus", "Nerve to obturator internus", "L5-S2"),
    (r"quadratus femoris|inferior gemellus", "Nerve to quadratus femoris", "L4-S1"),
    (r"obturator externus", "Obturator nerve", "L3-L4"),
    # Thigh
    (r"sartorius|rectus femoris|vastus", "Femoral nerve", "L2-L4"),
    (r"pectineus", "Femoral nerve", "L2-L3"),
    (r"adductor (longus|brevis|minimus)|gracilis", "Obturator nerve", "L2-L4"),
    (r"adductor magnus", "Obturator nerve + tibial division of sciatic", "L2-L4"),
    (r"short head of biceps femoris", "Common fibular division of sciatic nerve", "L5-S2"),
    (r"semitendinosus|semimembranosus|biceps femoris", "Tibial division of sciatic nerve", "L5-S2"),
    # Leg and foot
    (r"tibialis anterior", "Deep fibular nerve", "L4-L5"),
    (r"extensor hallucis|extensor digitorum (longus|brevis)|fibularis tertius", "Deep fibular nerve", "L5-S1"),
    (r"fibularis (longus|brevis)", "Superficial fibular nerve", "L5-S2"),
    (r"gastrocnemius|soleus|plantaris muscle|calcaneal tendon", "Tibial nerve", "S1-S2"),
    (r"popliteus", "Tibial nerve", "L4-S1"),
    (r"tibialis posterior", "Tibial nerve", "L4-L5"),
    (r"flexor digitorum longus|flexor hallucis longus", "Tibial nerve", "S2-S3"),
    (r"abductor hallucis|flexor digitorum brevis|flexor hallucis brevis", "Medial plantar nerve", "S1-S2"),
    (r"digiti minimi.*foot|interossei muscles of foot|lumbrical muscles of foot|quadratus plantae|adductor hallucis|plantar interossei", "Lateral plantar nerve", "S2-S3"),
]
_INNERVATION = [(re.compile(p), nerve, roots) for p, nerve, roots in INNERVATION]

# (pattern, body region, display region). Matched against the full name.
REGIONS: list[tuple[str, str]] = [
    (r"masset|temporal|pterygoid|buccinator|bucinator|zygomatic|orbicularis oris|labii|anguli|mentalis|risorius|nasalis|nasolabialis|procerus|septi nasi|digastric|mylohyoid|geniohyoid|genioglossus|hyoglossus|stylohyoid|tmj", "face_jaw"),
    (r"temporoparietalis|frontalis|occipitalis|epicranial|corrugator|orbicul|palpebr|rectus muscle|(superior|inferior) oblique muscle|tarsus|trochlea|common tendinous ring", "head"),
    (r"platysma|sternocleidomastoid|scalen|longus (colli|capitis)|capitis|colli|cervical|hyoid|thyro|crico|aryt|pharyn|stylopharyn|levator scapulae|descending part of trapezius", "neck"),
    (r"deltoid|supraspinatus|infraspinatus|subscapularis|teres (major|minor)|subacromial|acromial bursa|coracobrachial bursa|rhomboid|transverse part of trapezius|bursa of trapezius|subclavius|clavipectoral", "shoulder"),
    (r"pectoral|serratus anterior|intercostal|transversus thoracis|diaphragm|sternocostal|clavicular head", "chest"),
    (r"rectus abdominis|abdominal oblique|transversus abdominis|pyramidalis|linea alba|investing abdominal|transversalis|inguinal ligament|abdominal part", "abdomen"),
    (r"latissimus|thoracis|ascending part of trapezius|serratus posterior|levatores|rotatores|costarum", "back"),
    (r"lumbor|thoracolumbar|quadratus lumborum|intertransversarii|psoas|iliopsoas", "back"),
    (r"biceps brachii|brachialis|brachial fascia|coracobrachialis|triceps|anconeus|intermuscular septum of arm|bicipitoradial|brachioradialis|pronator teres|supinator|common flexor", "arm"),
    (r"of hand|pollicis|indicis|palmar|lumbrical muscles of hand|interossei muscles of hand|wrist|digiti minimi(?!.*foot)|metacarpal|carpi|digitorum superficialis|digitorum profundus|palmaris|pronator quadratus|antebrachial|extensor digitorum(?! (longus|brevis))|digits of hand", "hand_wrist"),
    (r"gluteus|gluteal|piriformis|gemellus|obturator|quadratus femoris|tensor fasciae|trochanteric|iliacus|pectineus|iliopectineal|coccygeus|levator ani|pubococcygeus|iliococcygeus|pubo-analis|anal sphincter|sciatic bursa", "hip_pelvis"),
    (r"patell|popliteal|popliteus|infrapatellar|anserine|tuberosity of tibia|suprapatellar|subtendinous bursa of sartorius", "knee"),
    (r"rectus femoris|vastus|sartorius|adductor (longus|brevis|magnus|minimus)|gracilis|biceps femoris|semitendinosus|semimembranosus|fascia lata|iliotibial|femoral intermuscular", "leg"),
    (r"of foot|plantar(?!is)|hallucis|flexor digitorum brevis|calcaneal|malleolus|ankle|fibular retinacul|metatarsal|quadratus plantae|extensor digitorum (longus|brevis)|tendon of extensor digitorum longus", "ankle_foot"),
    (r"gastrocnemius|soleus|plantaris|tibialis|fibularis|digitorum longus|crural|of leg", "leg"),
]
_REGIONS = [(re.compile(p), region) for p, region in REGIONS]

REGION_NAMES = {
    "head": "Head", "face_jaw": "Face & jaw", "neck": "Neck", "shoulder": "Shoulder",
    "arm": "Arm & elbow", "hand_wrist": "Forearm, wrist & hand", "chest": "Chest wall",
    "abdomen": "Abdominal wall", "back": "Back", "hip_pelvis": "Hip & pelvis",
    "leg": "Leg", "knee": "Knee", "ankle_foot": "Ankle & foot",
}

# The 19 Widespread Pain Index areas and the 5 body regions used by the
# ACR 2016 generalized-pain criterion.
WPI_AREAS = {
    "jaw_l": ("Left jaw", "left_upper"), "jaw_r": ("Right jaw", "right_upper"),
    "shoulder_l": ("Left shoulder girdle", "left_upper"), "shoulder_r": ("Right shoulder girdle", "right_upper"),
    "upper_arm_l": ("Left upper arm", "left_upper"), "upper_arm_r": ("Right upper arm", "right_upper"),
    "lower_arm_l": ("Left lower arm", "left_upper"), "lower_arm_r": ("Right lower arm", "right_upper"),
    "hip_l": ("Left hip / buttock", "left_lower"), "hip_r": ("Right hip / buttock", "right_lower"),
    "upper_leg_l": ("Left upper leg", "left_lower"), "upper_leg_r": ("Right upper leg", "right_lower"),
    "lower_leg_l": ("Left lower leg", "left_lower"), "lower_leg_r": ("Right lower leg", "right_lower"),
    "neck": ("Neck", "axial"), "upper_back": ("Upper back", "axial"), "lower_back": ("Lower back", "axial"),
    "chest": ("Chest", "axial"), "abdomen": ("Abdomen", "axial"),
}

STRUCTURE_TYPES = [
    (r"bursa", "bursa"), (r"tendon|sheath", "tendon"), (r"ligament|retinacul|linea alba|iliotibial|arch", "ligament"),
    (r"fascia(?!e latae)|aponeurosis|septum", "fascia"),
]


@dataclass
class StructureInfo:
    name: str
    base_name: str
    side: str
    structure_type: str
    region: str
    region_name: str
    wpi_area: str | None
    nerve: str | None
    roots: list[str]


# Labels in the Z-Anatomy GLB that do not match the mesh's position. The
# mesh named "Descending part of trapezius" spans y 1.12-1.41 m (mid back)
# and "Ascending part" spans 1.42-1.57 m (neck), the reverse of anatomy:
# descending (upper) fibres run from the skull, ascending (lower) fibres
# from T4-T12. Checked with ml/body_map.py; front_end/src/utils/anatomyName.js
# applies the same fix for display.
MODEL_LABEL_FIXES = {
    "Descending part of trapezius muscle": "Ascending part of trapezius muscle",
    "Ascending part of trapezius muscle": "Descending part of trapezius muscle",
}


def corrected_name(name: str) -> str:
    match = re.match(r"^(.*?)([ .](?:l|r))?$", name.strip(), re.IGNORECASE)
    base, suffix = match.group(1), match.group(2) or ""
    return MODEL_LABEL_FIXES.get(base, base) + suffix


def split_side(name: str) -> tuple[str, str]:
    clean = corrected_name(name).replace("_", " ").strip()
    match = re.search(r"[ .](l|r)$", clean, re.IGNORECASE)
    if match:
        return clean[:match.start()].strip(" ()"), "left" if match.group(1).lower() == "l" else "right"
    return clean.strip(" ()"), "midline"


def _wpi_area(base: str, region: str, side: str) -> str | None:
    s = "l" if side == "left" else "r" if side == "right" else None
    if region == "face_jaw" and re.search(r"masset|temporalis|pterygoid|digastric|mylohyoid", base):
        return f"jaw_{s}" if s else None
    if region == "shoulder":
        return f"shoulder_{s}" if s else "upper_back"
    if region == "arm":
        return f"upper_arm_{s}" if s and not re.search(r"brachioradialis|pronator|supinator|common flexor|bicipitoradial", base) else (f"lower_arm_{s}" if s else None)
    if region == "hand_wrist":
        return f"lower_arm_{s}" if s else None
    if region == "hip_pelvis":
        return f"hip_{s}" if s else "lower_back"
    if region in ("leg", "knee"):
        if re.search(r"gastrocnemius|soleus|plantaris|tibialis|fibularis|digitorum longus|hallucis longus|crural|of leg|popliteus", base):
            return f"lower_leg_{s}" if s else None
        return f"upper_leg_{s}" if s else None
    if region == "ankle_foot":
        return f"lower_leg_{s}" if s else None
    if region == "neck":
        return "neck"
    if region == "chest":
        return "chest"
    if region == "abdomen":
        return "abdomen"
    if region == "back":
        return "lower_back" if re.search(r"lumbor|thoracolumbar|quadratus lumborum|intertransversarii|psoas|serratus posterior inferior", base) else "upper_back"
    return None


def describe_structure(name: str) -> StructureInfo:
    base, side = split_side(name)
    lower = base.lower()
    region = next((r for pattern, r in _REGIONS if pattern.search(lower)), "back" if "spin" in lower else "leg")
    structure_type = next((t for pattern, t in STRUCTURE_TYPES if re.search(pattern, lower)), "muscle")
    nerve, roots = None, []
    if structure_type in ("muscle", "tendon") or "calcaneal" in lower:
        match = next(((n, r) for pattern, n, r in _INNERVATION if pattern.search(lower)), None)
        if match:
            nerve, roots = match[0], root_range(match[1])
    return StructureInfo(
        name=name, base_name=base, side=side, structure_type=structure_type,
        region=region, region_name=REGION_NAMES[region],
        wpi_area=_wpi_area(lower, region, side), nerve=nerve, roots=roots,
    )


def analyse_pain_map(spots: list[dict]) -> dict:
    """Pattern analysis over all marked spots.

    ``spots`` items need ``regionName`` and ``severity``.
    """
    infos = []
    for spot in spots:
        info = describe_structure(spot.get("structureName") or spot.get("regionName") or "")
        # A structure the localizer only guessed at (body-area spot, low
        # confidence) still counts for region and WPI, but not for nerve
        # and spinal-segment patterns.
        if spot.get("inferredStructure"):
            info.nerve, info.roots = None, []
        # A body-area spot's region is the area the patient chose ("Knee"),
        # even when the nearest structure belongs to the next region.
        if spot.get("areaRegion") in REGION_NAMES and spot["areaRegion"] != info.region:
            info.region, info.region_name = spot["areaRegion"], REGION_NAMES[spot["areaRegion"]]
            info.wpi_area = _wpi_area(info.base_name.lower(), info.region, info.side)
        infos.append((info, float(spot.get("severity") or 5)))

    # Widespread Pain Index (0-19) and the generalized-pain body regions
    wpi = sorted({i.wpi_area for i, _ in infos if i.wpi_area})
    body_regions = {WPI_AREAS[a][1] for a in wpi}
    wpi_detail = [{"key": a, "label": WPI_AREAS[a][0], "group": WPI_AREAS[a][1]} for a in wpi]

    # Distribution descriptors
    sides = Counter(i.side for i, _ in infos)
    bilateral_regions = sorted({
        i.region for i, _ in infos if i.side in ("left", "right")
        and any(j.region == i.region and j.side not in (i.side, "midline") for j, _ in infos)
    })

    # Spinal-segment convergence: which root is shared by the most distinct
    # innervated structures, weighted by reported severity.
    innervated = [(i, sev) for i, sev in infos if i.roots]
    root_weight: dict[str, float] = defaultdict(float)
    root_members: dict[str, set[str]] = defaultdict(set)
    for info, severity in innervated:
        for root in info.roots:
            root_weight[root] += severity / 10 / len(info.roots) ** 0.5
            root_members[root].add(info.base_name)
    roots_ranked = sorted(root_weight, key=lambda r: (-len(root_members[r]), -root_weight[r]))
    segment = None
    distinct_nerves = {i.nerve for i, _ in innervated}
    if roots_ranked and len(innervated) >= 2:
        top = roots_ranked[0]
        coverage = len(root_members[top]) / len({i.base_name for i, _ in innervated})
        if len(root_members[top]) >= 2 and coverage >= 0.75:
            segment = {
                "root": top,
                "coverage": round(coverage, 2),
                "structures": sorted(root_members[top]),
                "distinct_nerves": len(distinct_nerves),
                "note": (
                    f"{len(root_members[top])} of the marked muscles share the {top} spinal segment"
                    + (f" while being supplied by {len(distinct_nerves)} different peripheral nerves" if len(distinct_nerves) > 1 else "")
                    + ". A clinician may want to consider a segmental (nerve-root) source alongside local causes."
                ),
            }
    nerve_counts = Counter(i.nerve for i, _ in innervated)
    peripheral = None
    if nerve_counts:
        nerve, count = nerve_counts.most_common(1)[0]
        if count >= 2 and count / len(innervated) >= 0.75:
            peripheral = {
                "nerve": nerve, "count": count,
                "note": f"{count} marked muscles are supplied by the {nerve}. Pain limited to one nerve's territory is worth mentioning to a clinician.",
            }

    root_histogram = [
        {"root": r, "weight": round(root_weight[r], 3), "structures": len(root_members[r])}
        for r in ROOT_ORDER if r in root_weight
    ]

    return {
        "structures": [asdict(i) | {"severity": s} for i, s in infos],
        "wpi": {
            "score": len(wpi),
            "max": 19,
            "areas": wpi_detail,
            "regions_involved": sorted(body_regions),
            "generalized_pattern": len(body_regions & {"left_upper", "right_upper", "left_lower", "right_lower", "axial"}) >= 4,
        },
        "distribution": {
            "left": sides.get("left", 0), "right": sides.get("right", 0), "midline": sides.get("midline", 0),
            "bilateral_regions": [REGION_NAMES[r] for r in bilateral_regions],
            "regions": sorted({i.region_name for i, _ in infos}),
        },
        "segment_pattern": segment,
        "peripheral_nerve_pattern": peripheral,
        "root_histogram": root_histogram,
    }
