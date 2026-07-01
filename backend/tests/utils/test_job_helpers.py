"""Tests for utils/job_helpers.py."""
from unittest.mock import MagicMock

from utils.job_helpers import canonical_input_type, is_batch_item


def test_canonical_input_type_known_kinds():
    assert canonical_input_type("upload") == "file"
    assert canonical_input_type("doc_id") == "doc_id"
    assert canonical_input_type("text") == "text"
    assert canonical_input_type("batch_dataset") == "text"
    assert canonical_input_type("gcs_batch_dataset") == "text"
    assert canonical_input_type("athena_encounter") == "text"
    assert canonical_input_type("athena_clinical_doc") == "text"


def test_canonical_input_type_unknown_kind_defaults_to_text():
    assert canonical_input_type("something_unrecognized") == "text"


def test_is_batch_item_true_when_batch_group_id_set():
    job = MagicMock(batch_group_id="group-1")
    assert is_batch_item(job) is True


def test_is_batch_item_false_when_batch_group_id_none():
    job = MagicMock(batch_group_id=None)
    assert is_batch_item(job) is False
