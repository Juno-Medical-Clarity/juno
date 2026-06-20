"""Tests for utils/firebase.py — TDD: write tests first, then create the module."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, call

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class InitializeFirebaseTest(unittest.TestCase):
    """Test initialize_firebase() is idempotent."""

    @patch("utils.firebase.firebase_admin._apps", {"app": MagicMock()})
    @patch("utils.firebase.firebase_admin.initialize_app")
    @patch("utils.firebase.firestore.client")
    def test_does_not_reinit_when_already_initialized(self, mock_client, mock_init_app):
        from utils.firebase import initialize_firebase

        initialize_firebase()
        mock_init_app.assert_not_called()

    @patch("utils.firebase.firebase_admin._apps", {})
    @patch.dict("os.environ", {"FIREBASE_SERVICE_ACCOUNT_JSON": '{"type": "service_account"}'})
    @patch("utils.firebase.credentials.Certificate")
    @patch("utils.firebase.firebase_admin.initialize_app")
    @patch("utils.firebase.firestore.client")
    def test_inits_with_json_env_when_not_initialized(self, mock_client, mock_init_app, mock_cert):
        from utils.firebase import initialize_firebase

        initialize_firebase()
        mock_cert.assert_called_once_with({"type": "service_account"})
        mock_init_app.assert_called_once()

    @patch("utils.firebase.firebase_admin._apps", {})
    @patch.dict("os.environ", {}, clear=False)
    @patch("utils.firebase.firebase_admin.initialize_app")
    @patch("utils.firebase.firestore.client")
    def test_inits_with_default_credentials_when_no_env(self, mock_client, mock_init_app):
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
    def test_returns_firestore_client(self, mock_client):
        from utils.firebase import initialize_firebase

        mock_client.return_value = MagicMock()
        result = initialize_firebase()
        mock_client.assert_called_once()
        self.assertEqual(result, mock_client.return_value)


class FirestoreClientTest(unittest.TestCase):
    """Test firestore_client() passes database_id from env."""

    @patch("utils.firebase.firestore.client")
    def test_uses_default_database_id(self, mock_client):
        import os
        os.environ.pop("FIRESTORE_DATABASE_ID", None)
        from utils.firebase import firestore_client

        firestore_client()
        mock_client.assert_called_once_with(database_id="(default)")

    @patch.dict("os.environ", {"FIRESTORE_DATABASE_ID": "my-db"})
    @patch("utils.firebase.firestore.client")
    def test_uses_env_database_id(self, mock_client):
        from utils.firebase import firestore_client

        firestore_client()
        mock_client.assert_called_once_with(database_id="my-db")

    @patch("utils.firebase.firestore.client")
    def test_returns_firestore_client_instance(self, mock_client):
        from utils.firebase import firestore_client

        fake_db = MagicMock()
        mock_client.return_value = fake_db
        result = firestore_client()
        self.assertIs(result, fake_db)


class GetOwnedDocOr403Test(unittest.TestCase):
    """Test get_owned_doc_or_403() returns 404/403/(doc, None)."""

    def _make_db(self, doc_exists=True, uid="user-1"):
        db = MagicMock()
        doc = MagicMock()
        doc.exists = doc_exists
        doc.to_dict.return_value = {"uid": uid, "name": "test"}
        db.collection.return_value.document.return_value.get.return_value = doc
        return db, doc

    def test_returns_404_when_doc_missing(self):
        from utils.firebase import get_owned_doc_or_403

        db, _ = self._make_db(doc_exists=False)

        # Need Flask app context for jsonify
        import sys
        sys.path.insert(0, str(BACKEND_DIR))
        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            result_doc, err = get_owned_doc_or_403(db, "care_plan_outputs", "doc-1", "user-1")
        self.assertIsNone(result_doc)
        self.assertIsNotNone(err)
        response, status_code = err
        self.assertEqual(status_code, 404)

    def test_returns_403_when_uid_mismatches(self):
        from utils.firebase import get_owned_doc_or_403

        db, _ = self._make_db(doc_exists=True, uid="other-user")

        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            result_doc, err = get_owned_doc_or_403(db, "care_plan_outputs", "doc-1", "user-1")
        self.assertIsNone(result_doc)
        self.assertIsNotNone(err)
        response, status_code = err
        self.assertEqual(status_code, 403)

    def test_returns_doc_and_none_on_success(self):
        from utils.firebase import get_owned_doc_or_403

        db, expected_doc = self._make_db(doc_exists=True, uid="user-1")

        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            result_doc, err = get_owned_doc_or_403(db, "care_plan_outputs", "doc-1", "user-1")
        self.assertIsNone(err)
        self.assertIs(result_doc, expected_doc)

    def test_uses_provided_collection_name(self):
        from utils.firebase import get_owned_doc_or_403

        db, _ = self._make_db(doc_exists=True, uid="user-1")

        from flask import Flask
        app = Flask(__name__)
        with app.app_context():
            get_owned_doc_or_403(db, "my_custom_collection", "doc-1", "user-1")
        db.collection.assert_called_with("my_custom_collection")


class SaveCarePlanOutputTest(unittest.TestCase):
    """Test save_care_plan_output() in utils/firebase.py."""

    @patch("utils.firebase.uuid.uuid4")
    @patch("utils.firebase.firestore.client")
    def test_persists_to_firestore(self, mock_client, mock_uuid4):
        from utils.firebase import save_care_plan_output

        mock_uuid4.return_value = "output-abc"
        doc_ref = MagicMock()
        mock_client.return_value.collection.return_value.document.return_value = doc_ref

        result = save_care_plan_output(
            user_id="user-1",
            name="Visit summary",
            source_filename="file.pdf",
            input_pdf_gcs="gs://bucket/care_plan/user-1/inputs/file.pdf",
            output_data={"care_plan": {"summary": "ok"}},
        )

        self.assertEqual(result, "output-abc")
        mock_client.return_value.collection.assert_called_with("care_plan_outputs")
        mock_client.return_value.collection.return_value.document.assert_called_with("output-abc")
        doc_ref.set.assert_called_once()

    @patch("utils.firebase.uuid.uuid4")
    @patch("utils.firebase.firestore.client")
    def test_uses_tz_aware_datetimes(self, mock_client, mock_uuid4):
        from utils.firebase import save_care_plan_output

        mock_uuid4.return_value = "output-abc"
        doc_ref = MagicMock()
        mock_client.return_value.collection.return_value.document.return_value = doc_ref

        save_care_plan_output(
            user_id="user-1",
            name="Visit",
            source_filename="f.txt",
            input_pdf_gcs=None,
            output_data={},
        )

        payload = doc_ref.set.call_args.args[0]
        self.assertIsInstance(payload["created_at"], datetime)
        self.assertIsNotNone(payload["created_at"].tzinfo)
        self.assertEqual(payload["created_at"].tzinfo, timezone.utc)
        self.assertEqual(payload["updated_at"], payload["created_at"])

    @patch("utils.firebase.uuid.uuid4")
    @patch("utils.firebase.firestore.client")
    def test_accepts_batch_metadata(self, mock_client, mock_uuid4):
        from utils.firebase import save_care_plan_output

        mock_uuid4.return_value = "output-abc"
        doc_ref = MagicMock()
        mock_client.return_value.collection.return_value.document.return_value = doc_ref

        save_care_plan_output(
            user_id="user-1",
            name="Visit",
            source_filename="notes.txt",
            input_pdf_gcs=None,
            output_data={"summary": "ok"},
            dataset_group="DocConv",
            batch_group_id="DocConv-20260616153012",
        )

        payload = doc_ref.set.call_args.args[0]
        self.assertEqual(payload["dataset_group"], "DocConv")
        self.assertEqual(payload["batch_group_id"], "DocConv-20260616153012")

    @patch("utils.firebase.uuid.uuid4")
    @patch("utils.firebase.firestore.client")
    def test_does_not_include_batch_fields_when_not_provided(self, mock_client, mock_uuid4):
        from utils.firebase import save_care_plan_output

        mock_uuid4.return_value = "output-abc"
        doc_ref = MagicMock()
        mock_client.return_value.collection.return_value.document.return_value = doc_ref

        save_care_plan_output(
            user_id="user-1",
            name="Visit",
            source_filename="notes.txt",
            input_pdf_gcs=None,
            output_data={},
        )

        payload = doc_ref.set.call_args.args[0]
        self.assertNotIn("dataset_group", payload)
        self.assertNotIn("batch_group_id", payload)

    @patch("utils.firebase.uuid.uuid4")
    @patch.dict("os.environ", {"FIRESTORE_DATABASE_ID": "custom-db"})
    @patch("utils.firebase.firestore.client")
    def test_uses_firestore_database_id_from_env(self, mock_client, mock_uuid4):
        from utils.firebase import save_care_plan_output

        mock_uuid4.return_value = "output-abc"
        doc_ref = MagicMock()
        mock_client.return_value.collection.return_value.document.return_value = doc_ref

        save_care_plan_output(
            user_id="user-1",
            name="Visit",
            source_filename="f.txt",
            input_pdf_gcs=None,
            output_data={},
        )

        mock_client.assert_called_with(database_id="custom-db")


if __name__ == "__main__":
    unittest.main()
