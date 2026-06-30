"""Tests for utils/env.py get_env accessor."""

import os
import pytest
from unittest.mock import patch

from utils.env import get_env


def test_returns_env_value(monkeypatch):
    monkeypatch.setenv("TEST_VAR_SP02", "hello")
    assert get_env("TEST_VAR_SP02") == "hello"


def test_returns_default_when_absent():
    os.environ.pop("TEST_VAR_SP02_ABSENT", None)
    assert get_env("TEST_VAR_SP02_ABSENT", "fallback") == "fallback"


def test_returns_none_when_absent_no_default():
    os.environ.pop("TEST_VAR_SP02_ABSENT", None)
    assert get_env("TEST_VAR_SP02_ABSENT") is None


def test_required_raises_when_absent():
    os.environ.pop("TEST_VAR_SP02_REQUIRED", None)
    with pytest.raises(EnvironmentError, match="TEST_VAR_SP02_REQUIRED"):
        get_env("TEST_VAR_SP02_REQUIRED", required=True)


def test_required_succeeds_when_set(monkeypatch):
    monkeypatch.setenv("TEST_VAR_SP02_REQUIRED", "value")
    assert get_env("TEST_VAR_SP02_REQUIRED", required=True) == "value"


def test_mockable_via_patch():
    with patch("utils.env.os.environ.get", return_value="mocked"):
        assert get_env("ANY_KEY") == "mocked"
