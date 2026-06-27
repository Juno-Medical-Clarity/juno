import logging
import pytest


def test_all_error_codes_in_registry():
    from utils.error_codes import ErrorCode, _REGISTRY
    missing = [code for code in ErrorCode if code not in _REGISTRY]
    assert missing == [], f"ErrorCodes missing from registry: {missing}"


def test_all_registry_entries_have_message_and_template():
    from utils.error_codes import _REGISTRY
    for code, (message, template) in _REGISTRY.items():
        assert isinstance(message, str) and message, f"{code}: message is empty"
        assert isinstance(template, str) and template, f"{code}: details template is empty"


def test_make_error_response_returns_api_response():
    from utils.error_codes import make_error_response, ErrorCode
    from models.errors import ApiResponse, StatusEnum
    resp = make_error_response(ErrorCode.RESOURCE_NOT_FOUND, path="/test", details_vars={"collection": "c", "doc_id": "d"})
    assert isinstance(resp, ApiResponse)
    assert resp.status == StatusEnum.error
    assert resp.error is not None
    assert resp.error.code == "RESOURCE_NOT_FOUND"
    assert "c" in resp.error.details or "d" in resp.error.details


def test_make_error_response_fills_details_template():
    from utils.error_codes import make_error_response, ErrorCode
    resp = make_error_response(ErrorCode.UNKNOWN_VERSION, path="/test", details_vars={"version": "3.0", "allowed": "1.2"})
    assert "3.0" in resp.error.details
    assert "1.2" in resp.error.details


def test_make_error_response_handles_missing_template_vars():
    from utils.error_codes import make_error_response, ErrorCode
    resp = make_error_response(ErrorCode.RESOURCE_NOT_FOUND, path="/test")
    assert "{collection}" in resp.error.details or resp.error.details


def test_make_error_response_no_flask_context_does_not_raise():
    from utils.error_codes import make_error_response, ErrorCode
    resp = make_error_response(ErrorCode.TIMEOUT, path=None)
    assert resp.requestId is None


def test_make_error_response_uses_g_session_id(app):
    from flask import g
    from utils.error_codes import make_error_response, ErrorCode
    with app.test_request_context():
        g.session_id = "sess-abc-123"
        resp = make_error_response(ErrorCode.INTERNAL_ERROR, path="/test")
        assert resp.requestId == "sess-abc-123"


def test_make_error_response_logs_error(caplog):
    from utils.error_codes import make_error_response, ErrorCode
    with caplog.at_level(logging.ERROR, logger="utils.error_codes"):
        make_error_response(ErrorCode.UNAUTHORIZED, path="/test", details_vars={"detail": "expired"})
    assert any(
        "UNAUTHORIZED" in r.getMessage() or getattr(r, "error_code", "") == "UNAUTHORIZED"
        for r in caplog.records
    )


def test_make_error_response_includes_user_hint():
    from utils.error_codes import make_error_response, ErrorCode
    r = make_error_response(ErrorCode.PIPELINE_ERROR, user_hint="Try again")
    assert r.error.user_hint == "Try again"


def test_make_error_response_includes_retryable():
    from utils.error_codes import make_error_response, ErrorCode
    r = make_error_response(ErrorCode.PIPELINE_ERROR, retryable=True)
    assert r.error.retryable is True


def test_make_error_response_default_retryable_false():
    from utils.error_codes import make_error_response, ErrorCode
    r = make_error_response(ErrorCode.PIPELINE_ERROR)
    assert r.error.retryable is False


def test_make_error_response_details_present_when_no_vars():
    from utils.error_codes import make_error_response, ErrorCode
    r = make_error_response(ErrorCode.PIPELINE_ERROR)
    # When no details_vars are supplied, the template string is returned as-is
    assert r.error.details is not None
    assert "detail" in r.error.details


def test_athena_error_codes_registered():
    from utils.error_codes import _REGISTRY, make_error_response, ErrorCode
    athena_codes = [
        ErrorCode.ATHENA_AUTH_FAILED,
        ErrorCode.ATHENA_API_ERROR,
        ErrorCode.ATHENA_RATE_LIMIT_ERROR,
        ErrorCode.ATHENA_PATIENT_NOT_FOUND,
        ErrorCode.ATHENA_TIMEOUT,
    ]
    for code in athena_codes:
        assert code in _REGISTRY, f"{code} not in _REGISTRY"
        r = make_error_response(code, "/test")
        assert r.error.code == code.value
