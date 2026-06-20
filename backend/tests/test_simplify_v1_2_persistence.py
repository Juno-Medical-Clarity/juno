import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import ANY, patch

from flask import Flask

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
for path in (PROJECT_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from routes import all_blueprints
from models.metrics import Metrics
import routes.care_plan as care_plan_module


class FakePipeline:
    def simplify_language_with_term_plan(self, text, substitution_candidates, preserve_terms, abbreviations):
        return f"simplified: {text}"

    def clarify_and_action(self, simplified, abbreviations):
        return f"clarified: {simplified}"

    def structure_appointment_note(self, clarified):
        return {"summary": clarified}


class CarePlanPersistenceTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        for blueprint in all_blueprints:
            app.register_blueprint(blueprint)
        self.client = app.test_client()

    def _events_from_response(self, response):
        events = []
        for block in response.get_data(as_text=True).strip().split("\n\n"):
            if block.startswith("data: "):
                events.append(json.loads(block.removeprefix("data: ")))
        return events

    def _events_from_chunks(self, chunks):
        events = []
        for chunk in chunks:
            if isinstance(chunk, tuple):
                continue  # skip __result__ sentinel
            for block in chunk.strip().split("\n\n"):
                if block.startswith("data: "):
                    events.append(json.loads(block.removeprefix("data: ")))
        return events

    def _docx_bytes(self, text):
        from docx import Document

        buffer = io.BytesIO()
        document = Document()
        document.add_paragraph(text)
        document.save(buffer)
        buffer.seek(0)
        return buffer

    @patch("routes.care_plan.save_care_plan_output")
    @patch("routes.care_plan.score_text", return_value={"composite": 70, "grade_estimate": 6.0, "label": "Patient-friendly", "word_count": 100, "dimensions": {"grade_level": {"score": 70, "raw": 6.0, "label": "Grade Level", "unit": "grade"}, "jargon_density": {"score": 70, "raw": 0.1, "label": "Jargon Density", "unit": "proportion"}, "sentence_complexity": {"score": 70, "raw": 12.0, "label": "Sentence Length", "unit": "words/sentence"}, "passive_voice": {"score": 70, "raw": 0.1, "label": "Active Voice", "unit": "passive ratio"}, "actionability": {"score": 70, "raw": 0.05, "label": "Actionability", "unit": "you-rate"}, "numeracy_clarity": {"score": 70, "raw": 1.0, "label": "Numeric Clarity", "unit": "vague count"}, "structural_clarity": {"score": 70, "raw": 30.0, "label": "Structure", "unit": "words/paragraph"}}})
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
    def test_run_care_plan_pipeline_direct_text_yields_steps_and_result_sentinel(
        self,
        _pipeline,
        _detect_terms,
        _glossary,
        _score,
        save_care_plan_output,
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

        # All string chunks should be step SSE events (not result events)
        str_chunks = [c for c in chunks if isinstance(c, str)]
        events = self._events_from_chunks(str_chunks)
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
        # The last chunk should be the __result__ sentinel tuple, not an SSE event
        tuple_chunks = [c for c in chunks if isinstance(c, tuple)]
        self.assertEqual(len(tuple_chunks), 1)
        self.assertEqual(tuple_chunks[0][0], "__result__")
        save_care_plan_output.assert_not_called()

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    @patch("routes.care_plan.save_care_plan_output", return_value="saved-123")
    @patch("routes.care_plan.upload_combined_pdf", return_value="gs://bucket/input.pdf")
    @patch("routes.care_plan.merge_pdfs", return_value=b"%PDF combined")
    @patch("routes.care_plan.score_text", return_value={"composite": 70, "grade_estimate": 6.0, "label": "Patient-friendly", "word_count": 100, "dimensions": {"grade_level": {"score": 70, "raw": 6.0, "label": "Grade Level", "unit": "grade"}, "jargon_density": {"score": 70, "raw": 0.1, "label": "Jargon Density", "unit": "proportion"}, "sentence_complexity": {"score": 70, "raw": 12.0, "label": "Sentence Length", "unit": "words/sentence"}, "passive_voice": {"score": 70, "raw": 0.1, "label": "Active Voice", "unit": "passive ratio"}, "actionability": {"score": 70, "raw": 0.05, "label": "Actionability", "unit": "you-rate"}, "numeracy_clarity": {"score": 70, "raw": 1.0, "label": "Numeric Clarity", "unit": "vague count"}, "structural_clarity": {"score": 70, "raw": 30.0, "label": "Structure", "unit": "words/paragraph"}}})
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
    def test_multi_file_input_is_concatenated_and_saved_after_result(
        self,
        _pipeline,
        _detect_terms,
        _glossary,
        _score,
        merge_pdfs,
        upload_combined_pdf,
        save_care_plan_output,
        _verify_token,
    ):
        response = self.client.post(
            "/care_plan",
            headers={"Authorization": "Bearer token"},
            data={
                "version": "v1-2",
                "files": [
                    (io.BytesIO(b"first note"), "a.txt"),
                    (io.BytesIO(b"second note"), "b.txt"),
                ]
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        events = self._events_from_response(response)
        result_event = events[-1]
        self.assertEqual(result_event["step"], "result")
        self.assertEqual(result_event["data"]["metrics"]["saved_id"], "saved-123")
        self.assertIsNotNone(result_event["data"]["metrics"]["session_id"])
        self.assertIsInstance(result_event["data"]["metrics"]["session_id"], str)
        self.assertIn("first note", result_event["data"]["care_plan"]["raw"]["text"])
        self.assertIn("second note", result_event["data"]["care_plan"]["raw"]["text"])
        self.assertIn("Source: a.txt", result_event["data"]["care_plan"]["raw"]["text"])
        self.assertIn("Source: b.txt", result_event["data"]["care_plan"]["raw"]["text"])

        merge_pdfs.assert_called_once()
        upload_combined_pdf.assert_called_once_with(b"%PDF combined", "user-1")
        save_care_plan_output.assert_called_once()
        saved_kwargs = save_care_plan_output.call_args.kwargs
        self.assertEqual(saved_kwargs["user_id"], "user-1")
        self.assertEqual(saved_kwargs["source_filename"], "a.txt, b.txt")
        self.assertEqual(saved_kwargs["input_pdf_gcs"], "gs://bucket/input.pdf")
        # Single-serialize: the persisted dict is the same object as the response payload
        persisted_output = saved_kwargs["output_data"]
        self.assertEqual(persisted_output["metrics"]["saved_id"], "saved-123")

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    @patch("routes.care_plan.save_care_plan_output", return_value="saved-123")
    @patch("routes.care_plan.upload_combined_pdf", return_value="gs://bucket/input.pdf")
    @patch("routes.care_plan.merge_pdfs", return_value=b"%PDF combined")
    @patch("routes.care_plan.score_text", return_value={"composite": 70, "grade_estimate": 6.0, "label": "Patient-friendly", "word_count": 100, "dimensions": {"grade_level": {"score": 70, "raw": 6.0, "label": "Grade Level", "unit": "grade"}, "jargon_density": {"score": 70, "raw": 0.1, "label": "Jargon Density", "unit": "proportion"}, "sentence_complexity": {"score": 70, "raw": 12.0, "label": "Sentence Length", "unit": "words/sentence"}, "passive_voice": {"score": 70, "raw": 0.1, "label": "Active Voice", "unit": "passive ratio"}, "actionability": {"score": 70, "raw": 0.05, "label": "Actionability", "unit": "you-rate"}, "numeracy_clarity": {"score": 70, "raw": 1.0, "label": "Numeric Clarity", "unit": "vague count"}, "structural_clarity": {"score": 70, "raw": 30.0, "label": "Structure", "unit": "words/paragraph"}}})
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
    def test_uploaded_docx_content_is_included_in_combined_pdf_artifact(
        self,
        _pipeline,
        _detect_terms,
        _glossary,
        _score,
        merge_pdfs,
        upload_combined_pdf,
        _save_care_plan_output,
        _verify_token,
    ):
        response = self.client.post(
            "/care_plan",
            headers={"Authorization": "Bearer token"},
            data={
                "version": "v1-2",
                "files": [(self._docx_bytes("docx clinical note"), "visit.docx")],
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self._events_from_response(response)
        merge_pdfs.assert_called_once_with([(b"docx clinical note", "visit.txt")])
        upload_combined_pdf.assert_called_once_with(b"%PDF combined", "user-1")

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_multi_file_upload_rejects_too_many_files(self, _verify_token):
        with self.assertLogs("utils.juno_logger", level="ERROR"):
            response = self.client.post(
                "/care_plan",
                headers={"Authorization": "Bearer token"},
                data={
                    "version": "v1-2",
                    "files": [
                        (io.BytesIO(f"note {index}".encode("utf-8")), f"{index}.txt")
                        for index in range(11)
                    ]
                },
                content_type="multipart/form-data",
            )
            events = self._events_from_response(response)

        self.assertEqual(events[-1]["step"], "error")
        self.assertIn("at most 10 files", events[-1]["error"])

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    @patch("routes.care_plan.MAX_AGGREGATE_FILE_BYTES", 10, create=True)
    @patch("routes.care_plan.V1_2Pipeline", return_value=FakePipeline())
    def test_multi_file_upload_rejects_aggregate_size_over_limit(
        self, _pipeline, _verify_token
    ):
        with self.assertLogs("utils.juno_logger", level="ERROR"):
            response = self.client.post(
                "/care_plan",
                headers={"Authorization": "Bearer token"},
                data={
                    "version": "v1-2",
                    "files": [
                        (io.BytesIO(b"abcdef"), "a.txt"),
                        (io.BytesIO(b"ghijkl"), "b.txt"),
                    ]
                },
                content_type="multipart/form-data",
            )
            events = self._events_from_response(response)

        self.assertEqual(events[-1]["step"], "error")
        self.assertIn("combined upload size exceeds", events[-1]["error"])

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    @patch("routes.care_plan.save_care_plan_output")
    @patch("routes.care_plan.upload_combined_pdf")
    @patch("routes.care_plan.merge_pdfs", return_value=b"%PDF combined")
    @patch("routes.care_plan._fetch_from_gcs", return_value=(b"stored note", "stored.txt"))
    @patch("routes.care_plan.score_text", return_value={"composite": 70, "grade_estimate": 6.0, "label": "Patient-friendly", "word_count": 100, "dimensions": {"grade_level": {"score": 70, "raw": 6.0, "label": "Grade Level", "unit": "grade"}, "jargon_density": {"score": 70, "raw": 0.1, "label": "Jargon Density", "unit": "proportion"}, "sentence_complexity": {"score": 70, "raw": 12.0, "label": "Sentence Length", "unit": "words/sentence"}, "passive_voice": {"score": 70, "raw": 0.1, "label": "Active Voice", "unit": "passive ratio"}, "actionability": {"score": 70, "raw": 0.05, "label": "Actionability", "unit": "you-rate"}, "numeracy_clarity": {"score": 70, "raw": 1.0, "label": "Numeric Clarity", "unit": "vague count"}, "structural_clarity": {"score": 70, "raw": 30.0, "label": "Structure", "unit": "words/paragraph"}}})
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
    def test_doc_id_input_is_processed_but_not_persisted(
        self,
        _pipeline,
        _detect_terms,
        _glossary,
        _score,
        _fetch_from_gcs,
        merge_pdfs,
        upload_combined_pdf,
        save_care_plan_output,
        _verify_token,
    ):
        response = self.client.post(
            "/care_plan",
            headers={"Authorization": "Bearer token"},
            data={"version": "v1-2", "doc_id": "legacy-doc"},
        )

        events = self._events_from_response(response)
        result_event = events[-1]
        self.assertEqual(result_event["step"], "result")
        self.assertIn("stored note", result_event["data"]["care_plan"]["raw"]["text"])
        self.assertIsNone(result_event["data"]["metrics"]["saved_id"])
        self.assertIsNotNone(result_event["data"]["metrics"]["session_id"])
        self.assertIsInstance(result_event["data"]["metrics"]["session_id"], str)
        merge_pdfs.assert_called_once_with(ANY)
        upload_combined_pdf.assert_not_called()
        save_care_plan_output.assert_not_called()

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    @patch("routes.care_plan.save_care_plan_output", side_effect=RuntimeError("no firestore"))
    @patch("routes.care_plan.score_text", return_value={"composite": 70, "grade_estimate": 6.0, "label": "Patient-friendly", "word_count": 100, "dimensions": {"grade_level": {"score": 70, "raw": 6.0, "label": "Grade Level", "unit": "grade"}, "jargon_density": {"score": 70, "raw": 0.1, "label": "Jargon Density", "unit": "proportion"}, "sentence_complexity": {"score": 70, "raw": 12.0, "label": "Sentence Length", "unit": "words/sentence"}, "passive_voice": {"score": 70, "raw": 0.1, "label": "Active Voice", "unit": "passive ratio"}, "actionability": {"score": 70, "raw": 0.05, "label": "Actionability", "unit": "you-rate"}, "numeracy_clarity": {"score": 70, "raw": 1.0, "label": "Numeric Clarity", "unit": "vague count"}, "structural_clarity": {"score": 70, "raw": 30.0, "label": "Structure", "unit": "words/paragraph"}}})
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
    def test_save_failure_returns_result_without_saved_id(
        self,
        _pipeline,
        _detect_terms,
        _glossary,
        _score,
        save_care_plan_output,
        _verify_token,
    ):
        with self.assertLogs("utils.juno_logger", level="ERROR") as logs:
            response = self.client.post(
                "/care_plan",
                headers={"Authorization": "Bearer token"},
                data={"version": "v1-2", "text": "plain note"},
            )
            events = self._events_from_response(response)

        self.assertEqual(response.status_code, 200)
        result_event = events[-1]
        self.assertEqual(result_event["step"], "result")
        self.assertIsNone(result_event["data"]["metrics"]["saved_id"])
        self.assertIsNotNone(result_event["data"]["metrics"]["session_id"])
        self.assertIsInstance(result_event["data"]["metrics"]["session_id"], str)
        save_care_plan_output.assert_called_once()
        self.assertIn("failed to save output", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
