"""Runs the pain scenarios, sweeps and safety invariants (no LLM calls)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import scenarios, sweep  # noqa: E402


class ScenarioTests(unittest.TestCase):
    def test_every_scenario_passes(self):
        out = scenarios.run(jitter_runs=1, verbose=False)
        failures = {r["id"]: r["problems"] for r in out["results"] if r["problems"]}
        self.assertEqual(failures, {})

    def test_phrase_battery(self):
        _, failures = sweep.phrase_battery()
        self.assertEqual(failures, [])

    def test_random_patients_keep_safety_invariants(self):
        _, _, violations = sweep.random_patients(n=150)
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
