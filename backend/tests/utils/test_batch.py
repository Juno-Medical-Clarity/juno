"""Tests for utils.batch — lock post-move module surface."""


def test_resolve_requested_runs_importable():
    from utils.batch import resolve_requested_runs
    assert callable(resolve_requested_runs)


def test_batch_timestamp_importable():
    from utils.batch import batch_timestamp
    assert callable(batch_timestamp)


def test_dead_helpers_removed():
    import utils.batch as m
    dead = [
        "_grading_enabled",
        "_pipeline_for_version",
        "_combined_text_for_dataset_input",
        "_output_name",
        "_batch_progress_error",
        "_pipeline_kwargs_for_batch",
    ]
    for fn in dead:
        assert not hasattr(m, fn), f"{fn} still exists in utils.batch"
