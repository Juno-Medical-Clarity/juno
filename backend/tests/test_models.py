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

    def test_missing_batch_dataset_fields_roundtrip_as_none(self):
        """Existing serialized Input dictionaries leave batch metadata unset."""
        reconstructed = Input.from_dict(
            {
                "mode": "text",
                "text": "Hello, world!",
                "doc_id": None,
                "files": [],
            }
        )

        self.assertIsNone(reconstructed.dataset_group)
        self.assertIsNone(reconstructed.dataset_input)
        self.assertIsNone(reconstructed.selected_files)
        self.assertIsNone(reconstructed.batch_group_id)

        d = reconstructed.to_dict()
        self.assertIsNone(d["dataset_group"])
        self.assertIsNone(d["dataset_input"])
        self.assertIsNone(d["selected_files"])
        self.assertIsNone(d["batch_group_id"])

        self.assertEqual(Input.from_dict(d), reconstructed)

    def test_from_batch_dataset_roundtrip(self):
        """Input.from_batch_dataset preserves dataset metadata through JSON shape."""
        inp = Input.from_batch_dataset(
            text="Dataset text",
            dataset_group="DocConv",
            dataset_input="input-1",
            selected_files=["visit.pdf", "notes.txt"],
            batch_group_id="DocConv-20260616T120000Z",
        )

        self.assertEqual(inp.mode, "text")
        self.assertEqual(inp.text, "Dataset text")
        self.assertIsNone(inp.doc_id)
        self.assertEqual(inp.files, [])
        self.assertEqual(inp.dataset_group, "DocConv")
        self.assertEqual(inp.dataset_input, "input-1")
        self.assertEqual(inp.selected_files, ["visit.pdf", "notes.txt"])
        self.assertEqual(inp.batch_group_id, "DocConv-20260616T120000Z")

        d = inp.to_dict()
        self.assertEqual(
            d,
            {
                "mode": "text",
                "text": "Dataset text",
                "doc_id": None,
                "files": [],
                "dataset_group": "DocConv",
                "dataset_input": "input-1",
                "selected_files": ["visit.pdf", "notes.txt"],
                "batch_group_id": "DocConv-20260616T120000Z",
            },
        )
        self.assertEqual(Input.from_dict(d), inp)


class TestGrading(unittest.TestCase):
    """Tests for the Grading model."""

    def test_default_to_dict(self):
        """Grading() produces the correct empty/enabled shape."""
        self.assertEqual(Grading().to_dict(), {"entries": [], "enabled": True, "graded_at": None})

    def test_roundtrip(self):
        """Grading round-trips correctly through to_dict/from_dict."""
        from backend.models.grading import GradingEntry
        entry = GradingEntry(name="smog", target="after", grade=72.0,
                             grade_breakdown={"grade": 9.5, "insufficient_sample": False},
                             reasoning="SMOG grade")
        original = Grading(entries=[entry], enabled=True, graded_at="2026-01-01T00:00:00+00:00")
        d = original.to_dict()
        self.assertEqual(d["entries"][0]["name"], "smog")
        self.assertEqual(d["enabled"], True)
        reconstructed = Grading.from_dict(d)
        self.assertEqual(reconstructed.entries[0].name, "smog")
        self.assertEqual(reconstructed.graded_at, "2026-01-01T00:00:00+00:00")


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
        """from_dict with an unregistered version must raise descriptive ValueError."""
        from backend.models.care_plan import SimplifiedCarePlan

        with self.assertRaisesRegex(
            ValueError,
            "Unknown version '9\\.9' for SimplifiedCarePlan\\. "
            "Available versions: 1\\.0, 1\\.1, 1\\.2",
        ):
            SimplifiedCarePlan.from_dict({"version": "9.9", "foo": "bar"})

    def test_from_dict_missing_version_raises_value_error(self):
        """from_dict with no 'version' key must raise ValueError."""
        from backend.models.care_plan import SimplifiedCarePlan

        with self.assertRaises(ValueError):
            SimplifiedCarePlan.from_dict({"doc_type": "appointment_note"})

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


