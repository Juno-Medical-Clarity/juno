"""Tests for backend.models.base classes."""

import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.models.base import JsonModel, VersionedJsonModel


class TestJsonModel(unittest.TestCase):
    """Tests for JsonModel base class."""

    def test_json_model_to_dict_roundtrip(self):
        """Test that a JsonModel subclass round-trips through to_dict/from_dict."""

        @dataclass
        class SimpleModel(JsonModel):
            name: str
            value: int

        original = SimpleModel(name="test", value=42)
        data = original.to_dict()

        self.assertEqual(data, {"name": "test", "value": 42})

        reconstructed = SimpleModel.from_dict(data)
        self.assertEqual(reconstructed, original)
        self.assertEqual(reconstructed.name, "test")
        self.assertEqual(reconstructed.value, 42)

    def test_json_model_nested(self):
        """Test JsonModel with nested dataclass."""

        @dataclass
        class Inner(JsonModel):
            field: str

        @dataclass
        class Outer(JsonModel):
            inner: Inner
            count: int

        original = Outer(inner=Inner(field="nested"), count=5)
        data = original.to_dict()

        self.assertEqual(data, {"inner": {"field": "nested"}, "count": 5})

        reconstructed = Outer.from_dict(data)
        self.assertEqual(reconstructed, original)


class TestVersionedJsonModel(unittest.TestCase):
    """Tests for VersionedJsonModel with registry."""

    def test_versioned_model_register_and_dispatch(self):
        """Test that VersionedJsonModel registers versions and dispatches correctly."""

        @dataclass
        class MyVersionedModel(VersionedJsonModel):
            """Base versioned model for testing."""

            version: str
            data: str

        @MyVersionedModel.register("1.0")
        @dataclass
        class MyModelV1(MyVersionedModel):
            data: str

        @MyVersionedModel.register("2.0")
        @dataclass
        class MyModelV2(MyVersionedModel):
            data: str
            extra: str = "default"

        # Test V1 dispatch
        v1_dict = {"version": "1.0", "data": "test_v1"}
        v1_instance = MyVersionedModel.from_dict(v1_dict)
        self.assertIsInstance(v1_instance, MyModelV1)
        self.assertEqual(v1_instance.data, "test_v1")
        self.assertEqual(v1_instance.version, "1.0")

        # Test V2 dispatch
        v2_dict = {"version": "2.0", "data": "test_v2", "extra": "custom"}
        v2_instance = MyVersionedModel.from_dict(v2_dict)
        self.assertIsInstance(v2_instance, MyModelV2)
        self.assertEqual(v2_instance.data, "test_v2")
        self.assertEqual(v2_instance.extra, "custom")
        self.assertEqual(v2_instance.version, "2.0")

    def test_versioned_model_missing_version_key(self):
        """Test that missing 'version' key raises ValueError."""

        @dataclass
        class MyVersionedModel(VersionedJsonModel):
            version: str

        @MyVersionedModel.register("1.0")
        @dataclass
        class MyModelV1(MyVersionedModel):
            pass

        with self.assertRaises(ValueError) as cm:
            MyVersionedModel.from_dict({"data": "test"})

        self.assertIn("Missing 'version' key", str(cm.exception))

    def test_versioned_model_unknown_version(self):
        """Test that unknown version raises ValueError with available versions."""

        @dataclass
        class MyVersionedModel(VersionedJsonModel):
            version: str

        @MyVersionedModel.register("1.0")
        @dataclass
        class MyModelV1(MyVersionedModel):
            pass

        @MyVersionedModel.register("2.0")
        @dataclass
        class MyModelV2(MyVersionedModel):
            pass

        with self.assertRaises(ValueError) as cm:
            MyVersionedModel.from_dict({"version": "3.0"})

        error_msg = str(cm.exception)
        self.assertIn("Unknown version '3.0'", error_msg)
        self.assertIn("Available versions: 1.0, 2.0", error_msg)

    def test_versioned_model_per_class_registry(self):
        """Test that each VersionedJsonModel subclass has its own registry."""

        @dataclass
        class ModelA(VersionedJsonModel):
            version: str

        @dataclass
        class ModelB(VersionedJsonModel):
            version: str

        @ModelA.register("1.0")
        @dataclass
        class ModelAV1(ModelA):
            pass

        @ModelB.register("1.0")
        @dataclass
        class ModelBV1(ModelB):
            pass

        # Registries should be separate
        self.assertIn("1.0", ModelA._registry)
        self.assertIn("1.0", ModelB._registry)
        self.assertIsNot(ModelA._registry, ModelB._registry)
        self.assertIs(ModelA._registry["1.0"], ModelAV1)
        self.assertIs(ModelB._registry["1.0"], ModelBV1)


if __name__ == "__main__":
    unittest.main()
