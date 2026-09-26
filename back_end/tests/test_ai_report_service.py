import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_report_service import (  # noqa: E402
    GROQ_REPORT_MODEL,
    MissingReportApiKey,
    generate_ai_report,
)
from main import app  # noqa: E402


class ReportServiceTests(unittest.TestCase):
    def test_missing_key_fails_without_calling_provider(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            with self.assertRaises(MissingReportApiKey):
                generate_ai_report(30, "2026-09-26", {}, {})

    def test_sends_only_intake_data_and_validates_report(self):
        report = {
            "report_title": "Patient-Reported Pain Summary",
            "patient_experience_summary": "The patient reports pain.",
            "pain_course_summary": "Not reported",
            "functional_impact_summary": "Not reported",
            "associated_symptoms_summary": "Not reported",
            "aggravating_factors": [],
            "relieving_factors": [],
            "region_summaries": [{
                "region_name": "Hamstring",
                "severity": 5,
                "pain_character": "Aching",
                "frequency": "Occasional",
                "onset": "Not reported",
                "original_patient_note": "Aches after running",
                "professionally_reworded_note": "Reports aching after running.",
                "clinical_summary": "Patient reports hamstring aching after running.",
            }],
            "clinician_review_items": [],
            "documentation_statement": "Draft statement",
        }
        fake_completion = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps(report))
        )])

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-only-key"}):
            with patch("ai_report_service.OpenAI") as client_class:
                client_class.return_value.chat.completions.create.return_value = fake_completion
                result = generate_ai_report(
                    30,
                    "2026-09-26",
                    {"impact": "running"},
                    {"hamstring": {"severity": 5, "notes": "Aches after running"}},
                )

        client_kwargs = client_class.call_args.kwargs
        self.assertEqual(client_kwargs["base_url"], "https://api.groq.com/openai/v1")
        request = client_class.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], GROQ_REPORT_MODEL)
        self.assertTrue(request["response_format"]["json_schema"]["strict"])
        self.assertNotIn("provider", request)
        self.assertIn("Aches after running", request["messages"][1]["content"])
        self.assertEqual(result["region_summaries"][0]["severity"], 5)
        self.assertIn("does not provide a diagnosis", result["documentation_statement"])

    def test_report_endpoint_returns_configuration_error_without_key(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            response = TestClient(app).post("/api/reports", json={
                "patient_name": "Synthetic Test",
                "patient_age": 30,
                "report_date": "2026-09-26",
                "questionnaire": {"impact": "running"},
                "pain_regions": {"hamstring": {"severity": 5}},
            })

        self.assertEqual(response.status_code, 503)
        self.assertIn("GROQ_API_KEY", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
