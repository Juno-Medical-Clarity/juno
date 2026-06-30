"""Tests for routes.batch_utils — lock post-rename module surface."""


def test_resolve_requested_runs_importable():
    from routes.batch_utils import _resolve_requested_runs
    assert callable(_resolve_requested_runs)


def test_batch_timestamp_importable():
    from routes.batch_utils import _batch_timestamp
    assert callable(_batch_timestamp)


def test_batch_bp_importable():
    from routes.batch_utils import batch_bp
    assert batch_bp is not None


def test_dead_helpers_removed():
    import routes.batch_utils as m
    dead = [
        "_grading_enabled",
        "_pipeline_for_version",
        "_combined_text_for_dataset_input",
        "_output_name",
        "_batch_progress_error",
        "_pipeline_kwargs_for_batch",
    ]
    for fn in dead:
        assert not hasattr(m, fn), f"{fn} still exists in routes.batch_utils"


