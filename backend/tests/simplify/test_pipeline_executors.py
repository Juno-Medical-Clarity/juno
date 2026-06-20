import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent
for path in (PROJECT_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from models.metrics import Metrics
import routes.care_plan as care_plan_module


class FakePipeline:
    def simplify_language_with_term_plan(self, text, substitution_candidates, preserve_terms, abbreviations):
        return f"simplified: {text}"

    def clarify_and_action(self, simplified, abbreviations):
        return f"clarified: {simplified}"

    def structure_appointment_note(self, clarified):
        return {"summary": clarified}


class CarePlanPipelineExecutorTest(unittest.TestCase):
    def _events_from_chunks(self, chunks):
        events = []
        for chunk in chunks:
            if isinstance(chunk, tuple):
                continue  # skip __result__ sentinel
            for block in chunk.strip().split("\n\n"):
                if block.startswith("data: "):
                    events.append(json.loads(block.removeprefix("data: ")))
        return events

    @patch("routes.care_plan.score_text", return_value={"composite": 70, "grade_estimate": 6.0, "label": "ok", "word_count": 50, "dimensions": {}})
    @patch("routes.care_plan.build_glossary_from_simplified_text", return_value={})
    @patch(
        "routes.care_plan.detect_terms",
        return_value={
            "substitution_candidates": [],
            "preserve_and_define_terms": [],
            "abbreviations": [],
        },
    )
    @patch("routes.care_plan.V1_2Pipeline", return_value=FakePipeline())
    def test_run_care_plan_pipeline_direct_text_yields_steps_and_sentinel(
        self,
        _pipeline,
        _detect_terms,
        _glossary,
        _score,
    ):
        metrics = Metrics.start(
            session_id="session-1",
            pipeline_version="v1-2",
            input_type="text",
        )

        chunks = list(care_plan_module.run_care_plan_pipeline(
            "plain note",
            metrics,
            grading_enabled=False,
        ))

        events = self._events_from_chunks(chunks)
        self.assertEqual(
            [(event["step"], event.get("status")) for event in events],
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
        # Last item is the __result__ sentinel tuple
        tuple_chunks = [c for c in chunks if isinstance(c, tuple)]
        self.assertEqual(len(tuple_chunks), 1)
        sentinel = tuple_chunks[0]
        self.assertEqual(sentinel[0], "__result__")
        # care_plan and grading objects should be returned
        _, care_plan_obj, grading_obj, raw_text, clarified_text = sentinel[:5]
        self.assertEqual(raw_text, "plain note")
        self.assertIn("plain note", clarified_text)


if __name__ == "__main__":
    unittest.main()
