"""Simple body areas and the structure localizer.

Patients think in body areas ("my stomach", "my lower back"), not in
muscle names. The 3D model's "Body areas" layer groups the 673 Z-Anatomy
structures into the everyday areas below. When a patient marks a spot in an
area, ``localize`` works out which muscles and connective tissues sit under
that spot so the clinician report can still name them.

How the localizer scores each candidate structure in the marked area:

* geometry: distance from the clicked 3D point to the nearest sampled
  surface vertex of the structure (from the same GLB the browser renders),
  turned into a weight with a Gaussian kernel;
* tissue prior: the patient's pain words shift weight between muscle and
  connective tissue (cramping/aching after exertion leans muscle; swelling,
  a twist or a pop leans ligament/tendon/bursa).

It is a transparent scoring rule, not a trained classifier: there is no
labelled data that maps a patient's tap to the injured structure. Its output
is a ranked list of candidates for a clinician to examine, never a finding.
``tests/test_scenarios.py`` checks it against hand-written cases.
"""

import json
import math
import re
import struct
from functools import lru_cache
from pathlib import Path

import numpy as np

from .anatomy import describe_structure

ARTIFACT = Path(__file__).resolve().parent / "artifacts" / "body_map.json"
GLB = Path(__file__).resolve().parents[2] / "front_end" / "public" / "models" / "zanatomy_split.glb"
FRONT_END_MAP = Path(__file__).resolve().parents[2] / "front_end" / "src" / "data" / "bodyAreas.json"

# key -> (label, sided, knowledge-graph region used by the triage/red-flag models)
SIMPLE_AREAS = {
    "head": ("Head", False, "head"),
    "face_jaw": ("Face & jaw", False, "face_jaw"),
    "neck": ("Neck", False, "neck"),
    "shoulder": ("Shoulder", True, "shoulder"),
    "chest": ("Chest", False, "chest"),
    "abdomen": ("Stomach / belly", False, "abdomen"),
    "upper_back": ("Upper back", False, "back"),
    "lower_back": ("Lower back", False, "back"),
    "upper_arm": ("Upper arm & elbow", True, "arm"),
    "forearm_hand": ("Forearm, wrist & hand", True, "hand_wrist"),
    "hip": ("Hip, buttock & groin", True, "hip_pelvis"),
    "thigh": ("Thigh", True, "leg"),
    "knee": ("Knee", True, "knee"),
    "lower_leg": ("Calf & shin", True, "leg"),
    "ankle_foot": ("Ankle & foot", True, "ankle_foot"),
}

# What each area can hurt from besides the muscles and connective tissue on
# the model. Shown so a "stomach" spot is not read as purely muscular.
AREA_CAVEATS = {
    "abdomen": "Belly pain often comes from organs inside the abdomen (stomach, bowel, appendix, gallbladder, bladder), which this muscle model does not show. The abdominal-wall structures below are only the musculoskeletal possibilities.",
    "chest": "Chest pain can come from the heart, lungs or oesophagus, which this model does not show. The chest-wall structures below are only the musculoskeletal possibilities.",
    "head": "Most headaches do not come from a single muscle. The structures below are the scalp and face muscles near the marked spot.",
    "lower_back": "Low back pain can also come from the spine's discs and joints or, less often, the kidneys, which this model does not show.",
}


# Long structures cross area borders (latissimus dorsi covers the lower back,
# the quadriceps tendon covers the knee, tensor fasciae latae runs down the
# outer thigh). For trunk and leg structures the area of a tap is therefore
# decided by the tap's height, not by the mesh's name. Heights are metres in
# the GLB (feet at 0, crown at 1.71), read off the per-area extents.
LEG_AREAS = ("hip", "thigh", "knee", "lower_leg", "ankle_foot")
# Knee runs up to the top of the suprapatellar bursa; ankle up to the mid
# Achilles tendon, which patients call the back of the heel or ankle.
LEG_BANDS = [(0.16, "ankle_foot"), (0.36, "lower_leg"), (0.56, "knee"), (0.80, "thigh"), (99.0, "hip")]
BACK_AREAS = ("upper_back", "lower_back")
LOW_BACK_TOP = 1.15  # top of quadratus lumborum, about T12-L1


