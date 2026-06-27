import pytest
from datetime import datetime
from error_codes import ErrorCode
from utils.pipeline_errors import JunoError, build_error_data, build_error_data_from_exc


def test_build_error_data_includes_timestamp():
    result = build_error_data(ErrorCode.JOB_TIMEOUT)
    assert "timestamp" in result
    datetime.fromisoformat(result["timestamp"])


def test_build_error_data_uses_details_key():
    result = build_error_data(ErrorCode.JOB_TIMEOUT, detail="some detail")
    assert "details" in result
    assert "detail" not in result


def test_build_error_data_from_exc_juno_error():
    try:
        raise JunoError(ErrorCode.LLM_MAX_TOKENS, "too big")
    except JunoError as exc:
        result = build_error_data_from_exc(exc)
    assert result["code"] == "LLM_MAX_TOKENS"
    assert result.get("user_hint") is not None
