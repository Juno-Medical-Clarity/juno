from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


def _make_doc(doc_id: str, data: dict) -> MagicMock:
    """Return a mock Firestore document snapshot."""
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data
    return doc


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