def simple_area(name: str) -> tuple[str, str]:
    """Structure name -> (default area key, side)."""
    info = describe_structure(name)
    region, wpi = info.region, info.wpi_area or ""
    if region == "shoulder" and re.search(r"rhomboid|transverse part of trapezius|bursa of trapezius", info.base_name, re.I):
        # Between the shoulder blades: patients call this the upper back.
        return "upper_back", info.side
    if region == "back":
        key = "lower_back" if wpi == "lower_back" else "upper_back"
    elif region == "arm":
        key = "forearm_hand" if wpi.startswith("lower_arm") else "upper_arm"
    elif region == "hand_wrist":
        key = "forearm_hand"
    elif region == "hip_pelvis":
        key = "hip"
    elif region == "leg":
        key = "lower_leg" if wpi.startswith("lower_leg") else "thigh"
    else:
        key = region
    return key, info.side


def area_at(name: str, point) -> tuple[str, str]:
    """Area of a tap on structure ``name`` at 3D ``point``."""
    area, side = simple_area(name)
    p = _point(point)
    if p is None:
        return area, side
    if area in LEG_AREAS:
        area = next(a for top, a in LEG_BANDS if p[1] < top)
    elif area in BACK_AREAS:
        area = "lower_back" if p[1] < LOW_BACK_TOP else "upper_back"
    return area, side


# --------------------------------------------------------------------------
# Build step: GLB -> artifacts/body_map.json + front_end/src/data/bodyAreas.json
# --------------------------------------------------------------------------

def _trs_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    t = np.array(node.get("translation", [0, 0, 0]), dtype=np.float64)
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    s = np.array(node.get("scale", [1, 1, 1]), dtype=np.float64)
    r = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    m = np.eye(4)
    m[:3, :3] = r * s
    m[:3, 3] = t
    return m


def _voxel_sample(pts: np.ndarray, voxel: float, cap: int, rng) -> np.ndarray:
    """One vertex per ``voxel``-sized cell keeps the surface evenly covered."""
    _, keep = np.unique(np.floor(pts / voxel).astype(np.int64), axis=0, return_index=True)
    sample = pts[np.sort(keep)]
    if len(sample) > cap:
        sample = sample[rng.choice(len(sample), cap, replace=False)]
    return sample


def build(voxel: float = 0.008, cap: int = 1200) -> dict:
    raw = GLB.read_bytes()
    json_len = struct.unpack("<I", raw[12:16])[0]
    gltf = json.loads(raw[20:20 + json_len])
    bin_start = 20 + json_len + 8
    blob = raw[bin_start:]

    def positions(accessor_index: int) -> np.ndarray:
        acc = gltf["accessors"][accessor_index]
        view = gltf["bufferViews"][acc["bufferView"]]
        offset = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = view.get("byteStride", 12)
        data = np.frombuffer(blob, dtype=np.uint8, count=stride * acc["count"], offset=offset)
        return data.reshape(acc["count"], stride)[:, :12].copy().view(np.float32).reshape(-1, 3).astype(np.float64)

    def collect(node_index: int, parent: np.ndarray, out: list):
        node = gltf["nodes"][node_index]
        world = parent @ _trs_matrix(node)
        if "mesh" in node:
            for prim in gltf["meshes"][node["mesh"]]["primitives"]:
                pts = positions(prim["attributes"]["POSITION"])
                out.append((np.c_[pts, np.ones(len(pts))] @ world.T)[:, :3])
        for child in node.get("children", []):
            collect(child, world, out)

    rng = np.random.default_rng(0)
    structures = []
    scene = gltf["scenes"][gltf.get("scene", 0)]
    for index in scene["nodes"]:
        name = gltf["nodes"][index].get("name", "")
        chunks: list = []
        collect(index, np.eye(4), chunks)
        if not chunks:
            continue
        pts = np.vstack(chunks)
        sample = _voxel_sample(pts, voxel, cap, rng)
        area, side = simple_area(name)
        info = describe_structure(name)
        structures.append({
            "name": name, "area": area, "side": side, "type": info.structure_type,
            "center": np.round(pts.mean(axis=0), 4).tolist(),
            "min": np.round(pts.min(axis=0), 4).tolist(), "max": np.round(pts.max(axis=0), 4).tolist(),
            "samples": np.round(sample, 3).tolist(),
        })

    # Which way is the patient's left? Average x of ".l" structures.
    left_x = np.mean([s["center"][0] for s in structures if s["side"] == "left"])
    body_min = np.min([s["min"] for s in structures], axis=0)
    body_max = np.max([s["max"] for s in structures], axis=0)
    body = {"left_sign": 1 if left_x > 0 else -1, "min": body_min.round(4).tolist(), "max": body_max.round(4).tolist()}
    for key in SIMPLE_AREAS:
        # Muscles only: broad fascia sheets would stretch the box.
        members = [s for s in structures if s["area"] == key and s["type"] == "muscle" and "Diaphragm" not in s["name"]]
        body[key] = {
            "min": np.min([s["min"] for s in members], axis=0).round(4).tolist(),
            "max": np.max([s["max"] for s in members], axis=0).round(4).tolist(),
        }

    artifact = {"structures": structures, "body": body}
    ARTIFACT.write_text(json.dumps(artifact, separators=(",", ":")))

    # The browser only needs name -> area and the labels.
    FRONT_END_MAP.parent.mkdir(parents=True, exist_ok=True)
    FRONT_END_MAP.write_text(json.dumps({
        "areas": {k: {"label": v[0], "sided": v[1]} for k, v in SIMPLE_AREAS.items()},
        "bands": {"legAreas": list(LEG_AREAS), "leg": LEG_BANDS, "backAreas": list(BACK_AREAS), "lowBackTop": LOW_BACK_TOP},
        "structures": {s["name"]: s["area"] for s in structures},
    }, indent=1, sort_keys=True))
    return artifact


