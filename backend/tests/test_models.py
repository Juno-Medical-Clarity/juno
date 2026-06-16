"""Tests for backend.models.metrics — Metrics model."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.models.metrics import Metrics


class TestMetrics(unittest.TestCase):
    """Tests for the Metrics dataclass."""

    def test_start_produces_correct_shape(self):
        """Metrics.start() must produce a dict with all required keys."""
        m = Metrics.start(
            session_id="sess-abc",
            pipeline_version="v1-2",
            input_type="file",
        )
        d = m.to_dict()

        self.assertEqual(d["session_id"], "sess-abc")
        self.assertEqual(d["pipeline_version"], "v1-2")
        self.assertEqual(d["input_type"], "file")
        # created_at must be a valid ISO8601 UTC string
        self.assertIn("T", d["created_at"])
        # defaults
        self.assertIsNone(d["total_duration_ms"])
        self.assertEqual(d["step_durations_ms"], {})
        self.assertIsNone(d["saved_id"])

    def test_start_created_at_is_utc_iso8601(self):
        """created_at must be parseable as a UTC ISO8601 timestamp."""
        m = Metrics.start("s", "v1", "text")
        # fromisoformat accepts the +00:00 suffix produced by timezone.utc
        parsed = datetime.fromisoformat(m.created_at)
        self.assertEqual(parsed.tzinfo.utcoffset(parsed).total_seconds(), 0)

    def test_to_dict_roundtrip(self):
        """Full round-trip: instance -> dict -> instance must be equal."""
        original = Metrics(
            session_id="sess-xyz",
            pipeline_version="v1-2",
            input_type="file",
            created_at="2026-06-16T12:00:00+00:00",
            total_duration_ms=4213.5,
            step_durations_ms={"find_medical_terms": 812.1},
            saved_id="doc-999",
        )
        d = original.to_dict()

        expected = {
            "session_id": "sess-xyz",
            "pipeline_version": "v1-2",
            "input_type": "file",
            "created_at": "2026-06-16T12:00:00+00:00",
            "total_duration_ms": 4213.5,
            "step_durations_ms": {"find_medical_terms": 812.1},
            "saved_id": "doc-999",
        }
        self.assertEqual(d, expected)

        reconstructed = Metrics.from_dict(d)
        self.assertEqual(reconstructed, original)

    def test_mutable_fields_can_be_set_post_creation(self):
        """Metrics is not frozen — durations and saved_id can be mutated."""
        m = Metrics.start("s", "v1", "doc_id")
        m.total_duration_ms = 100.0
        m.step_durations_ms["step_a"] = 50.0
        m.saved_id = "doc-1"

        self.assertEqual(m.total_duration_ms, 100.0)
        self.assertEqual(m.step_durations_ms, {"step_a": 50.0})
        self.assertEqual(m.saved_id, "doc-1")

    def test_metrics_inherits_json_model(self):
        """Metrics must inherit from JsonModel, not VersionedJsonModel."""
        from backend.models.base import JsonModel, VersionedJsonModel

        self.assertIsInstance(Metrics.start("s", "v1", "text"), JsonModel)
        self.assertNotIsInstance(Metrics.start("s", "v1", "text"), VersionedJsonModel)


if __name__ == "__main__":
    unittest.main()
