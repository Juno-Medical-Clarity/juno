import pytest


def test_models_exports_new_model_names():
    import models

    from models import (  # noqa: F401
        CarePlan,
        CarePlanInternal,
        CarePlanV1_2,
        CarePlanV1_2StructuredLLM,
        Grading,
        GradingEntry,
        Input,
        InputFile,
        JsonModel,
        Metrics,
        VersionedModel,
        build_grading,
        is_legacy_shape,
    )

    assert models.__all__ == [
        "JsonModel",
        "VersionedModel",
        "CarePlan",
        "CarePlanV1_2",
        "CarePlanV1_2StructuredLLM",
        "CarePlanInternal",
        "is_legacy_shape",
        "Grading",
        "GradingEntry",
        "build_grading",
        "Input",
        "InputFile",
        "Metrics",
    ]


def test_models_do_not_export_removed_aliases():
    with pytest.raises(ImportError):
        from models import SimplifyOutput  # noqa: F401

    with pytest.raises(ImportError):
        from models import SimplifiedCarePlan  # noqa: F401
