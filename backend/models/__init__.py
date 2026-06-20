"""Backend models package for JSON serialization and versioning."""

from importlib import import_module

from .base import JsonModel, VersionedModel

__all__ = [
    "Grading",
    "Input",
    "InputFile",
    "JsonModel",
    "Metrics",
    "SimplifiedCarePlan",
    "SimplifyOutput",
    "VersionedModel",
    "is_legacy_shape",
]

_LAZY_EXPORTS = {
    "Grading": (".grading", "Grading"),
    "Input": (".input", "Input"),
    "InputFile": (".input", "InputFile"),
    "Metrics": (".metrics", "Metrics"),
    "SimplifiedCarePlan": (".care_plan", "SimplifiedCarePlan"),
    "SimplifyOutput": (".envelope", "SimplifyOutput"),
    "is_legacy_shape": (".envelope", "is_legacy_shape"),
}


def __getattr__(name: str):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
