def test_make_error_response_returns_api_response():
    from errors import make_error_response, ErrorCode
    from models.errors import ApiResponse, StatusEnum
    resp = make_error_response(ErrorCode.RESOURCE_NOT_FOUND, path="/test")
    assert isinstance(resp, ApiResponse)
    assert resp.status == StatusEnum.error
    assert resp.error.code == "RESOURCE_NOT_FOUND"

def test_make_error_response_autofills_user_hint_from_catalog():
    from errors import make_error_response, ErrorCode
    resp = make_error_response(ErrorCode.VERTEX_QUOTA_EXCEEDED)
    assert resp.error.user_hint is not None
    assert len(resp.error.user_hint) > 0

def test_make_error_response_override_user_hint():
    from errors import make_error_response, ErrorCode
    resp = make_error_response(ErrorCode.PIPELINE_ERROR, user_hint="Custom hint")
    assert resp.error.user_hint == "Custom hint"

def test_make_error_response_autofills_retryable_from_catalog():
    from errors import make_error_response, ErrorCode
    resp = make_error_response(ErrorCode.VERTEX_QUOTA_EXCEEDED)
    assert resp.error.retryable is True

def test_make_error_response_retryable_override():
    from errors import make_error_response, ErrorCode
    resp = make_error_response(ErrorCode.VERTEX_QUOTA_EXCEEDED, retryable=False)
    assert resp.error.retryable is False

def test_make_error_response_no_flask_context_does_not_raise():
    from errors import make_error_response, ErrorCode
    resp = make_error_response(ErrorCode.TIMEOUT)
    assert resp.requestId is None

def test_build_error_data_includes_all_keys():
    from errors import build_error_data, ErrorCode
    from datetime import datetime
    result = build_error_data(ErrorCode.JOB_TIMEOUT)
    assert "timestamp" in result
    assert "code" in result
    assert "message" in result
    assert "user_hint" in result
    assert "retryable" in result
    assert "details" in result
    datetime.fromisoformat(result["timestamp"])

def test_build_error_data_uses_details_key():
    from errors import build_error_data, ErrorCode
    result = build_error_data(ErrorCode.JOB_TIMEOUT, detail="some detail")
    assert "details" in result
    assert "detail" not in result
    assert result["details"] == "some detail"

def test_build_error_data_from_exc_juno_error():
    from errors import build_error_data_from_exc, JunoError, ErrorCode
    try:
        raise JunoError(ErrorCode.LLM_MAX_TOKENS, "too big")
    except JunoError as exc:
        result = build_error_data_from_exc(exc)
    assert result["code"] == "LLM_MAX_TOKENS"
    assert result.get("user_hint") is not None

def test_build_error_data_athena_api_error_no_key_error():
    """Regression test for the worker.py KeyError bug (SP01)."""
    from errors import build_error_data, ErrorCode
    result = build_error_data(ErrorCode.ATHENA_API_ERROR, detail="status=500 path=/test")
    assert result["code"] == "ATHENA_API_ERROR"
    assert result["retryable"] is True

def test_handle_exception_unclassified_returns_500():
    from errors import handle_exception
    result, status = handle_exception(Exception("boom"))
    assert status == 500
