"""Tests for routes/grading.py — POST /care_plan/grade endpoint."""
import json
import time
import pytest
from unittest.mock import MagicMock

# A text long enough that score_text returns a real score.
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


def test_grade_missing_both_returns_400(client, auth_ok):
    """No saved_id and no text → 400 with an error field."""
    resp = client.post("/care_plan/grade", json={}, headers=auth_ok)
    assert resp.status_code == 400
    assert "error" in resp.get_json()
    body = resp.get_json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "INPUT_VALIDATION_ERROR"


def test_grade_disabled_returns_empty(client, auth_ok):
    """Text path with clarified_text returns enabled=true and non-empty entries."""
    resp = client.post(
        "/care_plan/grade",
        json={"text": SAMPLE_TEXT, "clarified_text": CLARIFIED_TEXT},
        headers=auth_ok,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "grading" in body
    grading = body["grading"]
    assert grading["enabled"] is True
    assert len(grading["entries"]) > 0


def test_grade_saved_id_path(client, auth_ok, fake_firestore):
    """saved_id path: reads doc, writes grading back, returns Grading."""
    fake_doc = MagicMock()
    fake_doc.exists = True
    fake_doc.to_dict.return_value = {
        "uid": "user-1",
        "output_data": {
            "care_plan": {
                "raw": {
                    "text": SAMPLE_TEXT,
                    "clarified_text": CLARIFIED_TEXT,
                }
            }
        },
    }
    fake_ref = MagicMock()
    fake_doc.reference = fake_ref
    fake_firestore.collection.return_value.document.return_value.get.return_value = fake_doc

    resp = client.post(
        "/care_plan/grade",
        json={"saved_id": "doc-abc"},
        headers=auth_ok,
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "grading" in body

    # Should have written grading back to Firestore
    fake_ref.update.assert_called_once()
    call_args = fake_ref.update.call_args[0][0]
    assert "output_data.grading" in call_args


def test_grade_saved_id_not_found_returns_404(client, auth_ok, fake_firestore):
    """saved_id for a nonexistent doc → 404."""
    not_found_doc = MagicMock()
    not_found_doc.exists = False
    fake_firestore.collection.return_value.document.return_value.get.return_value = not_found_doc

    resp = client.post(
        "/care_plan/grade",
        json={"saved_id": "nonexistent"},
        headers=auth_ok,
    )
    assert resp.status_code == 404


def test_grade_saved_id_wrong_user_returns_403(client, auth_ok, fake_firestore):
    """saved_id owned by a different user → 403."""
    forbidden_doc = MagicMock()
    forbidden_doc.exists = True
    forbidden_doc.to_dict.return_value = {"uid": "other-user"}
    fake_firestore.collection.return_value.document.return_value.get.return_value = forbidden_doc

    resp = client.post(
        "/care_plan/grade",
        json={"saved_id": "doc-abc"},
        headers=auth_ok,
    )
    assert resp.status_code == 403


def test_grade_text_path_no_firestore_write(client, auth_ok, fake_firestore):
    """text+clarified path: returns Grading, no Firestore collection accessed."""
    resp = client.post(
        "/care_plan/grade",
        json={"text": SAMPLE_TEXT},
        headers=auth_ok,
    )
    assert resp.status_code == 200
    # firestore.client() / collection should not have been touched for the text path
    fake_firestore.collection.assert_not_called()


def test_grade_two_runs_differ(client, auth_ok):
    """Two sequential grading runs → graded_at timestamps differ."""
    resp1 = client.post(
        "/care_plan/grade",
        json={"text": SAMPLE_TEXT},
        headers=auth_ok,
    )
    time.sleep(0.01)
    resp2 = client.post(
        "/care_plan/grade",
        json={"text": SAMPLE_TEXT},
        headers=auth_ok,
    )
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    at1 = resp1.get_json()["grading"]["graded_at"]
    at2 = resp2.get_json()["grading"]["graded_at"]
    assert at1 != at2


def test_grade_missing_auth_returns_401(client):
    """No Authorization header → 401."""
    resp = client.post("/care_plan/grade", json={"text": SAMPLE_TEXT})
    assert resp.status_code == 401


def test_grade_malformed_auth_returns_401(client):
    """Malformed Authorization header → 401."""
    resp = client.post(
        "/care_plan/grade",
        json={"text": SAMPLE_TEXT},
        headers={"Authorization": "NotBearer token"},
    )
    assert resp.status_code == 401


def test_run_grading_returns_500_on_firestore_update_error(client, auth_ok):
    """saved_id path: Firestore update raises → 500 INTERNAL_ERROR."""
    from unittest.mock import MagicMock, patch

    mock_doc = MagicMock()
    mock_doc.to_dict.return_value = {
        "output_data": {
            "care_plan": {
                "raw": {"text": "patient has hypertension", "clarified_text": ""}
            }
        }
    }
    mock_doc.reference.update.side_effect = Exception("Firestore failure")

    mock_grading = MagicMock()
    mock_grading.to_dict.return_value = {}

    with patch("routes.grading.get_owned_doc_or_403", return_value=(mock_doc, None)), \
         patch("routes.grading.firestore_client"), \
         patch("routes.grading.score_text_safe", return_value={"composite": 5.0}), \
         patch("routes.grading.build_grading_with_before_after_score", return_value=mock_grading):
        response = client.post(
            "/care_plan/grade",
            json={"saved_id": "some-id"},
            headers=auth_ok,
        )
    assert response.status_code == 500
    data = response.get_json()
    assert data["status"] == "error"
    assert data["error"]["code"] == "INTERNAL_ERROR"


def test_run_grading_validates_body_with_pydantic(client, auth_ok):
    """POST with saved_id as int (not str) should return 400 validation error."""
    response = client.post(
        "/care_plan/grade",
        json={"saved_id": 123},
        headers=auth_ok,
    )
    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"
    assert data["error"]["code"] == "INPUT_VALIDATION_ERROR"
