"""Tests for routes/grading.py — /simplify/grade endpoint."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent
for p in (str(BACKEND_DIR), str(PROJECT_DIR)):
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)

from routes.grading import grading_bp

# A text long enough that score_text returns a real score (not None).
SAMPLE_TEXT = (
    "The patient was diagnosed with hypertension and type 2 diabetes mellitus. "
    "She was prescribed metformin 500 mg twice daily and lisinopril 10 mg once daily. "
    "Please take your medications as directed by your physician. "
    "Follow up with your primary care provider in four weeks. "
    "Monitor your blood glucose levels and report any hypoglycemia. "
    "Avoid excessive sodium intake to manage your blood pressure effectively. "
    "Contact the clinic if you experience chest pain or shortness of breath."
)

CLARIFIED_TEXT = (
    "You have high blood pressure and high blood sugar. "
    "Take metformin 500 mg in the morning and evening with food. "
    "Also take lisinopril 10 mg once each morning. "
    "See your regular doctor in four weeks. "
    "Check your blood sugar daily and call us if it gets very low. "
    "Eat less salty food to help your blood pressure. "
    "Call us right away if you have chest pain or trouble breathing."
)

BEARER = {"Authorization": "Bearer test-token"}


def create_app():
    app = Flask(__name__)
    app.register_blueprint(grading_bp)
    return app


class TestGradingRouteMissingTextAndId(unittest.TestCase):
    """POST with no saved_id and no text returns 400."""

    def setUp(self):
        self.client = create_app().test_client()

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_missing_both_returns_400(self, _mock_token):
        resp = self.client.post(
            "/simplify/grade",
            json={},
            headers=BEARER,
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        self.assertIn("error", body)


class TestGradingRouteTextPath(unittest.TestCase):
    """POST with text/clarified_text returns Grading, no Firestore write."""

    def setUp(self):
        self.client = create_app().test_client()

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_text_path_returns_grading(self, _mock_token):
        resp = self.client.post(
            "/simplify/grade",
            json={"text": SAMPLE_TEXT, "clarified_text": CLARIFIED_TEXT},
            headers=BEARER,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("grading", body)
        grading = body["grading"]
        self.assertIn("entries", grading)
        self.assertIn("enabled", grading)
        self.assertTrue(grading["enabled"])

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    @patch("firebase_admin.firestore.client")
    def test_text_path_no_firestore_write(self, mock_fs_client, _mock_token):
        """When using the text path, Firestore update must NOT be called."""
        resp = self.client.post(
            "/simplify/grade",
            json={"text": SAMPLE_TEXT},
            headers=BEARER,
        )
        self.assertEqual(resp.status_code, 200)
        # firestore.client() should not have been called at all for the text path.
        mock_fs_client.assert_not_called()

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_text_path_entries_are_non_empty(self, _mock_token):
        resp = self.client.post(
            "/simplify/grade",
            json={"text": SAMPLE_TEXT, "clarified_text": CLARIFIED_TEXT},
            headers=BEARER,
        )
        self.assertEqual(resp.status_code, 200)
        grading = resp.get_json()["grading"]
        self.assertGreater(len(grading["entries"]), 0)


class TestGradingRouteSavedIdPath(unittest.TestCase):
    """POST with saved_id fetches Firestore doc, grades it, and writes back."""

    def setUp(self):
        self.client = create_app().test_client()
        # Build a fake Firestore document.
        self.fake_doc = MagicMock()
        self.fake_doc.exists = True
        self.fake_doc.to_dict.return_value = {
            "uid": "user-1",
            "output_data": {
                "simplified_care_plan": {
                    "raw": {
                        "text": SAMPLE_TEXT,
                        "clarified_text": CLARIFIED_TEXT,
                    }
                }
            },
        }
        self.fake_ref = MagicMock()
        self.fake_doc.reference = self.fake_ref

        self.fake_db = MagicMock()
        self.fake_db.collection.return_value.document.return_value.get.return_value = self.fake_doc

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    @patch("firebase_admin.firestore.client")
    def test_saved_id_returns_grading(self, mock_fs_client, _mock_token):
        mock_fs_client.return_value = self.fake_db
        resp = self.client.post(
            "/simplify/grade",
            json={"saved_id": "doc-abc"},
            headers=BEARER,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertIn("grading", body)

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    @patch("firebase_admin.firestore.client")
    def test_saved_id_calls_firestore_update(self, mock_fs_client, _mock_token):
        """After grading a saved doc, the route must call reference.update()."""
        mock_fs_client.return_value = self.fake_db
        resp = self.client.post(
            "/simplify/grade",
            json={"saved_id": "doc-abc"},
            headers=BEARER,
        )
        self.assertEqual(resp.status_code, 200)
        self.fake_ref.update.assert_called_once()
        # The update call should set output_data.grading.
        call_args = self.fake_ref.update.call_args[0][0]
        self.assertIn("output_data.grading", call_args)

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    @patch("firebase_admin.firestore.client")
    def test_saved_id_not_found_returns_404(self, mock_fs_client, _mock_token):
        not_found_doc = MagicMock()
        not_found_doc.exists = False
        fake_db = MagicMock()
        fake_db.collection.return_value.document.return_value.get.return_value = not_found_doc
        mock_fs_client.return_value = fake_db

        resp = self.client.post(
            "/simplify/grade",
            json={"saved_id": "nonexistent"},
            headers=BEARER,
        )
        self.assertEqual(resp.status_code, 404)

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    @patch("firebase_admin.firestore.client")
    def test_saved_id_wrong_user_returns_403(self, mock_fs_client, _mock_token):
        forbidden_doc = MagicMock()
        forbidden_doc.exists = True
        forbidden_doc.to_dict.return_value = {"uid": "other-user"}
        fake_db = MagicMock()
        fake_db.collection.return_value.document.return_value.get.return_value = forbidden_doc
        mock_fs_client.return_value = fake_db

        resp = self.client.post(
            "/simplify/grade",
            json={"saved_id": "doc-abc"},
            headers=BEARER,
        )
        self.assertEqual(resp.status_code, 403)


class TestGradingRouteAuth(unittest.TestCase):
    """Auth enforcement."""

    def setUp(self):
        self.client = create_app().test_client()

    def test_missing_auth_header_returns_401(self):
        resp = self.client.post("/simplify/grade", json={"text": SAMPLE_TEXT})
        self.assertEqual(resp.status_code, 401)

    def test_malformed_token_returns_401(self):
        resp = self.client.post(
            "/simplify/grade",
            json={"text": SAMPLE_TEXT},
            headers={"Authorization": "NotBearer token"},
        )
        self.assertEqual(resp.status_code, 401)


class TestGradingRouteTwoSequentialRuns(unittest.TestCase):
    """Two sequential grading runs should produce different graded_at timestamps
    and must not grow the entries array."""

    def setUp(self):
        self.client = create_app().test_client()

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_two_runs_graded_at_differ(self, _mock_token):
        import time

        resp1 = self.client.post(
            "/simplify/grade",
            json={"text": SAMPLE_TEXT},
            headers=BEARER,
        )
        time.sleep(0.01)
        resp2 = self.client.post(
            "/simplify/grade",
            json={"text": SAMPLE_TEXT},
            headers=BEARER,
        )
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)
        graded_at_1 = resp1.get_json()["grading"]["graded_at"]
        graded_at_2 = resp2.get_json()["grading"]["graded_at"]
        self.assertNotEqual(graded_at_1, graded_at_2)

    @patch("utils.auth.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_two_runs_entries_count_unchanged(self, _mock_token):
        resp1 = self.client.post(
            "/simplify/grade",
            json={"text": SAMPLE_TEXT},
            headers=BEARER,
        )
        resp2 = self.client.post(
            "/simplify/grade",
            json={"text": SAMPLE_TEXT},
            headers=BEARER,
        )
        entries1 = resp1.get_json()["grading"]["entries"]
        entries2 = resp2.get_json()["grading"]["entries"]
        self.assertEqual(len(entries1), len(entries2))


if __name__ == "__main__":
    unittest.main()
