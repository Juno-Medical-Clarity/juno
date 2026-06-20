"""Happy-path test for the V1.2 simplification pipeline (SSE stream)."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent
for p in (str(BACKEND_DIR), str(PROJECT_DIR)):
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)

import routes.simplify_v1_2 as v1_2_module
from backend.models.metrics import Metrics


def parse_sse(chunks):
    """Parse SSE chunks (strings) into a list of event dicts."""
    events = []
    for chunk in chunks:
        if not isinstance(chunk, str):
            continue
        for block in chunk.strip().split("\n\n"):
            if block.startswith("data: "):
                try:
                    events.append(json.loads(block.removeprefix("data: ")))
                except json.JSONDecodeError:
                    pass
    return events


class FakeV1_2Pipeline:
    """Canned pipeline that returns a minimal care plan without touching LLMs."""

    def simplify_language_with_term_plan(self, text, substitution_candidates, preserve_terms, abbreviations):
        return "simplified text"

    def clarify_and_action(self, simplified, abbreviations):
        return "clarified text"

    def structure_appointment_note(self, clarified):
        return {
            "summary": "Patient has high blood pressure.",
            "diagnosis": {"main_conclusion": "Hypertension", "details": []},
            "medications": [],
            "follow_up": [],
            "reason_for_visit": [],
        }


class TestPipelineHappyPath(unittest.TestCase):
    """run_v1_2_pipeline with a mocked LLM pipeline streams steps then a result."""

    def _run_pipeline(self, text="Patient note.", grading_enabled=False):
        metrics = Metrics.start(
            session_id="session-1",
            pipeline_version="v1-2",
            input_type="text",
        )
        with patch.object(v1_2_module, "V1_2Pipeline", return_value=FakeV1_2Pipeline()), \
             patch.object(v1_2_module, "_score_or_none", return_value=None):
            chunks = list(v1_2_module.run_v1_2_pipeline(text, metrics, grading_enabled=grading_enabled))
        return parse_sse(chunks)

    def test_no_error_events(self):
        events = self._run_pipeline()
        error_events = [e for e in events if e.get("step") == "error"]
        self.assertEqual(error_events, [], f"Unexpected error events: {error_events}")

    def test_terminal_result_event_present(self):
        events = self._run_pipeline()
        result_events = [e for e in events if e.get("step") == "result"]
        self.assertEqual(len(result_events), 1, f"Expected exactly one result event, got: {result_events}")

    def test_terminal_event_has_simplified_care_plan(self):
        events = self._run_pipeline()
        result = next(e for e in events if e.get("step") == "result")
        data = result.get("data", {})
        self.assertIn("simplified_care_plan", data)

    def test_terminal_event_has_grading(self):
        events = self._run_pipeline()
        result = next(e for e in events if e.get("step") == "result")
        data = result.get("data", {})
        self.assertIn("grading", data)

    def test_terminal_event_grading_enabled_false(self):
        """With grading_enabled=False the grading object has enabled=False and no entries."""
        events = self._run_pipeline(grading_enabled=False)
        result = next(e for e in events if e.get("step") == "result")
        grading = result["data"]["grading"]
        self.assertFalse(grading["enabled"])
        self.assertEqual(grading["entries"], [])

    def test_progress_events_appear_before_result(self):
        """Step-progress events (step 2-5) must all appear before the result event."""
        events = self._run_pipeline()
        result_idx = next(i for i, e in enumerate(events) if e.get("step") == "result")
        progress_events = [
            e for e in events[:result_idx]
            if isinstance(e.get("step"), int)
        ]
        self.assertGreater(len(progress_events), 0, "Expected progress events before result")

    def test_step_labels_are_present(self):
        events = self._run_pipeline()
        progress_events = [e for e in events if isinstance(e.get("step"), int)]
        for event in progress_events:
            with self.subTest(event=event):
                self.assertIn("label", event)

    def test_terminal_event_has_metrics(self):
        events = self._run_pipeline()
        result = next(e for e in events if e.get("step") == "result")
        data = result["data"]
        self.assertIn("metrics", data)


class TestPipelineGradingEnabled(unittest.TestCase):
    """With grading_enabled=True the grading object has entries."""

    def _run_pipeline(self, text, grading_enabled=True):
        metrics = Metrics.start(
            session_id="session-1",
            pipeline_version="v1-2",
            input_type="text",
        )
        fake_score = {
            "composite": 55,
            "grade_estimate": 10.5,
            "label": "Moderate",
            "word_count": 50,
            "dimensions": {
                "grade_level": {"score": 60, "raw": 10.5, "label": "Grade Level", "unit": "grade"},
                "jargon_density": {"score": 70, "raw": 0.1, "label": "Jargon", "unit": "proportion"},
                "sentence_complexity": {"score": 80, "raw": 12.0, "label": "Sentence", "unit": "words/sentence"},
                "passive_voice": {"score": 90, "raw": 0.0, "label": "Active", "unit": "passive ratio"},
                "actionability": {"score": 50, "raw": 0.05, "label": "Action", "unit": "you-rate"},
                "numeracy_clarity": {"score": 100, "raw": 0.0, "label": "Numeracy", "unit": "vague count"},
                "structural_clarity": {"score": 75, "raw": 30.0, "label": "Structure", "unit": "words/paragraph"},
            },
            "research_basis": {},
        }
        with patch.object(v1_2_module, "V1_2Pipeline", return_value=FakeV1_2Pipeline()), \
             patch.object(v1_2_module, "_score_or_none", return_value=fake_score):
            chunks = list(v1_2_module.run_v1_2_pipeline(text, metrics, grading_enabled=grading_enabled))
        return [
            json.loads(block.removeprefix("data: "))
            for chunk in chunks if isinstance(chunk, str)
            for block in chunk.strip().split("\n\n")
            if block.startswith("data: ")
        ]

    def test_grading_enabled_has_entries(self):
        long_text = (
            "The patient has hypertension. Take your pills daily. "
            "Follow up in two weeks. Call us if anything changes. "
            "Drink more water and reduce salt intake. Avoid stress. Rest well."
        )
        events = self._run_pipeline(long_text, grading_enabled=True)
        result = next(e for e in events if e.get("step") == "result")
        grading = result["data"]["grading"]
        self.assertTrue(grading.get("enabled"))
        self.assertGreater(len(grading["entries"]), 0)


if __name__ == "__main__":
    unittest.main()
