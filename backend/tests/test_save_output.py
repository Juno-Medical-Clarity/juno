import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class SaveOutputTest(unittest.TestCase):
    @patch("utils.save_output.uuid.uuid4")
    @patch("utils.save_output.firestore.client")
    def test_save_simplify_output_strips_raw_and_uses_aware_datetimes(
        self, firestore_client, uuid4
    ):
        from utils.save_output import save_simplify_output

        uuid4.return_value = "output-123"
        doc_ref = MagicMock()
        firestore_client.return_value.collection.return_value.document.return_value = doc_ref

        saved_id = save_simplify_output(
            user_id="user-1",
            name="Visit summary",
            source_filename="a.pdf, b.txt",
            input_pdf_gcs="gs://bucket/simplify/user-1/inputs/input.pdf",
            output_data={"summary": "ok", "raw": {"text": "secret-ish raw text"}},
        )

        self.assertEqual(saved_id, "output-123")
        payload = doc_ref.set.call_args.args[0]
        self.assertEqual(payload["output_data"], {"summary": "ok"})
        self.assertEqual(payload["uid"], "user-1")
        self.assertEqual(payload["source_filename"], "a.pdf, b.txt")
        self.assertIsInstance(payload["created_at"], datetime)
        self.assertIsNotNone(payload["created_at"].tzinfo)
        self.assertEqual(payload["created_at"].tzinfo, timezone.utc)
        self.assertEqual(payload["updated_at"], payload["created_at"])

    @patch.dict("utils.save_output.os.environ", {"GCP_BUCKET_NAME": "bucket", "GCP_PROJECT_ID": "project"})
    @patch("utils.save_output.uuid.uuid4")
    @patch("utils.save_output.gcs.Client")
    def test_upload_combined_pdf_uses_expected_gcs_path(self, gcs_client, uuid4):
        from utils.save_output import upload_combined_pdf

        uuid4.return_value = "input-456"
        blob = MagicMock()
        bucket = gcs_client.return_value.bucket.return_value
        bucket.blob.return_value = blob

        uri = upload_combined_pdf(b"%PDF", "user-1")

        self.assertEqual(uri, "gs://bucket/simplify/user-1/inputs/input-456.pdf")
        bucket.blob.assert_called_once_with("simplify/user-1/inputs/input-456.pdf")
        blob.upload_from_string.assert_called_once_with(
            b"%PDF", content_type="application/pdf"
        )


if __name__ == "__main__":
    unittest.main()
