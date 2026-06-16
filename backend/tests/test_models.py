"""Tests for backend.models — Metrics and Input models."""

import io
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.models.grading import Grading
from backend.models.input import Input, InputFile
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


class TestInputFile(unittest.TestCase):
    """Tests for the InputFile dataclass."""

    def test_to_dict_roundtrip(self):
        """InputFile round-trips cleanly through to_dict/from_dict."""
        original = InputFile(
            filename="report.pdf",
            content_type="application/pdf",
            size_bytes=204800,
        )
        d = original.to_dict()
        self.assertEqual(d, {
            "filename": "report.pdf",
            "content_type": "application/pdf",
            "size_bytes": 204800,
        })
        reconstructed = InputFile.from_dict(d)
        self.assertEqual(reconstructed, original)

    def test_inherits_json_model(self):
        """InputFile must be a JsonModel subclass."""
        from backend.models.base import JsonModel
        self.assertIsInstance(
            InputFile("f.pdf", "application/pdf", 100),
            JsonModel,
        )


class TestInput(unittest.TestCase):
    """Tests for the Input dataclass and constructor helpers."""

    # ------------------------------------------------------------------
    # Mode: text
    # ------------------------------------------------------------------

    def test_from_text_roundtrip(self):
        """Input.from_text round-trips correctly."""
        inp = Input.from_text("Hello, world!")
        self.assertEqual(inp.mode, "text")
        self.assertEqual(inp.text, "Hello, world!")
        self.assertIsNone(inp.doc_id)
        self.assertEqual(inp.files, [])

        d = inp.to_dict()
        self.assertEqual(d["mode"], "text")
        self.assertEqual(d["text"], "Hello, world!")
        self.assertIsNone(d["doc_id"])
        self.assertEqual(d["files"], [])

        reconstructed = Input.from_dict(d)
        self.assertEqual(reconstructed, inp)

    # ------------------------------------------------------------------
    # Mode: doc_id
    # ------------------------------------------------------------------

    def test_from_doc_id_roundtrip(self):
        """Input.from_doc_id round-trips correctly."""
        inp = Input.from_doc_id("doc-abc123")
        self.assertEqual(inp.mode, "doc_id")
        self.assertEqual(inp.doc_id, "doc-abc123")
        self.assertIsNone(inp.text)
        self.assertEqual(inp.files, [])

        d = inp.to_dict()
        reconstructed = Input.from_dict(d)
        self.assertEqual(reconstructed, inp)

    # ------------------------------------------------------------------
    # Mode: file
    # ------------------------------------------------------------------

    def test_from_file_uploads_roundtrip(self):
        """Input.from_file_uploads builds correct metadata and resets streams."""

        class FakeUpload:
            """Minimal duck-typed FileStorage replacement."""
            def __init__(self, filename, content_type, content):
                self.filename = filename
                self.content_type = content_type
                self._stream = io.BytesIO(content)

            def read(self):
                return self._stream.read()

            def seek(self, pos):
                self._stream.seek(pos)

            def tell(self):
                return self._stream.tell()

        fake_pdf = FakeUpload("report.pdf", "application/pdf", b"PDF" * 1000)
        fake_txt = FakeUpload("notes.txt", "text/plain", b"A" * 512)

        inp = Input.from_file_uploads([fake_pdf, fake_txt])

        self.assertEqual(inp.mode, "file")
        self.assertIsNone(inp.text)
        self.assertIsNone(inp.doc_id)
        self.assertEqual(len(inp.files), 2)

        # Check metadata captured correctly
        self.assertEqual(inp.files[0].filename, "report.pdf")
        self.assertEqual(inp.files[0].content_type, "application/pdf")
        self.assertEqual(inp.files[0].size_bytes, 3000)  # b"PDF" * 1000

        self.assertEqual(inp.files[1].filename, "notes.txt")
        self.assertEqual(inp.files[1].content_type, "text/plain")
        self.assertEqual(inp.files[1].size_bytes, 512)

        # Streams must be reset so downstream code can re-read
        self.assertEqual(fake_pdf.tell(), 0)
        self.assertEqual(fake_txt.tell(), 0)

    def test_file_mode_nested_roundtrip(self):
        """Input with files list round-trips with nested InputFile objects."""
        original = Input(
            mode="file",
            files=[
                InputFile("a.pdf", "application/pdf", 1024),
                InputFile("b.txt", "text/plain", 256),
            ],
        )
        d = original.to_dict()

        # files should be a list of plain dicts in the serialized form
        self.assertIsInstance(d["files"][0], dict)
        self.assertEqual(d["files"][0]["filename"], "a.pdf")

        reconstructed = Input.from_dict(d)
        self.assertEqual(reconstructed.mode, "file")
        self.assertEqual(len(reconstructed.files), 2)
        # Nested objects must be InputFile instances, not dicts
        self.assertIsInstance(reconstructed.files[0], InputFile)
        self.assertEqual(reconstructed.files[0].filename, "a.pdf")
        self.assertEqual(reconstructed.files[0].size_bytes, 1024)
        self.assertEqual(reconstructed.files[1].filename, "b.txt")
        self.assertEqual(reconstructed, original)

    def test_inherits_json_model(self):
        """Input must be a JsonModel subclass."""
        from backend.models.base import JsonModel
        self.assertIsInstance(Input.from_text("x"), JsonModel)

    def test_empty_files_list_roundtrip(self):
        """Input with no files serializes and deserializes without error."""
        inp = Input(mode="file", files=[])
        self.assertEqual(Input.from_dict(inp.to_dict()), inp)


