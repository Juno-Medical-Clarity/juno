from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


@patch("utils.firebase.uuid.uuid4")
@patch("utils.firebase.firestore.client")
def test_save_care_plan_output_persists_raw_and_uses_aware_datetimes(
    firestore_client, uuid4
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
        output_data=output_data,
    )

    assert saved_id == "output-123"
    # Verify Firestore collection is "care_plan_outputs"
    firestore_client.return_value.collection.assert_called_with("care_plan_outputs")
    payload = doc_ref.set.call_args.args[0]
    assert payload["output_data"] is output_data
    assert payload["output_data"]["care_plan"]["raw"] == {"text": "secret-ish raw text"}
    assert payload["uid"] == "user-1"
    assert payload["source_filename"] == "a.pdf, b.txt"
    assert isinstance(payload["created_at"], datetime)
    assert payload["created_at"].tzinfo is not None
    assert payload["created_at"].tzinfo == timezone.utc
    assert payload["updated_at"] == payload["created_at"]


@patch("utils.firebase.uuid.uuid4")
@patch("utils.firebase.firestore.client")
def test_save_care_plan_output_accepts_batch_metadata(
    firestore_client, uuid4
):
    from utils.firebase import save_care_plan_output

    uuid4.return_value = "output-123"
    doc_ref = MagicMock()
    firestore_client.return_value.collection.return_value.document.return_value = doc_ref

    save_care_plan_output(
        user_id="user-1",
        name="Visit summary",
        source_filename="notes.txt",
        output_data={"summary": "ok"},
        dataset_group="DocConv",
        batch_group_id="DocConv-20260616153012",
    )

    payload = doc_ref.set.call_args.args[0]
    assert payload["dataset_group"] == "DocConv"
    assert payload["batch_group_id"] == "DocConv-20260616153012"


@patch.dict("routes.care_plan.os.environ", {"GCP_BUCKET_NAME": "bucket", "GCP_PROJECT_ID": "project"})
@patch("routes.care_plan.uuid.uuid4")
@patch("routes.care_plan.get_gcs_bucket")
def test_upload_combined_pdf_uses_care_plan_gcs_path(get_gcs_bucket, uuid4):
    from routes.care_plan import upload_combined_pdf

    uuid4.return_value = "input-456"
    blob = MagicMock()
    bucket = get_gcs_bucket.return_value
    bucket.blob.return_value = blob

    uri = upload_combined_pdf(b"%PDF", "user-1")

    assert uri == "gs://bucket/care_plan/user-1/inputs/input-456.pdf"
    get_gcs_bucket.assert_called_once_with("bucket")
    bucket.blob.assert_called_once_with("care_plan/user-1/inputs/input-456.pdf")
    blob.upload_from_string.assert_called_once_with(
        b"%PDF", content_type="application/pdf"
    )
