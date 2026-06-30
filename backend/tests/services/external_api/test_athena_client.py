"""tests/services/external_api/test_athena_client.py — Unit tests for AthenaClient."""
import time
import unittest
from unittest.mock import MagicMock, patch, call, ANY

import pytest

from services.external_api.athena_client import AthenaClient
from models.external_api.athena_errors import AthenaAPIError
from errors import ErrorCode
from utils.constants import Constants
from utils.markers.registry import register_sink
from utils.markers.sinks import InMemorySink


@pytest.fixture
def client():
    return AthenaClient()


def _mock_token_response(access_token: str = "test_token"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"access_token": access_token, "token_type": "Bearer", "expires_in": 3600}
    return resp


def _mock_get_response(body: dict):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = body
    return resp


# ─────────────────────────── get_token ────────────────────────────────────


def test_get_token_success(client, monkeypatch):
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
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_SECRET", "csec")
    with patch("services.external_api.athena_client.requests.post", return_value=_mock_token_response("tok_cached")) as mock_post:
        t1 = client.get_token()
        t2 = client.get_token()
    assert t1 == t2 == "tok_cached"
    assert mock_post.call_count == 1


def test_get_token_refresh_when_expiry_within_buffer(client, monkeypatch):
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_SECRET", "csec")
    client._token = "old_token"
    client._token_expires_at = time.time() + 10  # 10s < 20s buffer
    with patch("services.external_api.athena_client.requests.post", return_value=_mock_token_response("new_token")) as mock_post:
        token = client.get_token()
    assert token == "new_token"
    mock_post.assert_called_once()


def test_get_token_does_not_refresh_when_fresh(client, monkeypatch):
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    client._token = "fresh_token"
    client._token_expires_at = time.time() + 100  # 100s > 20s buffer
    with patch("services.external_api.athena_client.requests.post") as mock_post:
        token = client.get_token()
    assert token == "fresh_token"
    mock_post.assert_not_called()


def test_get_token_uses_typed_model(client, monkeypatch):
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_SECRET", "csec")
    with patch("services.external_api.athena_client.requests.post",
               return_value=_mock_token_response("tok")) as mock_post:
        mock_post.return_value.json.return_value = {
            "access_token": "tok", "token_type": "Bearer", "expires_in": 3600, "extra": "ignored"
        }
        token = client.get_token()
    assert token == "tok"


def test_get_token_raises_auth_failed_error_code(client, monkeypatch):
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_SECRET", "csec")
    resp = MagicMock()
    resp.status_code = 401
    resp.text = "Unauthorized"
    with patch("services.external_api.athena_client.requests.post", return_value=resp):
        with pytest.raises(AthenaAPIError) as exc_info:
            client.get_token()
    assert exc_info.value.error_code == ErrorCode.ATHENA_AUTH_FAILED


# ─────────────────────────── _strip_html ──────────────────────────────────


def test_strip_html_removes_tags():
    result = AthenaClient._strip_html("<p>Hello <b>world</b></p>")
    assert result == "Hello world"


def test_strip_html_unescapes_entities():
    result = AthenaClient._strip_html("hello &amp; world")
    assert result == "hello & world"


# ─────────────────────────── _get ─────────────────────────────────────────


def test_get_raises_rate_limit_error_code_after_exhausted_retries(client, monkeypatch):
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_SECRET", "csec")
    rate_limit_resp = MagicMock()
    rate_limit_resp.status_code = 429
    rate_limit_resp.headers = {"Retry-After": "0"}
    # Token mock
    with patch("services.external_api.athena_client.requests.post", return_value=_mock_token_response()), \
         patch("services.external_api.athena_client.requests.get", return_value=rate_limit_resp), \
         patch("services.external_api.athena_client.time.sleep"):
        with pytest.raises(AthenaAPIError) as exc_info:
            client._get("/test/path", retries=1)
    assert exc_info.value.error_code == ErrorCode.ATHENA_RATE_LIMIT_ERROR


def test_get_raises_athena_api_error_on_non_200(client, monkeypatch):
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_SECRET", "csec")
    err_resp = MagicMock()
    err_resp.status_code = 503
    err_resp.text = "Service Unavailable"
    with patch("services.external_api.athena_client.requests.post", return_value=_mock_token_response()), \
         patch("services.external_api.athena_client.requests.get", return_value=err_resp):
        with pytest.raises(AthenaAPIError) as exc_info:
            client._get("/test/path")
    assert exc_info.value.status_code == 503
    assert exc_info.value.error_code == ErrorCode.ATHENA_API_ERROR


