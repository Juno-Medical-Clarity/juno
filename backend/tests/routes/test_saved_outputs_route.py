from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


def _make_doc(doc_id: str, data: dict) -> MagicMock:
    """Return a mock Firestore document snapshot."""
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data
    return doc


def _make_owned_doc(data: dict) -> MagicMock:
    """Return a doc that passes ownership check (uid=user-1, exists=True)."""
    doc = _make_doc("doc-1", {"uid": "user-1", **data})
    doc.exists = True
    return doc


def _wire_get_owned(mock_firestore_client, doc: MagicMock):
    """Wire mock_firestore_client so get_owned_doc_or_403 fetches `doc`."""
    mock_db = MagicMock()
    mock_firestore_client.return_value = mock_db
    mock_db.collection.return_value.document.return_value.get.return_value = doc
    return mock_db


# ---------------------------------------------------------------------------
# get_input_pdf_url — tolerant read tests
# ---------------------------------------------------------------------------


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
@patch("routes.saved_outputs.firestore.client")
@patch("routes.saved_outputs.gcs.Client")
@patch("routes.saved_outputs._BUCKET_NAME", "my-bucket")
def test_get_input_pdf_url_new_path(mock_gcs_client, mock_firestore_client, _verify_token, client):
    """Doc with output_data.input.pdf_gcs_url set → uses new path, returns signed URL."""
    doc = _make_owned_doc({
        "output_data": {"input": {"pdf_gcs_url": "gs://my-bucket/care_plan/user-1/inputs/abc.pdf"}},
    })
    _wire_get_owned(mock_firestore_client, doc)

    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = "https://signed.url/new-path"
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_gcs_client.return_value.bucket.return_value = mock_bucket

    response = client.get(
        "/care_plan/saved/doc-1/input-pdf-url",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 200
    assert response.get_json()["url"] == "https://signed.url/new-path"
    mock_bucket.blob.assert_called_with("care_plan/user-1/inputs/abc.pdf")


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
@patch("routes.saved_outputs.firestore.client")
@patch("routes.saved_outputs.gcs.Client")
@patch("routes.saved_outputs._BUCKET_NAME", "my-bucket")
def test_get_input_pdf_url_legacy_fallback(mock_gcs_client, mock_firestore_client, _verify_token, client):
    """Doc with only top-level input_pdf_gcs set (legacy) → uses fallback, returns URL."""
    doc = _make_owned_doc({
        "input_pdf_gcs": "gs://my-bucket/care_plan/user-1/inputs/legacy.pdf",
        # no output_data.input.pdf_gcs_url
    })
    _wire_get_owned(mock_firestore_client, doc)

    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = "https://signed.url/legacy"
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_gcs_client.return_value.bucket.return_value = mock_bucket

    response = client.get(
        "/care_plan/saved/doc-1/input-pdf-url",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 200
    assert response.get_json()["url"] == "https://signed.url/legacy"
    mock_bucket.blob.assert_called_with("care_plan/user-1/inputs/legacy.pdf")


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
@patch("routes.saved_outputs.firestore.client")
@patch("routes.saved_outputs.gcs.Client")
@patch("routes.saved_outputs._BUCKET_NAME", "my-bucket")
def test_get_input_pdf_url_new_path_takes_priority(mock_gcs_client, mock_firestore_client, _verify_token, client):
    """Doc with both fields set → new path (output_data.input.pdf_gcs_url) takes priority."""
    doc = _make_owned_doc({
        "output_data": {"input": {"pdf_gcs_url": "gs://my-bucket/care_plan/user-1/inputs/new.pdf"}},
        "input_pdf_gcs": "gs://my-bucket/care_plan/user-1/inputs/legacy.pdf",
    })
    _wire_get_owned(mock_firestore_client, doc)

    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = "https://signed.url/priority"
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_gcs_client.return_value.bucket.return_value = mock_bucket

    response = client.get(
        "/care_plan/saved/doc-1/input-pdf-url",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 200
    assert response.get_json()["url"] == "https://signed.url/priority"
    # Must use the new path blob name, not the legacy one
    mock_bucket.blob.assert_called_with("care_plan/user-1/inputs/new.pdf")


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
@patch("routes.saved_outputs.firestore.client")
@patch("routes.saved_outputs._BUCKET_NAME", "my-bucket")
def test_get_input_pdf_url_neither_set_returns_404(mock_firestore_client, _verify_token, client):
    """Doc with neither field set → returns 404 with error message."""
    doc = _make_owned_doc({
        # no output_data, no input_pdf_gcs
    })
    _wire_get_owned(mock_firestore_client, doc)

    response = client.get(
        "/care_plan/saved/doc-1/input-pdf-url",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 404
    assert "error" in response.get_json()


# ---------------------------------------------------------------------------
# Existing tests
# ---------------------------------------------------------------------------


@patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
@patch("routes.saved_outputs.firestore.client")
def test_batch_group_id_round_trip(mock_firestore_client, _verify_token, client):
    """GET /care_plan/saved returns batch_group_id correctly for both cases."""
    now = datetime(2026, 6, 16, 15, 0, 0, tzinfo=timezone.utc)

    doc_with_batch = _make_doc("output-1", {
        "uid": "user-1",
        "name": "Visit with batch",
        "source_filename": "notes.txt",
        "created_at": now,
        "updated_at": now,
        "batch_group_id": "DocConv-test",
    })
    doc_standalone = _make_doc("output-2", {
        "uid": "user-1",
        "name": "Standalone visit",
        "source_filename": "transcript.txt",
        "created_at": now,
        "updated_at": now,
        # no batch_group_id key — simulates item saved without one
    })

    mock_db = MagicMock()
    mock_firestore_client.return_value = mock_db
    (
        mock_db.collection.return_value
        .where.return_value
        .order_by.return_value
        .stream.return_value
    ) = iter([doc_with_batch, doc_standalone])

    response = client.get(
        "/care_plan/saved",
        headers={"Authorization": "Bearer token"},
    )

    assert response.status_code == 200
    data = response.get_json()
    outputs = data["outputs"]
    assert len(outputs) == 2

    # First output: saved with batch_group_id
    assert outputs[0]["id"] == "output-1"
    assert outputs[0]["batch_group_id"] == "DocConv-test"

    # Second output: saved without batch_group_id — should be None/null
    assert outputs[1]["id"] == "output-2"
    assert outputs[1]["batch_group_id"] is None
