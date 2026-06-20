import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class SaveOutputTest(unittest.TestCase):
    @patch("utils.firebase.uuid.uuid4")
    @patch("utils.firebase.firestore.client")
    def test_save_care_plan_output_persists_raw_and_uses_aware_datetimes(
        self, firestore_client, uuid4
    ):
        from utils.firebase import save_care_plan_output

        uuid4.return_value = "output-123"
        doc_ref = MagicMock()
        firestore_client.return_value.collection.return_value.document.return_value = doc_ref

        output_data = {
            "care_plan": {
                "summary": "ok",
                "raw": {"text": "secret-ish raw text"},
            }
        }
        saved_id = save_care_plan_output(
            user_id="user-1",
            name="Visit summary",
            source_filename="a.pdf, b.txt",
            input_pdf_gcs="gs://bucket/care_plan/user-1/inputs/input.pdf",
            output_data=output_data,
        )

        self.assertEqual(saved_id, "output-123")
        # Verify Firestore collection is "care_plan_outputs"
        firestore_client.return_value.collection.assert_called_with("care_plan_outputs")
        payload = doc_ref.set.call_args.args[0]
        self.assertIs(payload["output_data"], output_data)
        self.assertEqual(
            payload["output_data"]["care_plan"]["raw"],
            {"text": "secret-ish raw text"},
        )
        self.assertEqual(payload["uid"], "user-1")
        self.assertEqual(payload["source_filename"], "a.pdf, b.txt")
        self.assertIsInstance(payload["created_at"], datetime)
        self.assertIsNotNone(payload["created_at"].tzinfo)
        self.assertEqual(payload["created_at"].tzinfo, timezone.utc)
        self.assertEqual(payload["updated_at"], payload["created_at"])

    @patch("utils.firebase.uuid.uuid4")
    @patch("utils.firebase.firestore.client")
    def test_save_care_plan_output_accepts_batch_metadata(
        self, firestore_client, uuid4
    ):
        from utils.firebase import save_care_plan_output

        uuid4.return_value = "output-123"
        doc_ref = MagicMock()
        firestore_client.return_value.collection.return_value.document.return_value = doc_ref

        save_care_plan_output(
            user_id="user-1",
            name="Visit summary",
            source_filename="notes.txt",
            input_pdf_gcs=None,
            output_data={"summary": "ok"},
            dataset_group="DocConv",
            batch_group_id="DocConv-20260616153012",
        )

        payload = doc_ref.set.call_args.args[0]
        self.assertEqual(payload["dataset_group"], "DocConv")
        self.assertEqual(payload["batch_group_id"], "DocConv-20260616153012")

    @patch.dict("routes.care_plan.os.environ", {"GCP_BUCKET_NAME": "bucket", "GCP_PROJECT_ID": "project"})
    @patch("routes.care_plan.uuid.uuid4")
    @patch("routes.care_plan.gcs.Client")
    def test_upload_combined_pdf_uses_care_plan_gcs_path(self, gcs_client, uuid4):
        from routes.care_plan import upload_combined_pdf

        uuid4.return_value = "input-456"
        blob = MagicMock()
        bucket = gcs_client.return_value.bucket.return_value
        bucket.blob.return_value = blob

        uri = upload_combined_pdf(b"%PDF", "user-1")

        self.assertEqual(uri, "gs://bucket/care_plan/user-1/inputs/input-456.pdf")
        bucket.blob.assert_called_once_with("care_plan/user-1/inputs/input-456.pdf")
        blob.upload_from_string.assert_called_once_with(
            b"%PDF", content_type="application/pdf"
        )


if __name__ == "__main__":
    unittest.main()
