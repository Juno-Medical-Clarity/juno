import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routes.simplify_v1_2 import simplify_v1_2_bp


class FakePipeline:
    def simplify_language_with_term_plan(self, text, substitution_candidates, preserve_terms, abbreviations):
        return f"simplified: {text}"

    def clarify_and_action(self, simplified, abbreviations):
        return f"clarified: {simplified}"

    def structure_appointment_note(self, clarified):
        return {"summary": clarified}


class SimplifyV12PersistenceTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(simplify_v1_2_bp)
        self.client = app.test_client()

    def _events_from_response(self, response):
        events = []
        for block in response.get_data(as_text=True).strip().split("\n\n"):
            if block.startswith("data: "):
                events.append(json.loads(block.removeprefix("data: ")))
        return events

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    @patch("routes.simplify_v1_2.save_simplify_output", return_value="saved-123")
    @patch("routes.simplify_v1_2.upload_combined_pdf", return_value="gs://bucket/input.pdf")
    @patch("routes.simplify_v1_2.merge_pdfs", return_value=b"%PDF combined")
    @patch("routes.simplify_v1_2.score_text", return_value={"score": 1})
    @patch("routes.simplify_v1_2.build_glossary_from_simplified_text", return_value=[])
    @patch(
        "routes.simplify_v1_2.detect_terms",
        return_value={
            "substitution_candidates": [],
            "preserve_and_define_terms": [],
            "abbreviations": [],
        },
    )
    @patch("routes.simplify_v1_2.V1_2Pipeline", return_value=FakePipeline())
    def test_multi_file_input_is_concatenated_and_saved_after_result(
        self,
        _pipeline,
        _detect_terms,
        _glossary,
        _score,
        merge_pdfs,
        upload_combined_pdf,
        save_simplify_output,
        _verify_token,
    ):
        response = self.client.post(
            "/simplify/v1-2",
            headers={"Authorization": "Bearer token"},
            data={
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
        self.assertEqual(result_event["data"]["saved_id"], "saved-123")
        self.assertIn("first note", result_event["data"]["raw"]["text"])
        self.assertIn("second note", result_event["data"]["raw"]["text"])
        self.assertIn("Source: a.txt", result_event["data"]["raw"]["text"])
        self.assertIn("Source: b.txt", result_event["data"]["raw"]["text"])

        merge_pdfs.assert_called_once()
        upload_combined_pdf.assert_called_once_with(b"%PDF combined", "user-1")
        save_simplify_output.assert_called_once()
        saved_kwargs = save_simplify_output.call_args.kwargs
        self.assertEqual(saved_kwargs["user_id"], "user-1")
        self.assertEqual(saved_kwargs["source_filename"], "a.txt, b.txt")
        self.assertEqual(saved_kwargs["input_pdf_gcs"], "gs://bucket/input.pdf")

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    @patch("routes.simplify_v1_2.save_simplify_output", side_effect=RuntimeError("no firestore"))
    @patch("routes.simplify_v1_2.score_text", return_value={"score": 1})
    @patch("routes.simplify_v1_2.build_glossary_from_simplified_text", return_value=[])
    @patch(
        "routes.simplify_v1_2.detect_terms",
        return_value={
            "substitution_candidates": [],
            "preserve_and_define_terms": [],
            "abbreviations": [],
        },
    )
    @patch("routes.simplify_v1_2.V1_2Pipeline", return_value=FakePipeline())
    def test_save_failure_returns_result_without_saved_id(
        self,
        _pipeline,
        _detect_terms,
        _glossary,
        _score,
        save_simplify_output,
        _verify_token,
    ):
        with self.assertLogs("routes.simplify_v1_2", level="ERROR") as logs:
            response = self.client.post(
                "/simplify/v1-2",
                headers={"Authorization": "Bearer token"},
                data={"text": "plain note"},
            )
            events = self._events_from_response(response)

        self.assertEqual(response.status_code, 200)
        result_event = events[-1]
        self.assertEqual(result_event["step"], "result")
        self.assertNotIn("saved_id", result_event["data"])
        save_simplify_output.assert_called_once()
        self.assertIn("failed to save output", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
