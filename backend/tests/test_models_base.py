"""Tests for the strict Pydantic model base and version dispatch mixin."""

import importlib

import pytest
from pydantic import ValidationError

from models.base import JsonModel, VersionedModel


class SimpleModel(JsonModel):
    name: str
    value: int


def test_json_model_forbids_extra_kwargs():
    with pytest.raises(ValidationError):
        SimpleModel(name="test", value=42, unexpected=True)


def test_json_model_to_dict_uses_json_mode_for_serialization():
    original = SimpleModel(name="test", value=42)

    assert original.to_dict() == {"name": "test", "value": 42}
    assert SimpleModel.from_dict(original.to_dict()) == original


def test_versioned_model_dispatches_by_version():
    class Document(VersionedModel):
        title: str

    class DocumentV1(Document):
        version_value = "1.0"

    class DocumentV2(Document):
        version_value = "2.0"
        body: str

    v1 = Document.from_dict({"version": "1.0", "title": "First"})
    v2 = Document.from_dict({"version": "2.0", "title": "Second", "body": "Text"})

    assert isinstance(v1, DocumentV1)
    assert v1.version == "1.0"
    assert v1.title == "First"
    assert isinstance(v2, DocumentV2)
    assert v2.body == "Text"


def test_versioned_model_validates_directly_when_called_on_concrete_subclass():
    class Document(VersionedModel):
        title: str

    class DocumentV1(Document):
        version_value = "1.0"

    instance = DocumentV1.from_dict({"version": "1.0", "title": "Direct"})

    assert isinstance(instance, DocumentV1)
    assert instance.title == "Direct"


def test_versioned_model_missing_version_raises_value_error():
    class Document(VersionedModel):
        title: str

    class DocumentV1(Document):
        version_value = "1.0"

    with pytest.raises(ValueError, match="Missing 'version' key"):
        Document.from_dict({"title": "Missing"})


def test_versioned_model_unknown_version_raises_value_error_with_available_versions():
    class Document(VersionedModel):
        title: str

    class DocumentV1(Document):
        version_value = "1.0"

    class DocumentV2(Document):
        version_value = "2.0"

    with pytest.raises(ValueError) as exc_info:
        Document.from_dict({"version": "9.9", "title": "Unknown"})

    message = str(exc_info.value)
    assert "Unknown version '9.9'" in message
    assert "1.0" in message
    assert "2.0" in message


def test_each_direct_family_base_has_its_own_registry():
    class FirstFamily(VersionedModel):
        pass

    class SecondFamily(VersionedModel):
        pass

    class FirstV1(FirstFamily):
        version_value = "1.0"

    class SecondV1(SecondFamily):
        version_value = "1.0"

    assert FirstFamily._registry is not SecondFamily._registry
    assert FirstFamily._registry == {"1.0": FirstV1}
    assert SecondFamily._registry == {"1.0": SecondV1}


def test_import_models_base_succeeds_without_legacy_references():
    module = importlib.import_module("models.base")

    assert module.JsonModel is JsonModel
    assert module.VersionedModel is VersionedModel
    assert not hasattr(module, "VersionedJsonModel")
    assert "dataclasses" not in module.__dict__
    assert "typing" not in module.__dict__
