"""Tests for backend.models — Metrics and Input models."""

import io
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from models.grading import Grading
from models.input import Input, InputFile
from models.metrics import Metrics


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
            saved_id="doc-999",
        )
        d = original.to_dict()

        expected = {
            "session_id": "sess-xyz",
            "pipeline_version": "v1-2",
            "input_type": "file",
            "created_at": "2026-06-16T12:00:00+00:00",
            "total_duration_ms": 4213.5,
            "saved_id": "doc-999",
        }
        self.assertEqual(d, expected)

        reconstructed = Metrics.from_dict(d)
        self.assertEqual(reconstructed, original)

    def test_mutable_fields_can_be_set_post_creation(self):
        """Metrics is not frozen — duration and saved_id can be mutated."""
        m = Metrics.start("s", "v1", "doc_id")
        m.total_duration_ms = 100.0
        m.saved_id = "doc-1"

        self.assertEqual(m.total_duration_ms, 100.0)
        self.assertEqual(m.saved_id, "doc-1")

    def test_metrics_inherits_json_model(self):
        """Metrics must inherit from JsonModel, not VersionedModel."""
        from models.base import JsonModel, VersionedModel

        self.assertIsInstance(Metrics.start("s", "v1", "text"), JsonModel)
        self.assertNotIsInstance(Metrics.start("s", "v1", "text"), VersionedModel)


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
        from models.base import JsonModel
        self.assertIsInstance(
            InputFile(filename="f.pdf", content_type="application/pdf", size_bytes=100),
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
                InputFile(filename="a.pdf", content_type="application/pdf", size_bytes=1024),
                InputFile(filename="b.txt", content_type="text/plain", size_bytes=256),
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
        from models.base import JsonModel
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
        from models.grading import GradingEntry
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


class TestCarePlanV1_2(unittest.TestCase):
    """Tests for the current CarePlan v1.2 versioned model."""

    SAMPLE_V12 = {
        "doc_type": "care_plan",
        "summary": "Take blood pressure medicine daily.",
        "terms": {
            "hypertension": {
                "definition": "High blood pressure.",
                "source": "provider note",
            }
        },
    }

    def test_from_pipeline_result_dispatches_to_v12_model(self):
        """CarePlan.from_pipeline_result('1.2', sample) validates as CarePlanV1_2."""
        from models.care_plan import CarePlan, CarePlanV1_2

        result = CarePlan.from_pipeline_result("1.2", self.SAMPLE_V12)

        self.assertIsInstance(result, CarePlanV1_2)
        self.assertEqual(result.to_dict()["version"], "1.2")
        self.assertEqual(result.to_dict()["doc_type"], "care_plan")
        self.assertEqual(result.to_dict()["summary"], self.SAMPLE_V12["summary"])

    def test_from_dict_roundtrip(self):
        """CarePlan.from_dict dispatches and round-trips through the v1.2 shape."""
        from models.care_plan import CarePlan, CarePlanV1_2

        flat = {"version": "1.2", **self.SAMPLE_V12}
        obj = CarePlan.from_dict(flat)

        self.assertIsInstance(obj, CarePlanV1_2)
        self.assertEqual(CarePlan.from_dict(obj.to_dict()), obj)

    def test_unknown_version_raises(self):
        """from_dict with an unregistered version must raise descriptive ValueError."""
        from models.care_plan import CarePlan

        with self.assertRaisesRegex(ValueError, "Unknown version '9\\.9' for CarePlan"):
            CarePlan.from_dict({"version": "9.9", "doc_type": "care_plan"})

    def test_registry_contains_v12_model(self):
        """The v1.2 model must be registered on the CarePlan family."""
        from models.care_plan import CarePlan, CarePlanV1_2

        self.assertIs(CarePlan._registry["1.2"], CarePlanV1_2)

    def test_inherits_versioned_model(self):
        """CarePlanV1_2 must be a VersionedModel subclass."""
        from models.base import VersionedModel
        from models.care_plan import CarePlan

        obj = CarePlan.from_pipeline_result("1.2", self.SAMPLE_V12)
        self.assertIsInstance(obj, VersionedModel)

    def test_package_export(self):
        """CarePlan and CarePlanV1_2 must be importable directly from models."""
        from models import CarePlan, CarePlanV1_2  # noqa: F401


class TestCarePlanInternal(unittest.TestCase):
    """Tests for CarePlanInternal envelope and is_legacy_shape helper."""

    def _make_output(self):
        """Build a representative CarePlanInternal instance."""
        from models.care_plan import CarePlan
        from models.envelope import CarePlanInternal

        metrics = Metrics(
            session_id="sess-001",
            pipeline_version="v1-2",
            input_type="file",
            created_at="2026-06-16T12:00:00+00:00",
            total_duration_ms=4213.5,
            saved_id="doc-42",
        )
        inp = Input(
            mode="file",
            files=[
                InputFile(
                    filename="visit.pdf",
                    content_type="application/pdf",
                    size_bytes=88210,
                )
            ],
        )
        grading = Grading(entries=[])
        care_plan = CarePlan.from_pipeline_result(
            "1.2",
            {"doc_type": "care_plan", "summary": "Take medicine daily."},
        )
        return CarePlanInternal(
            metrics=metrics,
            input=inp,
            grading=grading,
            care_plan=care_plan,
        )

    def test_to_dict_produces_exact_nested_shape(self):
        """CarePlanInternal.to_dict() must produce the current top-level shape."""

        output = self._make_output()
        d = output.to_dict()

        # Top-level keys
        self.assertIn("metrics", d)
        self.assertIn("input", d)
        self.assertIn("grading", d)
        self.assertIn("care_plan", d)
        self.assertIn("before_score", d)
        self.assertIn("after_score", d)
        self.assertEqual(
            set(d.keys()),
            {"metrics", "input", "grading", "care_plan", "before_score", "after_score"},
        )
        self.assertNotIn("simplified_care_plan", d)

    def test_to_dict_metrics_shape(self):
        """metrics sub-dict must match Metrics.to_dict() output."""
        output = self._make_output()
        d = output.to_dict()

        self.assertEqual(d["metrics"]["session_id"], "sess-001")
        self.assertEqual(d["metrics"]["pipeline_version"], "v1-2")
        self.assertEqual(d["metrics"]["input_type"], "file")
        self.assertEqual(d["metrics"]["total_duration_ms"], 4213.5)
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
        """care_plan sub-dict must be the v1.2 care-plan shape."""
        output = self._make_output()
        d = output.to_dict()

        cp = d["care_plan"]
        self.assertEqual(cp["version"], "1.2")
        self.assertEqual(cp["doc_type"], "care_plan")
        self.assertEqual(cp["summary"], "Take medicine daily.")
        self.assertNotIn("data", cp)

    def test_package_exports(self):
        """CarePlanInternal and is_legacy_shape must be importable from models."""
        from models import CarePlanInternal, is_legacy_shape  # noqa: F401

    def test_is_legacy_shape_returns_true_for_flat_dict(self):
        """is_legacy_shape must return True when 'care_plan' key is absent."""
        from models.envelope import is_legacy_shape

        flat_legacy = {"session_id": "s", "doc_type": "note", "diagnosis": {}}
        self.assertTrue(is_legacy_shape(flat_legacy))

    def test_is_legacy_shape_returns_false_for_new_shape(self):
        """is_legacy_shape must return False when 'care_plan' key is present."""
        from models.envelope import is_legacy_shape

        new_shape = {
            "metrics": {},
            "input": {},
            "grading": {},
            "care_plan": {},
        }
        self.assertFalse(is_legacy_shape(new_shape))

    def test_is_legacy_shape_empty_dict(self):
        """is_legacy_shape must return True for an empty dict."""
        from models.envelope import is_legacy_shape

        self.assertTrue(is_legacy_shape({}))

    def test_care_plan_internal_inherits_json_model(self):
        """CarePlanInternal must be a JsonModel subclass."""
        from models.base import JsonModel

        output = self._make_output()
        self.assertIsInstance(output, JsonModel)


if __name__ == "__main__":
    unittest.main()