class TestSimplifyOutput(unittest.TestCase):
    """Tests for SimplifyOutput envelope and is_legacy_shape helper."""

    def _make_output(self):
        """Build a representative SimplifyOutput instance."""
        from backend.models.care_plan import SimplifiedCarePlan
        from backend.models.envelope import SimplifyOutput

        metrics = Metrics(
            session_id="sess-001",
            pipeline_version="v1-2",
            input_type="file",
            created_at="2026-06-16T12:00:00+00:00",
            total_duration_ms=4213.5,
            step_durations_ms={"find_medical_terms": 812.1},
            saved_id="doc-42",
        )
        inp = Input(
            mode="file",
            files=[InputFile("visit.pdf", "application/pdf", 88210)],
        )
        grading = Grading(entries=[])
        care_plan = SimplifiedCarePlan.from_pipeline_result(
            "1.2",
            {"doc_type": "appointment_note", "diagnosis": {"primary": "hypertension"}},
        )
        return SimplifyOutput(
            metrics=metrics,
            input=inp,
            grading=grading,
            simplified_care_plan=care_plan,
        )

    def test_to_dict_produces_exact_nested_shape(self):
        """SimplifyOutput.to_dict() must produce the PRD §5 'After' top-level shape."""
        from backend.models.envelope import SimplifyOutput

        output = self._make_output()
        d = output.to_dict()

        # Top-level keys
        self.assertIn("metrics", d)
        self.assertIn("input", d)
        self.assertIn("grading", d)
        self.assertIn("simplified_care_plan", d)
        self.assertEqual(set(d.keys()), {"metrics", "input", "grading", "simplified_care_plan"})

    def test_to_dict_metrics_shape(self):
        """metrics sub-dict must match Metrics.to_dict() output."""
        output = self._make_output()
        d = output.to_dict()

        self.assertEqual(d["metrics"]["session_id"], "sess-001")
        self.assertEqual(d["metrics"]["pipeline_version"], "v1-2")
        self.assertEqual(d["metrics"]["input_type"], "file")
        self.assertEqual(d["metrics"]["total_duration_ms"], 4213.5)
        self.assertEqual(d["metrics"]["step_durations_ms"], {"find_medical_terms": 812.1})
        self.assertEqual(d["metrics"]["saved_id"], "doc-42")

    def test_to_dict_input_shape(self):
        """input sub-dict must contain mode=file and one file entry."""
        output = self._make_output()
        d = output.to_dict()

        self.assertEqual(d["input"]["mode"], "file")
        self.assertEqual(len(d["input"]["files"]), 1)
        self.assertEqual(d["input"]["files"][0]["filename"], "visit.pdf")
        self.assertEqual(d["input"]["files"][0]["content_type"], "application/pdf")
        self.assertEqual(d["input"]["files"][0]["size_bytes"], 88210)
        self.assertIsNone(d["input"]["text"])
        self.assertIsNone(d["input"]["doc_id"])

    def test_to_dict_grading_shape(self):
        """grading sub-dict must have entries, enabled, and graded_at keys."""
        output = self._make_output()
        d = output.to_dict()
        self.assertEqual(d["grading"], {"entries": [], "enabled": True, "graded_at": None})

    def test_to_dict_care_plan_shape(self):
        """simplified_care_plan sub-dict must be flat (no nested 'data' key)."""
        output = self._make_output()
        d = output.to_dict()

        cp = d["simplified_care_plan"]
        self.assertEqual(cp["version"], "1.2")
        self.assertEqual(cp["doc_type"], "appointment_note")
        self.assertEqual(cp["diagnosis"], {"primary": "hypertension"})
        self.assertNotIn("data", cp)

    def test_package_exports(self):
        """SimplifyOutput and is_legacy_shape must be importable from backend.models."""
        from backend.models import SimplifyOutput, is_legacy_shape  # noqa: F401

    def test_is_legacy_shape_returns_true_for_flat_dict(self):
        """is_legacy_shape must return True when 'simplified_care_plan' key is absent."""
        from backend.models.envelope import is_legacy_shape

        flat_legacy = {"session_id": "s", "doc_type": "note", "diagnosis": {}}
        self.assertTrue(is_legacy_shape(flat_legacy))

    def test_is_legacy_shape_returns_false_for_new_shape(self):
        """is_legacy_shape must return False when 'simplified_care_plan' key is present."""
        from backend.models.envelope import is_legacy_shape

        new_shape = {
            "metrics": {},
            "input": {},
            "grading": {},
            "simplified_care_plan": {},
        }
        self.assertFalse(is_legacy_shape(new_shape))

    def test_is_legacy_shape_empty_dict(self):
        """is_legacy_shape must return True for an empty dict."""
        from backend.models.envelope import is_legacy_shape

        self.assertTrue(is_legacy_shape({}))

    def test_simplify_output_inherits_json_model(self):
        """SimplifyOutput must be a JsonModel subclass."""
        from backend.models.base import JsonModel
        from backend.models.envelope import SimplifyOutput

        output = self._make_output()
        self.assertIsInstance(output, JsonModel)


if __name__ == "__main__":
    unittest.main()