@lru_cache(maxsize=1)
def body_map() -> dict | None:
    if not ARTIFACT.exists():
        return None
    data = json.loads(ARTIFACT.read_text())
    for s in data["structures"]:
        s["samples_np"] = np.array(s["samples"], dtype=np.float64)
    return data


# --------------------------------------------------------------------------
# Localizer
# --------------------------------------------------------------------------

# Patient words -> which tissue types they make more likely. Multipliers.
TISSUE_PRIORS = {
    # PainBERT labels
    "pressure": {"muscle": 1.35},
    "aching": {"muscle": 1.2},
    "stiffness": {"muscle": 1.15, "fascia": 1.1},
    "swelling": {"ligament": 1.4, "bursa": 1.5, "tendon": 1.3},
    "trauma": {"ligament": 1.35, "tendon": 1.2},
    "sharp": {"tendon": 1.15, "ligament": 1.15},
    "burning": {"fascia": 1.15},
}
# Free-text cues that PainBERT has no label for.
TEXT_PRIORS = [
    (r"\b(twist|twisted|rolled|sprain|popp?ed|pop|gave way|buckled)\b", {"ligament": 1.5, "tendon": 1.2}),
    (r"\b(workout|gym|lifting|lifted|exercise|sore after|cramp|cramping|knot|pulled a muscle|strain)", {"muscle": 1.4}),
    (r"\b(running|run|jump|jumping|tendon|repetitive|overuse|typing|tennis|golf)", {"tendon": 1.35}),
    (r"\b(lying on|lie on|sleep on (it|that side)|bump|lump|squishy)", {"bursa": 1.5}),
]
NEIGHBOUR_RADIUS = 0.03
NEIGHBOUR_WEIGHT = 0.6
SIGMA = 0.025  # metres; a fingertip-to-palm sized neighbourhood on the model


def _type_weights(descriptors: set[str], text: str) -> dict[str, float]:
    weights = {"muscle": 1.0, "tendon": 1.0, "ligament": 1.0, "fascia": 0.8, "bursa": 0.85}
    for key in descriptors:
        for tissue, factor in TISSUE_PRIORS.get(key, {}).items():
            weights[tissue] *= factor
    lower = (text or "").lower()
    for pattern, effects in TEXT_PRIORS:
        if re.search(pattern, lower):
            for tissue, factor in effects.items():
                weights[tissue] *= factor
    return weights


def _point(value) -> np.ndarray | None:
    if value is None:
        return None
    if isinstance(value, str):
        parts = value.split()
    else:
        parts = list(value)
    try:
        arr = np.array([float(p) for p in parts[:3]], dtype=np.float64)
    except (TypeError, ValueError):
        return None
    return arr if arr.shape == (3,) and np.all(np.isfinite(arr)) else None


