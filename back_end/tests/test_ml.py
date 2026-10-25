import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import app  # noqa: E402
from ml.anatomy import analyse_pain_map, describe_structure, root_range  # noqa: E402
from ml.concepts import concepts_from_intake, concepts_from_rfv_labels  # noqa: E402
from ml.inference import triage  # noqa: E402
from ml.red_flags import evaluate_red_flags  # noqa: E402

FRONT_END = Path(__file__).resolve().parents[2] / "front_end"


def spot(name, severity=5, **extra):
    return {"regionName": name, "severity": severity, **extra}


class AnatomyTests(unittest.TestCase):
    def test_root_range_crosses_regions(self):
        self.assertEqual(root_range("L4-S1"), ["L4", "L5", "S1"])
        self.assertEqual(root_range("C8-T1"), ["C8", "T1"])

    def test_known_innervation(self):
        cases = {
            "Acromial part of deltoid muscle.l": ("Axillary nerve", ["C5", "C6"]),
            "Tibialis anterior muscle.r": ("Deep fibular nerve", ["L4", "L5"]),
            "Extensor digitorum longus.r": ("Deep fibular nerve", ["L5", "S1"]),
            "Extensor digitorum.l": ("Posterior interosseous nerve", ["C7", "C8"]),
            "Short head of biceps femoris.l": ("Common fibular division of sciatic nerve", ["L5", "S1", "S2"]),
        }
        for name, (nerve, roots) in cases.items():
            info = describe_structure(name)
            self.assertEqual((info.nerve, info.roots), (nerve, roots), name)

    def test_regions_and_sides(self):
        self.assertEqual(describe_structure("External abdominal oblique muscle.r").region, "abdomen")
        self.assertEqual(describe_structure("Deep head of pronator teres.l").region, "arm")
        info = describe_structure("Gluteus medius muscle.l")
        self.assertEqual((info.side, info.wpi_area), ("left", "hip_l"))

    def test_every_model_structure_maps(self):
        names = {line.strip() for line in (FRONT_END / "node_names.txt").read_text().splitlines() if line.strip()}
        for name in names:
            info = describe_structure(name)
            self.assertTrue(info.region, name)
            if info.structure_type == "muscle" and "tarsus" not in name and "tendinous ring" not in name:
                self.assertIsNotNone(info.nerve, name)

    def test_l5_pattern_detected_across_nerves(self):
        result = analyse_pain_map([
            spot("Gluteus medius muscle.l", 7), spot("Tibialis anterior muscle.l"),
            spot("Extensor hallucis longus.l"), spot("Fibularis longus muscle.l"),
        ])
        self.assertEqual(result["segment_pattern"]["root"], "L5")
        self.assertEqual(result["segment_pattern"]["distinct_nerves"], 3)

    def test_widespread_pain_index(self):
        result = analyse_pain_map([
            spot("Acromial part of deltoid muscle.l"), spot("Acromial part of deltoid muscle.r"),
            spot("Gluteus maximus muscle.l"), spot("Gluteus maximus muscle.r"), spot("Multifidus lumborum muscle.l"),
        ])
        self.assertEqual(result["wpi"]["score"], 5)
        self.assertTrue(result["wpi"]["generalized_pattern"])


class ConceptTests(unittest.TestCase):
    def test_rfv_labels(self):
        found = concepts_from_rfv_labels(["Low back pain, ache, soreness, discomfort", "Hay fever"])
        self.assertEqual(found["back"], 1)
        self.assertEqual(found["fever"], 0)

    def test_intake(self):
        found = concepts_from_intake(["chest"], {"symptoms": ["Sweating"], "trigger": "After a fall or injury"}, {"weakness"})
        self.assertEqual({k for k, v in found.items() if v}, {"chest", "sweating", "injury", "weakness"})


class RedFlagTests(unittest.TestCase):
    def ctx(self, **overrides):
        base = {"regions": set(), "symptoms": set(), "nlp": set(), "max_severity": 5, "age": 40,
                "onset": None, "history": set(), "trend": None}
        return {**base, **overrides}

    def ids(self, **overrides):
        return [flag["id"] for flag in evaluate_red_flags(self.ctx(**overrides))]

    def test_chest_with_breathlessness_is_emergency(self):
        flags = evaluate_red_flags(self.ctx(regions={"chest"}, symptoms={"breathless"}))
        self.assertEqual(flags[0]["id"], "chest_plus")
        self.assertEqual(flags[0]["level"], "emergency")

    def test_cauda_equina(self):
        self.assertIn("cauda_equina", self.ids(regions={"back"}, nlp={"bladder_bowel"}))

    def test_no_flags_for_simple_case(self):
        self.assertEqual(self.ids(regions={"knee"}, nlp={"aching"}), [])

    def test_emergency_sorted_first(self):
        flags = evaluate_red_flags(self.ctx(regions={"chest", "back"}, symptoms={"sweating", "fever"}, nlp={"distress"}))
        self.assertEqual(flags[0]["level"], "emergency")
        self.assertEqual(flags[-1]["level"], "support")


@unittest.skipIf(triage() is None, "triage artifact not trained")
class AnalyzeEndpointTests(unittest.TestCase):
    def test_analyze_returns_all_parts(self):
        response = TestClient(app).post("/api/analyze", json={
            "age": 62, "sex": "Female",
            "questionnaire": {"symptoms": ["Shortness of breath", "Sweating"], "history": ["Heart disease"]},
            "pain_regions": {"a": spot("Sternocostal head of pectoralis major muscle.l", 8)},
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["care_level"]["level"], "emergency")
        probabilities = [p["p"] for p in body["triage"]["probabilities"]]
        self.assertAlmostEqual(sum(probabilities), 1.0, places=3)
        self.assertGreater(body["triage"]["p_emergent"], 0.3)

    def test_empty_map(self):
        body = TestClient(app).post("/api/analyze", json={"questionnaire": {}, "pain_regions": {}}).json()
        self.assertIsNone(body["care_level"])
        self.assertIsNone(body["triage"])

    def test_model_cards(self):
        body = TestClient(app).get("/api/models").json()
        self.assertGreater(body["triage"]["acuity"]["test"]["macro_auroc"], 0.7)


if __name__ == "__main__":
    unittest.main()