class TestGrading(unittest.TestCase):
    """Tests for the Grading stub model."""

    def test_default_to_dict(self):
        """Grading().to_dict() must equal {"entries": []}."""
        self.assertEqual(Grading().to_dict(), {"entries": []})

    def test_roundtrip(self):
        """Grading round-trips correctly through to_dict/from_dict."""
        original = Grading(entries=[{"term": "hypertension", "score": 0.9}])
        d = original.to_dict()
        self.assertEqual(d, {"entries": [{"term": "hypertension", "score": 0.9}]})
        reconstructed = Grading.from_dict(d)
        self.assertEqual(reconstructed, original)


class TestSimplifiedCarePlan(unittest.TestCase):
    """Tests for the SimplifiedCarePlan versioned model."""

    # Minimal representative V1.2 pipeline output.
    SAMPLE_V12 = {
        "doc_type": "appointment_note",
        "diagnosis": {"primary": "hypertension"},
        "terms": ["BP", "systolic"],
    }

    # ------------------------------------------------------------------
    # Acceptance criteria: from_pipeline_result -> to_dict round-trip
    # ------------------------------------------------------------------

    def test_v12_acceptance_criteria(self):
        """from_pipeline_result('1.2', sample).to_dict() == {'version': '1.2', **sample}."""
        from backend.models.care_plan import SimplifiedCarePlan

        result = SimplifiedCarePlan.from_pipeline_result("1.2", self.SAMPLE_V12).to_dict()
        expected = {"version": "1.2", **self.SAMPLE_V12}
        self.assertEqual(result, expected)

    def test_v10_pipeline_result_roundtrip(self):
        """Version 1.0 pipeline result serialises and flattens correctly."""
        from backend.models.care_plan import SimplifiedCarePlan

        sample = {"raw_text": "Patient presents with...", "scores": {"accuracy": 0.9}}
        result = SimplifiedCarePlan.from_pipeline_result("1.0", sample).to_dict()
        self.assertEqual(result, {"version": "1.0", **sample})

    def test_v11_pipeline_result_roundtrip(self):
        """Version 1.1 pipeline result serialises and flattens correctly."""
        from backend.models.care_plan import SimplifiedCarePlan

        sample = {"structured": True, "medications": ["metformin"]}
        result = SimplifiedCarePlan.from_pipeline_result("1.1", sample).to_dict()
        self.assertEqual(result, {"version": "1.1", **sample})

    # ------------------------------------------------------------------
    # from_dict reconstruction
    # ------------------------------------------------------------------

    def test_from_dict_reconstructs_correctly(self):
        """from_dict splits 'version' from the rest and builds the object."""
        from backend.models.care_plan import SimplifiedCarePlan

        flat = {"version": "1.2", **self.SAMPLE_V12}
        obj = SimplifiedCarePlan.from_dict(flat)
        self.assertEqual(obj.version, "1.2")
        self.assertEqual(obj.data, self.SAMPLE_V12)

    def test_from_dict_v10(self):
        """from_dict works for version 1.0."""
        from backend.models.care_plan import SimplifiedCarePlan

        flat = {"version": "1.0", "raw_text": "visit note"}
        obj = SimplifiedCarePlan.from_dict(flat)
        self.assertEqual(obj.version, "1.0")
        self.assertEqual(obj.data, {"raw_text": "visit note"})

    def test_from_dict_v11(self):
        """from_dict works for version 1.1."""
        from backend.models.care_plan import SimplifiedCarePlan

        flat = {"version": "1.1", "medications": ["aspirin"]}
        obj = SimplifiedCarePlan.from_dict(flat)
        self.assertEqual(obj.version, "1.1")
        self.assertEqual(obj.data, {"medications": ["aspirin"]})

    def test_full_roundtrip_v12(self):
        """Full round-trip: from_pipeline_result -> to_dict -> from_dict -> to_dict."""
        from backend.models.care_plan import SimplifiedCarePlan

        obj = SimplifiedCarePlan.from_pipeline_result("1.2", self.SAMPLE_V12)
        flat = obj.to_dict()
        reconstructed = SimplifiedCarePlan.from_dict(flat)
        self.assertEqual(reconstructed.version, "1.2")
        self.assertEqual(reconstructed.data, self.SAMPLE_V12)
        self.assertEqual(reconstructed.to_dict(), flat)

    def test_to_dict_flattening_no_nested_data_key(self):
        """to_dict must NOT produce a nested 'data' key."""
        from backend.models.care_plan import SimplifiedCarePlan

        obj = SimplifiedCarePlan.from_pipeline_result("1.2", self.SAMPLE_V12)
        d = obj.to_dict()
        self.assertNotIn("data", d)
        self.assertIn("doc_type", d)
        self.assertIn("diagnosis", d)
        self.assertIn("terms", d)

    def test_unknown_version_raises(self):
        """from_dict with an unregistered version must raise KeyError."""
        from backend.models.care_plan import SimplifiedCarePlan

        with self.assertRaises(KeyError):
            SimplifiedCarePlan.from_dict({"version": "9.9", "foo": "bar"})

    def test_registry_contains_all_three_versions(self):
        """All three versions must be registered in SimplifiedCarePlan._registry."""
        from backend.models.care_plan import SimplifiedCarePlan

        self.assertIn("1.0", SimplifiedCarePlan._registry)
        self.assertIn("1.1", SimplifiedCarePlan._registry)
        self.assertIn("1.2", SimplifiedCarePlan._registry)

    def test_all_versions_map_to_same_class(self):
        """All three registered versions must map to SimplifiedCarePlan."""
        from backend.models.care_plan import SimplifiedCarePlan

        for version in ("1.0", "1.1", "1.2"):
            self.assertIs(SimplifiedCarePlan._registry[version], SimplifiedCarePlan)

    def test_inherits_versioned_json_model(self):
        """SimplifiedCarePlan must be a VersionedJsonModel subclass."""
        from backend.models.base import VersionedJsonModel
        from backend.models.care_plan import SimplifiedCarePlan

        obj = SimplifiedCarePlan.from_pipeline_result("1.2", self.SAMPLE_V12)
        self.assertIsInstance(obj, VersionedJsonModel)

    def test_package_export(self):
        """SimplifiedCarePlan must be importable directly from backend.models."""
        from backend.models import SimplifiedCarePlan  # noqa: F401


if __name__ == "__main__":
    unittest.main()