def where_in_area(area: str, point: np.ndarray | None) -> str | None:
    """Plain-language sub-location, e.g. 'upper right' for the belly."""
    data = body_map()
    if data is None or point is None or area not in data["body"]:
        return None
    box = data["body"][area]
    lo, hi = np.array(box["min"]), np.array(box["max"])
    rel = (point - lo) / np.maximum(hi - lo, 1e-6)
    patient_left = (point[0] > (data["body"]["min"][0] + data["body"]["max"][0]) / 2) == (data["body"]["left_sign"] > 0)
    centre_x = abs(point[0] - (data["body"]["min"][0] + data["body"]["max"][0]) / 2) < 0.025
    side = "middle" if centre_x else ("left" if patient_left else "right")
    if area in ("abdomen", "chest", "upper_back", "lower_back", "neck", "head"):
        vertical = "upper" if rel[1] > 0.6 else "lower" if rel[1] < 0.4 else "central"
        if area == "abdomen" and vertical == "central" and side == "middle":
            return "around the belly button"
        return f"{vertical} {side}" if side != "middle" else f"{vertical} middle"
    return None


def localize(area: str, side: str | None, point, descriptors: set[str] | None = None, text: str = "", top: int = 5) -> dict:
    data = body_map()
    if data is None:
        return {"candidates": [], "confidence": None, "note": "Body map artifact is not installed."}
    point = _point(point)
    same_side = lambda s: side in (None, "midline", "") or s["side"] in (side, "midline")  # noqa: E731
    pool = [s for s in data["structures"] if s["area"] == area and same_side(s)]
    if point is not None:
        # Structures from a neighbouring area that physically sit under the
        # tap (e.g. the quadriceps tendon over the knee) are candidates too.
        names = {s["name"] for s in pool}
        pool += [s for s in data["structures"] if s["name"] not in names and same_side(s)
                 and float(np.min(np.linalg.norm(s["samples_np"] - point, axis=1))) < NEIGHBOUR_RADIUS]
    if not pool:
        return {"candidates": [], "confidence": None, "note": f"No structures mapped to area {area!r}."}
    if point is None:
        # Chosen from the list, not tapped: there is nothing to rank by.
        return {"candidates": [], "confidence": None, "where": None, "caveat": AREA_CAVEATS.get(area),
                "note": "No tap position. Tap the spot on the model to rank the structures under it."}
    weights = _type_weights(descriptors or set(), text)

    scored = []
    for s in pool:
        if point is not None:
            distance = float(np.min(np.linalg.norm(s["samples_np"] - point, axis=1)))
            geo = math.exp(-(distance / SIGMA) ** 2 / 2)
        else:
            distance, geo = None, 1.0
        # The patient chose this area; structures borrowed from the next
        # area only win when they are clearly closer.
        score = geo * weights.get(s["type"], 1.0) * (1.0 if s["area"] == area else NEIGHBOUR_WEIGHT)
        scored.append((score, distance, s))
    total = sum(score for score, _, _ in scored) or 1.0
    scored.sort(key=lambda item: -item[0])

    candidates = []
    for score, distance, s in scored[:top]:
        info = describe_structure(s["name"])
        candidates.append({
            "name": s["name"], "display": info.base_name + (f" ({info.side})" if info.side != "midline" else ""),
            "type": s["type"], "nerve": info.nerve, "roots": info.roots,
            "share": round(score / total, 3),
            "distance_cm": None if distance is None else round(distance * 100, 1),
        })
    top_share = candidates[0]["share"] if candidates else 0
    confidence = None if point is None else "high" if top_share >= 0.5 else "moderate" if top_share >= 0.25 else "low"
    return {
        "candidates": candidates,
        "confidence": confidence,
        "where": where_in_area(area, point),
        "caveat": AREA_CAVEATS.get(area),
        "tissue_weights": {k: round(v, 2) for k, v in weights.items()},
        "method": "Nearest-surface distance from the marked point (Gaussian, sigma 2.5 cm) x tissue prior from the patient's words",
    }


if __name__ == "__main__":
    out = build()
    print(f"{len(out['structures'])} structures -> {ARTIFACT}")
    print(f"area map -> {FRONT_END_MAP}")
