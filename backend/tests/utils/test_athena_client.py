"""tests/utils/test_athena_client.py — Unit tests for AthenaClient."""
import time
import unittest
from unittest.mock import MagicMock, patch, call

import pytest

from services.external_api import AthenaClient
from models.external_api.athena_errors import AthenaAPIError
from utils.constants import Constants


@pytest.fixture
def client():
    """Return a fresh AthenaClient with no cached token."""
    return AthenaClient()


def _mock_token_response(access_token: str = "test_token"):
    """Build a mock requests.Response for a successful token POST."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"access_token": access_token}
    return resp


def _mock_get_response(body: dict):
    """Build a mock requests.Response for a successful GET."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = body
    return resp


# ─────────────────────────── get_token ────────────────────────────────────


def test_get_token_success(client, monkeypatch):
    """get_token() calls POST /oauth2/v1/token and returns access_token."""
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_SECRET", "csec")
    with patch("services.external_api.athena_client.requests.post", return_value=_mock_token_response("tok1")) as mock_post:
        token = client.get_token()
    assert token == "tok1"
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert "/oauth2/v1/token" in args[0]
    assert kwargs.get("data", {}).get("grant_type") == "client_credentials"


def test_get_token_cached_within_ttl(client, monkeypatch):
    """get_token() called twice within TTL makes only one HTTP call."""
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_SECRET", "csec")
    with patch("services.external_api.athena_client.requests.post", return_value=_mock_token_response("tok_cached")) as mock_post:
        t1 = client.get_token()
        t2 = client.get_token()
    assert t1 == t2 == "tok_cached"
    assert mock_post.call_count == 1


def test_get_token_refresh_when_expiry_within_buffer(client, monkeypatch):
    """get_token() refreshes when fewer than TOKEN_REFRESH_BUFFER_S seconds remain."""
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_SECRET", "csec")
    client._token = "old_token"
    client._token_expires_at = time.time() + 10  # 10s < 20s buffer
    with patch("services.external_api.athena_client.requests.post", return_value=_mock_token_response("new_token")) as mock_post:
        token = client.get_token()
    assert token == "new_token"
    mock_post.assert_called_once()


def test_get_token_does_not_refresh_when_fresh(client, monkeypatch):
    """get_token() returns cached token when more than TOKEN_REFRESH_BUFFER_S seconds remain."""
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    client._token = "fresh_token"
    client._token_expires_at = time.time() + 100  # 100s > 20s buffer
    with patch("services.external_api.athena_client.requests.post") as mock_post:
        token = client.get_token()
    assert token == "fresh_token"
    mock_post.assert_not_called()


# ─────────────────────────── _strip_html ──────────────────────────────────


def test_strip_html_removes_tags():
    """_strip_html strips all HTML tags from the input."""
    result = AthenaClient._strip_html("<p>Hello <b>world</b></p>")
    assert result == "Hello world"


def test_strip_html_unescapes_entities():
    """_strip_html unescapes HTML entities (tags resulting from unescape are also stripped)."""
    result = AthenaClient._strip_html("hello &amp; world")
    assert result == "hello & world"


# ─────────────────────────── fetch_encounter_summary ─────────────────────


def test_fetch_encounter_summary_calls_correct_path(client, monkeypatch):
    """fetch_encounter_summary calls _get with the correct Athena path."""
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    with patch.object(client, "_get", return_value={"summaryhtml": "<p>Gary</p>"}) as mock_get:
        result = client.fetch_encounter_summary("195900", "62021")
    mock_get.assert_called_once_with("/v1/195900/chart/encounters/62021/summary")
    assert result == "Gary"


# ─────────────────────────── fetch_clinical_doc ──────────────────────────


def test_fetch_clinical_doc_calls_correct_path(client, monkeypatch):
    """fetch_clinical_doc calls _get with the correct Athena path."""
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    with patch.object(client, "_get", return_value={"documentdata": "SOAP note text"}) as mock_get:
        result = client.fetch_clinical_doc("195900", "60178", "204552")
    mock_get.assert_called_once_with("/v1/195900/patients/60178/documents/clinicaldocument/204552")
    assert result == "SOAP note text"


# ─────────────────────────── fetch_items_with_rate_limit ─────────────────


def test_fetch_items_rate_limit_sleeps_between_batches_not_after_last(client):
    """fetch_items_with_rate_limit sleeps once between batch 1 and 2, not after batch 2."""
    items = [
        {"source_kind": "athena_encounter", "practice_id": "195900", "encounter_id": "62021"},
        {"source_kind": "athena_encounter", "practice_id": "195900", "encounter_id": "61456"},
        {"source_kind": "athena_encounter", "practice_id": "195900", "encounter_id": "62281"},
    ]
    with patch.object(client, "fetch_encounter_summary", return_value="text") as mock_fetch, \
         patch("services.external_api.athena_client.time.sleep") as mock_sleep:
        results = client.fetch_items_with_rate_limit(items)

    assert mock_sleep.call_count == 1
    assert mock_sleep.call_args == call(Constants.Athena.BATCH_SLEEP_S)
    assert len(results) == 3


def test_fetch_items_no_sleep_for_single_batch(client):
    """fetch_items_with_rate_limit does not sleep when all items fit in one batch."""
    items = [
        {"source_kind": "athena_encounter", "practice_id": "195900", "encounter_id": "62021"},
        {"source_kind": "athena_encounter", "practice_id": "195900", "encounter_id": "61456"},
    ]
    with patch.object(client, "fetch_encounter_summary", return_value="text"), \
         patch("services.external_api.athena_client.time.sleep") as mock_sleep:
        results = client.fetch_items_with_rate_limit(items)
    mock_sleep.assert_not_called()
    assert len(results) == 2
