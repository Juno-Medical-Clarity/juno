"""Error-path tests for the V1.2 simplification pipeline (SSE stream)."""

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


class FailingPipeline:
    """Pipeline that always raises on simplify_language_with_term_plan."""

    def simplify_language_with_term_plan(self, *args, **kwargs):
        raise RuntimeError("Injected simplify failure")

    def clarify_and_action(self, *args, **kwargs):
        raise RuntimeError("Should not reach clarify")

    def structure_appointment_note(self, *args, **kwargs):
        raise RuntimeError("Should not reach structure")


class FailingStructurePipeline:
    """Pipeline that succeeds through simplify but fails on structure."""

    def simplify_language_with_term_plan(self, *args, **kwargs):
        return "simplified text"

    def clarify_and_action(self, *args, **kwargs):
        return "clarified text"

    def structure_appointment_note(self, *args, **kwargs):
        raise RuntimeError("Injected structure failure")


class TestPipelineSimplifyError(unittest.TestCase):
    """When simplify_language raises, an error SSE event must be streamed."""

    def _run_pipeline(self, pipeline_factory):
        metrics = Metrics.start(
            session_id="session-1",
            pipeline_version="v1-2",
            input_type="text",
        )
        with patch.object(v1_2_module, "V1_2Pipeline", return_value=pipeline_factory()), \
             patch.object(v1_2_module, "_score_or_none", return_value=None):
            chunks = list(v1_2_module.run_v1_2_pipeline(
                "some input text", metrics, grading_enabled=False
            ))
        return parse_sse(chunks)

    def test_simplify_error_yields_error_event(self):
        events = self._run_pipeline(FailingPipeline)
        error_events = [e for e in events if e.get("step") == "error"]
        self.assertGreater(
            len(error_events), 0,
            f"Expected at least one error event, got: {events}"
        )

    def test_simplify_error_no_result_event(self):
        """If simplification fails, no result event should be emitted."""
        events = self._run_pipeline(FailingPipeline)
        result_events = [e for e in events if e.get("step") == "result"]
        self.assertEqual(result_events, [], f"Unexpected result event after error: {result_events}")

    def test_error_event_has_error_field(self):
        events = self._run_pipeline(FailingPipeline)
        error_event = next(e for e in events if e.get("step") == "error")
        self.assertIn("error", error_event)
        self.assertIsInstance(error_event["error"], str)
        self.assertTrue(len(error_event["error"]) > 0)

    def test_error_message_contains_reason(self):
        events = self._run_pipeline(FailingPipeline)
        error_event = next(e for e in events if e.get("step") == "error")
        # The pipeline wraps the exception message in the SSE error field.
        self.assertIn("Simplification failed", error_event["error"])

    def test_structure_error_yields_error_event(self):
        events = self._run_pipeline(FailingStructurePipeline)
        error_events = [e for e in events if e.get("step") == "error"]
        self.assertGreater(
            len(error_events), 0,
            f"Expected error event on structure failure, got: {events}"
        )


class TestPipelineInitError(unittest.TestCase):
    """When V1_2Pipeline() itself raises, an error SSE event must be streamed."""

    def _run_pipeline_with_bad_init(self):
        metrics = Metrics.start(
            session_id="session-1",
            pipeline_version="v1-2",
            input_type="text",
        )
        with patch.object(
            v1_2_module, "V1_2Pipeline", side_effect=RuntimeError("No credentials")
        ):
            chunks = list(v1_2_module.run_v1_2_pipeline(
                "some input", metrics, grading_enabled=False
            ))
        return parse_sse(chunks)

    def test_init_error_yields_error_event(self):
        events = self._run_pipeline_with_bad_init()
        error_events = [e for e in events if e.get("step") == "error"]
        self.assertGreater(len(error_events), 0, f"Expected error event, got: {events}")

    def test_init_error_no_result_event(self):
        events = self._run_pipeline_with_bad_init()
        result_events = [e for e in events if e.get("step") == "result"]
        self.assertEqual(result_events, [])


if __name__ == "__main__":
    unittest.main()
