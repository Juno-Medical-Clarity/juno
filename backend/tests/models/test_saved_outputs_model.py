"""Tests for models/saved_outputs.py"""
import pytest
from pydantic import ValidationError
from models.saved_outputs import RenameOutputRequest


def test_rename_output_request_name_stripped():
    req = RenameOutputRequest(name=" foo ")
    assert req.name == "foo"


def test_rename_output_request_empty_name_raises():
    with pytest.raises(ValidationError):
        RenameOutputRequest(name=" ")


def test_rename_output_request_name_too_long():
    with pytest.raises(ValidationError):
        RenameOutputRequest(name="a" * 201)


def test_rename_output_request_comment_not_string_raises():
    with pytest.raises(ValidationError):
        RenameOutputRequest(comment=123)


def test_rename_output_request_all_none():
    req = RenameOutputRequest()
    assert req.name is None
    assert req.comment is None
    assert req.note is None
    assert req.grading is None
