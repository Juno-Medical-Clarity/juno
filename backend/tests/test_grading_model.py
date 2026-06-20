"""Tests for backend/models/grading.py — GradingEntry, Grading, build_grading."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
for p in (PROJECT_DIR, BACKEND_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from models.grading import Grading, GradingEntry, build_grading
from utils.scoring import score_text


# Long enough for SMOG (>30 sentences)
FIXTURE_TEXT = (
    "The patient was diagnosed with hypertension. Take your blood pressure medicine every day. "
    "Call your doctor if you feel dizzy. Drink eight glasses of water daily. Avoid salty foods. "
    "Exercise for thirty minutes each day. Monitor your blood pressure at home. "
    "Come back for a follow-up in two weeks. Ask your doctor any questions you have. "
) * 5  # ~45 sentences

FIXTURE_CLARIFIED = (
    "Your blood pressure is too high. Take your pill every morning with water. "
    "If you feel dizzy, call your doctor right away. Eat less salt. Walk every day. "
    "Check your blood pressure at home. See your doctor again in two weeks. "
) * 5


class TestGradingEntryModel(unittest.TestCase):
    def test_to_dict_roundtrip(self):
        entry = GradingEntry(
            name="smog", target="after", grade=72.5,
            grade_breakdown={"grade": 9.5, "insufficient_sample": False},
            reasoning="SMOG grade",
        )
        d = entry.to_dict()
        self.assertEqual(d["name"], "smog")
        self.assertEqual(d["target"], "after")
        self.assertAlmostEqual(d["grade"], 72.5)
        entry2 = GradingEntry.from_dict(d)
        self.assertEqual(entry2.name, "smog")
        self.assertAlmostEqual(entry2.grade, 72.5)

    def test_optional_fields_default_none(self):
        entry = GradingEntry(name="combined", target="before", grade=60.0)
        d = entry.to_dict()
        self.assertIsNone(d["grade_breakdown"])
        self.assertIsNone(d["reasoning"])


class TestGradingModel(unittest.TestCase):
    def test_default_produces_empty_enabled_true(self):
        g = Grading()
        d = g.to_dict()
        self.assertEqual(d, {"entries": [], "enabled": True, "graded_at": None})

    def test_disabled_grading(self):
        g = Grading(enabled=False)
        d = g.to_dict()
        self.assertEqual(d["entries"], [])
        self.assertFalse(d["enabled"])
        self.assertIsNone(d["graded_at"])

    def test_roundtrip_with_entries(self):
        entry = GradingEntry(name="smog", target="after", grade=55.0)
        g = Grading(entries=[entry], enabled=True, graded_at="2026-01-01T00:00:00+00:00")
        d = g.to_dict()
        g2 = Grading.from_dict(d)
        self.assertEqual(len(g2.entries), 1)
        self.assertEqual(g2.entries[0].name, "smog")
        self.assertEqual(g2.graded_at, "2026-01-01T00:00:00+00:00")


class TestBuildGrading(unittest.TestCase):
    def setUp(self):
        self.before_score = score_text(FIXTURE_TEXT)
        self.after_score = score_text(FIXTURE_CLARIFIED)

    def test_produces_14_entries(self):
        g = build_grading(self.before_score, FIXTURE_TEXT, self.after_score, FIXTURE_CLARIFIED)
        self.assertEqual(len(g.entries), 14)

    def test_correct_name_target_combinations(self):
        g = build_grading(self.before_score, FIXTURE_TEXT, self.after_score, FIXTURE_CLARIFIED)
        names = {(e.name, e.target) for e in g.entries}
        expected_names = {"smog", "flesch_kincaid", "dale_chall", "pemat", "sam", "cdc_cci", "combined"}
        for name in expected_names:
            self.assertIn((name, "before"), names, f"Missing ({name}, before)")
            self.assertIn((name, "after"), names, f"Missing ({name}, after)")

    def test_combined_entry_has_dimensions(self):
        g = build_grading(self.before_score, FIXTURE_TEXT, self.after_score, FIXTURE_CLARIFIED)
        combined_after = next(e for e in g.entries if e.name == "combined" and e.target == "after")
        self.assertIn("dimensions", combined_after.grade_breakdown)
        dims = combined_after.grade_breakdown["dimensions"]
        self.assertIn("grade_level", dims)

    def test_combined_grade_matches_composite(self):
        g = build_grading(self.before_score, FIXTURE_TEXT, self.after_score, FIXTURE_CLARIFIED)
        combined_after = next(e for e in g.entries if e.name == "combined" and e.target == "after")
        self.assertEqual(combined_after.grade, self.after_score["composite"])

    def test_graded_at_is_set(self):
        g = build_grading(self.before_score, FIXTURE_TEXT, self.after_score, FIXTURE_CLARIFIED)
        self.assertIsNotNone(g.graded_at)

    def test_none_before_produces_7_entries(self):
        g = build_grading(None, None, self.after_score, FIXTURE_CLARIFIED)
        self.assertEqual(len(g.entries), 7)
        self.assertTrue(all(e.target == "after" for e in g.entries))

    def test_both_none_produces_empty_grading(self):
        g = build_grading(None, None, None, None)
        self.assertEqual(len(g.entries), 0)
        self.assertTrue(g.enabled)


class TestGradeEndpoint(unittest.TestCase):
    """Route tests for POST /care_plan/grade."""

    def setUp(self):
        from routes import all_blueprints
        self.app = Flask(__name__)
        for bp in all_blueprints:
            self.app.register_blueprint(bp)
        self.client = self.app.test_client()

    @patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_text_mode_returns_grading_no_firestore(self, _):
        """POST with text/clarified_text computes and returns Grading without persisting."""
        with patch("routes.grading._score_safe") as mock_score:
            mock_score.return_value = score_text(FIXTURE_TEXT)
            response = self.client.post(
                "/care_plan/grade",
                headers={"Authorization": "Bearer token"},
                json={"text": FIXTURE_TEXT, "clarified_text": FIXTURE_CLARIFIED},
            )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("grading", data)
        self.assertIn("entries", data["grading"])

    @patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_missing_body_returns_400(self, _):
        """POST with neither saved_id nor text returns 400."""
        response = self.client.post(
            "/care_plan/grade",
            headers={"Authorization": "Bearer token"},
            json={},
        )
        self.assertEqual(response.status_code, 400)

    @patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_saved_id_not_found_returns_404(self, _):
        """POST with a saved_id not in Firestore returns 404."""
        mock_doc = MagicMock()
        mock_doc.exists = False
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("routes.grading.firestore_client", return_value=mock_db):
            response = self.client.post(
                "/care_plan/grade",
                headers={"Authorization": "Bearer token"},
                json={"saved_id": "nonexistent-id"},
            )
        self.assertEqual(response.status_code, 404)

    @patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_saved_id_wrong_user_returns_403(self, _):
        """POST with a saved_id owned by another user returns 403."""
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {"uid": "other-user"}
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("routes.grading.firestore_client", return_value=mock_db):
            response = self.client.post(
                "/care_plan/grade",
                headers={"Authorization": "Bearer token"},
                json={"saved_id": "someone-elses-id"},
            )
        self.assertEqual(response.status_code, 403)

    @patch("utils.firebase.auth.verify_id_token", return_value={"uid": "user-1"})
    def test_saved_id_updates_firestore_and_returns_grading(self, _):
        """POST with valid saved_id overwrites Firestore grading and returns it."""
        mock_ref = MagicMock()
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.reference = mock_ref
        mock_doc.to_dict.return_value = {
            "uid": "user-1",
            "output_data": {
                "care_plan": {
                    "raw": {
                        "text": FIXTURE_TEXT,
                        "clarified_text": FIXTURE_CLARIFIED,
                    }
                }
            },
        }
        mock_db = MagicMock()
        mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

        with patch("routes.grading.firestore_client", return_value=mock_db):
            response = self.client.post(
                "/care_plan/grade",
                headers={"Authorization": "Bearer token"},
                json={"saved_id": "valid-doc-id"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("grading", data)
        self.assertIn("entries", data["grading"])
        # Verify Firestore was updated
        mock_ref.update.assert_called_once()
        update_call_arg = mock_ref.update.call_args[0][0]
        self.assertIn("output_data.grading", update_call_arg)


if __name__ == "__main__":
    unittest.main()