# ─────────────────────────── fetch_encounter_summary ─────────────────────


def test_fetch_encounter_summary_calls_correct_path(client, monkeypatch):
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    with patch.object(client, "_get", return_value={"summaryhtml": "<p>Gary</p>"}) as mock_get:
        result = client.fetch_encounter_summary("195900", "62021")
    # _get is called with path and scope kwarg
    assert mock_get.call_args[0][0] == "/v1/195900/chart/encounters/62021/summary"
    assert result == "Gary"


def test_fetch_encounter_summary_uses_typed_model(client, monkeypatch):
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    with patch.object(client, "_get", return_value={"summaryhtml": "<p>Gary</p>", "extra_field": "x"}):
        result = client.fetch_encounter_summary("195900", "62021")
    assert result == "Gary"


def test_fetch_encounter_summary_raises_on_missing_summaryhtml(client, monkeypatch):
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    from pydantic import ValidationError
    with patch.object(client, "_get", return_value={}):
        with pytest.raises(ValidationError):
            client.fetch_encounter_summary("195900", "62021")


# ─────────────────────────── fetch_clinical_doc ──────────────────────────


def test_fetch_clinical_doc_calls_correct_path(client, monkeypatch):
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    with patch.object(client, "_get", return_value={"documentdata": "SOAP note text"}) as mock_get:
        result = client.fetch_clinical_doc("195900", "60178", "204552")
    assert mock_get.call_args[0][0] == "/v1/195900/patients/60178/documents/clinicaldocument/204552"
    assert result == "SOAP note text"


def test_fetch_clinical_doc_uses_typed_model(client, monkeypatch):
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    with patch.object(client, "_get", return_value={"documentdata": "SOAP text", "pages": []}):
        result = client.fetch_clinical_doc("195900", "60178", "204552")
    assert result == "SOAP text"


def test_fetch_clinical_doc_returns_empty_string_when_documentdata_none(client, monkeypatch):
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_CLIENT_SECRET", "csec")
    with patch.object(client, "_get", return_value={"pages": []}):
        result = client.fetch_clinical_doc("195900", "60178", "204552")
    assert result == ""


# ─────────────────────────── Constants wiring ────────────────────────────


def test_athena_client_has_no_token_ttl_class_attr():
    assert not hasattr(AthenaClient, "TOKEN_TTL_S")
    assert not hasattr(AthenaClient, "TOKEN_REFRESH_BUFFER_S")


def test_get_uses_constants_request_timeout(client, monkeypatch):
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_SECRET", "csec")
    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.json.return_value = {"summaryhtml": "text"}
    with patch("services.external_api.athena_client.requests.post", return_value=_mock_token_response()), \
         patch("services.external_api.athena_client.requests.get", return_value=ok_resp) as mock_get:
        client._get("/test/path")
    _, kwargs = mock_get.call_args
    assert kwargs.get("timeout") == Constants.Athena.HTTP_TIMEOUT_GET_S


# ─────────────────────────── Markers ─────────────────────────────────────


@pytest.fixture(autouse=False)
def in_memory_sink():
    sink = InMemorySink()
    register_sink(sink)
    yield sink
    register_sink(None)


def test_fetch_encounter_summary_emits_marker(client, in_memory_sink, monkeypatch):
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_SECRET", "csec")
    with patch.object(client, "_get", return_value={"summaryhtml": "<p>text</p>"}):
        client.fetch_encounter_summary("195900", "62021")
    events = [e for e in in_memory_sink.events if e["name"] == "athena.fetch_encounter_summary"]
    assert events, "Expected marker event for fetch_encounter_summary"
    assert events[0]["dimensions"].get("source_kind") == Constants.Athena.AthenaSourceKind.ATHENA_ENCOUNTER.value


def test_fetch_clinical_doc_emits_marker(client, in_memory_sink, monkeypatch):
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_ID", "cid")
    monkeypatch.setenv("ATHENA_HEALTH_TEST_CLIENT_SECRET", "csec")
    with patch.object(client, "_get", return_value={"pages": []}):
        client.fetch_clinical_doc("195900", "60178", "204552")
    events = [e for e in in_memory_sink.events if e["name"] == "athena.fetch_clinical_doc"]
    assert events, "Expected marker event for fetch_clinical_doc"
    assert events[0]["dimensions"].get("source_kind") == Constants.Athena.AthenaSourceKind.ATHENA_CLINICAL_DOC.value
