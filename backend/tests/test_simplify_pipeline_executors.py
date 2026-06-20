import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
for path in (PROJECT_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from models.metrics import Metrics
import routes.simplify as simplify_module
import routes.simplify_v1_1 as simplify_v1_1_module


class FakeV1Pipeline:
    def classify_document(self, text):
        return {"doc_type": "appointment_note"}

    def detect_jargon(self, text):
        return {"medical_jargon": [], "complex_terms": []}

    def simplify_language(self, text, medical_jargon, complex_terms):
        return f"simplified: {text}"

    def add_definitions(self, simplified, medical_jargon):
        return f"defined: {simplified}"

    def clarify_and_action(self, with_defs):
        return f"clarified: {with_defs}"

    def structure_document(self, clarified, medical_jargon, doc_type):
        return {"doc_type": doc_type, "summary": clarified}


class FakeV1_1Pipeline:
    def simplify_language_with_term_plan(self, text, substitution_candidates, preserve_terms, abbreviations):
        return f"simplified: {text}"

    def clarify_and_action(self, simplified, abbreviations):
        return f"clarified: {simplified}"

    def structure_appointment_note(self, clarified):
        return {"summary": clarified, "questions": ["legacy question"]}


class SimplifyPipelineExecutorsTest(unittest.TestCase):
    def _events_from_chunks(self, chunks):
        events = []
        for chunk in chunks:
            for block in chunk.strip().split("\n\n"):
                if block.startswith("data: "):
                    events.append(json.loads(block.removeprefix("data: ")))
        return events

    @patch("routes.simplify.score_text", return_value={"score": 1})
    @patch("routes.simplify.V1Pipeline", return_value=FakeV1Pipeline())
    def test_run_v1_pipeline_direct_text_yields_steps_and_result_without_saving(
        self,
        _pipeline,
        _score,
    ):
        metrics = Metrics.start(
            session_id="session-1",
            pipeline_version="v1",
            input_type="text",
        )

        events = self._events_from_chunks(
            simplify_module.run_v1_pipeline(
                "plain note",
                metrics,
                grading_enabled=False,
            )
        )

        self.assertEqual(
            [(event["step"], event.get("status")) for event in events[:-1]],
            [
                (2, "active"),
                (2, "done"),
                (3, "active"),
                (3, "done"),
                (4, "active"),
                (4, "done"),
                (5, "active"),
                (5, "done"),
                (6, "active"),
                (7, "active"),
                (6, "done"),
                (7, "done"),
            ],
        )
        result_event = events[-1]
        self.assertEqual(result_event["step"], "result")
        self.assertEqual(result_event["data"]["input"]["mode"], "text")
        self.assertEqual(result_event["data"]["input"]["text"], "plain note")
        self.assertEqual(result_event["data"]["metrics"]["saved_id"], None)
        self.assertIn("plain note", result_event["data"]["care_plan"]["summary"])

    @patch("routes.simplify_v1_1.score_text", return_value={"score": 1})
    @patch("routes.simplify_v1_1.build_glossary_from_simplified_text", return_value={})
    @patch(
        "routes.simplify_v1_1.detect_terms",
        return_value={
            "substitution_candidates": [],
            "preserve_and_define_terms": [],
            "abbreviations": [],
        },
    )
    @patch("routes.simplify_v1_1.V1_1Pipeline", return_value=FakeV1_1Pipeline())
    def test_run_v1_1_pipeline_direct_text_yields_steps_and_result_without_saving(
        self,
        _pipeline,
        _detect_terms,
        _glossary,
        _score,
    ):
        metrics = Metrics.start(
            session_id="session-1",
            pipeline_version="v1-1",
            input_type="text",
        )

        events = self._events_from_chunks(
            simplify_v1_1_module.run_v1_1_pipeline(
                "plain note",
                metrics,
                grading_enabled=False,
            )
        )

        self.assertEqual(
            [(event["step"], event.get("status")) for event in events[:-1]],
            [
                (2, "active"),
                (2, "done"),
                (3, "active"),
                (3, "done"),
                (4, "active"),
                (4, "done"),
                (5, "active"),
                (5, "done"),
            ],
        )
        result_event = events[-1]
        self.assertEqual(result_event["step"], "result")
        self.assertEqual(result_event["data"]["input"]["mode"], "text")
        self.assertEqual(result_event["data"]["input"]["text"], "plain note")
        self.assertEqual(result_event["data"]["metrics"]["saved_id"], None)
        self.assertIn("plain note", result_event["data"]["care_plan"]["raw"]["text"])
        self.assertNotIn("questions", result_event["data"]["care_plan"])


if __name__ == "__main__":
    unittest.main()
