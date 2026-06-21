"""Tests for utils/firebase.py — TDD: write tests first, then create the module."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

from flask import Flask


# ---------------------------------------------------------------------------
# initialize_firebase
# ---------------------------------------------------------------------------

@patch("utils.firebase.firebase_admin._apps", {"app": MagicMock()})
@patch("utils.firebase.firebase_admin.initialize_app")
@patch("utils.firebase.firestore.client")
def test_does_not_reinit_when_already_initialized(mock_client, mock_init_app):
    from utils.firebase import initialize_firebase

    initialize_firebase()
    mock_init_app.assert_not_called()


@patch("utils.firebase.firebase_admin._apps", {})
@patch.dict("os.environ", {"FIREBASE_SERVICE_ACCOUNT_JSON": '{"type": "service_account"}'})
@patch("utils.firebase.credentials.Certificate")
@patch("utils.firebase.firebase_admin.initialize_app")
@patch("utils.firebase.firestore.client")
def test_inits_with_json_env_when_not_initialized(mock_client, mock_init_app, mock_cert):
    from utils.firebase import initialize_firebase

    initialize_firebase()
    mock_cert.assert_called_once_with({"type": "service_account"})
    mock_init_app.assert_called_once()


@patch("utils.firebase.firebase_admin._apps", {})
@patch.dict("os.environ", {}, clear=False)
@patch("utils.firebase.firebase_admin.initialize_app")
@patch("utils.firebase.firestore.client")
def test_inits_with_default_credentials_when_no_env(mock_client, mock_init_app):
    import os
    # Ensure neither JSON nor path env var is set
    env_backup = {}
    for key in ("FIREBASE_SERVICE_ACCOUNT_JSON", "FIREBASE_SERVICE_ACCOUNT_PATH"):
        if key in os.environ:
            env_backup[key] = os.environ.pop(key)
    try:
        from utils.firebase import initialize_firebase
        initialize_firebase()
        mock_init_app.assert_called_once_with()
    finally:
        os.environ.update(env_backup)


@patch("utils.firebase.firebase_admin._apps", {"app": MagicMock()})
@patch("utils.firebase.firestore.client")
def test_returns_firestore_client(mock_client):
    from utils.firebase import initialize_firebase

    mock_client.return_value = MagicMock()
    result = initialize_firebase()
    mock_client.assert_called_once()
    assert result == mock_client.return_value


# ---------------------------------------------------------------------------
# firestore_client
# ---------------------------------------------------------------------------

@patch("utils.firebase.firestore.client")
def test_uses_default_database_id(mock_client):
    import os
    os.environ.pop("FIRESTORE_DATABASE_ID", None)
    from utils.firebase import firestore_client

    firestore_client()
    mock_client.assert_called_once_with(database_id="(default)")


@patch.dict("os.environ", {"FIRESTORE_DATABASE_ID": "my-db"})
@patch("utils.firebase.firestore.client")
def test_uses_env_database_id(mock_client):
    from utils.firebase import firestore_client

    firestore_client()
    mock_client.assert_called_once_with(database_id="my-db")


@patch("utils.firebase.firestore.client")
def test_returns_firestore_client_instance(mock_client):
    from utils.firebase import firestore_client

    fake_db = MagicMock()
    mock_client.return_value = fake_db
    result = firestore_client()
    assert result is fake_db


# ---------------------------------------------------------------------------
# get_owned_doc_or_403
# ---------------------------------------------------------------------------

def _make_db(doc_exists=True, uid="user-1"):
    db = MagicMock()
    doc = MagicMock()
    doc.exists = doc_exists
    doc.to_dict.return_value = {"uid": uid, "name": "test"}
    db.collection.return_value.document.return_value.get.return_value = doc
    return db, doc


def test_returns_404_when_doc_missing():
    from utils.firebase import get_owned_doc_or_403

    db, _ = _make_db(doc_exists=False)

    app = Flask(__name__)
    with app.app_context():
        result_doc, err = get_owned_doc_or_403(db, "care_plan_outputs", "doc-1", "user-1")
    assert result_doc is None
    assert err is not None
    response, status_code = err
    assert status_code == 404


def test_returns_403_when_uid_mismatches():
    from utils.firebase import get_owned_doc_or_403

    db, _ = _make_db(doc_exists=True, uid="other-user")

    app = Flask(__name__)
    with app.app_context():
        result_doc, err = get_owned_doc_or_403(db, "care_plan_outputs", "doc-1", "user-1")
    assert result_doc is None
    assert err is not None
    response, status_code = err
    assert status_code == 403


def test_returns_doc_and_none_on_success():
    from utils.firebase import get_owned_doc_or_403

    db, expected_doc = _make_db(doc_exists=True, uid="user-1")

    app = Flask(__name__)
    with app.app_context():
        result_doc, err = get_owned_doc_or_403(db, "care_plan_outputs", "doc-1", "user-1")
    assert err is None
    assert result_doc is expected_doc


def test_uses_provided_collection_name():
    from utils.firebase import get_owned_doc_or_403

    db, _ = _make_db(doc_exists=True, uid="user-1")

    app = Flask(__name__)
    with app.app_context():
        get_owned_doc_or_403(db, "my_custom_collection", "doc-1", "user-1")
    db.collection.assert_called_with("my_custom_collection")


# ---------------------------------------------------------------------------
# save_care_plan_output
# ---------------------------------------------------------------------------

@patch("utils.firebase.uuid.uuid4")
@patch("utils.firebase.firestore.client")
def test_persists_to_firestore(mock_client, mock_uuid4):
    from utils.firebase import save_care_plan_output

    mock_uuid4.return_value = "output-abc"
    doc_ref = MagicMock()
    mock_client.return_value.collection.return_value.document.return_value = doc_ref

    result = save_care_plan_output(
        user_id="user-1",
        name="Visit summary",
        source_filename="file.pdf",
        output_data={"care_plan": {"summary": "ok"}},
    )

    assert result == "output-abc"
    mock_client.return_value.collection.assert_called_with("care_plan_outputs")
    mock_client.return_value.collection.return_value.document.assert_called_with("output-abc")
    doc_ref.set.assert_called_once()


@patch("utils.firebase.uuid.uuid4")
@patch("utils.firebase.firestore.client")
def test_uses_tz_aware_datetimes(mock_client, mock_uuid4):
    from utils.firebase import save_care_plan_output

    mock_uuid4.return_value = "output-abc"
    doc_ref = MagicMock()
    mock_client.return_value.collection.return_value.document.return_value = doc_ref

    save_care_plan_output(
        user_id="user-1",
        name="Visit",
        source_filename="f.txt",
        output_data={},
    )

    payload = doc_ref.set.call_args.args[0]
    assert isinstance(payload["created_at"], datetime)
    assert payload["created_at"].tzinfo is not None
    assert payload["created_at"].tzinfo == timezone.utc
    assert payload["updated_at"] == payload["created_at"]


@patch("utils.firebase.uuid.uuid4")
@patch("utils.firebase.firestore.client")
def test_accepts_batch_metadata(mock_client, mock_uuid4):
    from utils.firebase import save_care_plan_output

    mock_uuid4.return_value = "output-abc"
    doc_ref = MagicMock()
    mock_client.return_value.collection.return_value.document.return_value = doc_ref

    save_care_plan_output(
        user_id="user-1",
        name="Visit",
        source_filename="notes.txt",
        output_data={"summary": "ok"},
        dataset_group="DocConv",
        batch_group_id="DocConv-20260616153012",
    )

    payload = doc_ref.set.call_args.args[0]
    assert payload["dataset_group"] == "DocConv"
    assert payload["batch_group_id"] == "DocConv-20260616153012"


@patch("utils.firebase.uuid.uuid4")
@patch("utils.firebase.firestore.client")
def test_does_not_include_batch_fields_when_not_provided(mock_client, mock_uuid4):
    from utils.firebase import save_care_plan_output

    mock_uuid4.return_value = "output-abc"
    doc_ref = MagicMock()
    mock_client.return_value.collection.return_value.document.return_value = doc_ref

    save_care_plan_output(
        user_id="user-1",
        name="Visit",
        source_filename="notes.txt",
        output_data={},
    )

    payload = doc_ref.set.call_args.args[0]
    assert "dataset_group" not in payload
    assert "batch_group_id" not in payload


@patch("utils.firebase.uuid.uuid4")
@patch.dict("os.environ", {"FIRESTORE_DATABASE_ID": "custom-db"})
@patch("utils.firebase.firestore.client")
def test_uses_firestore_database_id_from_env(mock_client, mock_uuid4):
    from utils.firebase import save_care_plan_output

    mock_uuid4.return_value = "output-abc"
    doc_ref = MagicMock()
    mock_client.return_value.collection.return_value.document.return_value = doc_ref

    save_care_plan_output(
        user_id="user-1",
        name="Visit",
        source_filename="f.txt",
        output_data={},
    )

    mock_client.assert_called_with(database_id="custom-db")
