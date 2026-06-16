"""Base classes for JSON-serializable models with optional versioning."""

import dataclasses
from typing import Any, Dict, Type, TypeVar

T = TypeVar("T", bound="JsonModel")
V = TypeVar("V", bound="VersionedJsonModel")


class JsonModel:
    """Base class for JSON-serializable models.

    Subclasses should use @dataclass decorator. Provides default implementations
    of to_dict() and from_dict() for round-trip serialization.
    """

    def to_dict(self) -> dict:
        """Convert instance to dictionary.

        Default implementation uses dataclasses.asdict().
        Subclasses may override for custom flattening logic.

        Returns:
            Dictionary representation of the instance.
        """
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls: Type[T], data: dict) -> T:
        """Create instance from dictionary.

        Default implementation calls cls(**data).
        Handles nested JsonModel instances by recursively calling from_dict.
        Subclasses may override for custom deserialization logic.

        Args:
            data: Dictionary to deserialize from.

        Returns:
            New instance of this class.
        """
        # Get dataclass fields to handle nested JsonModel instances
        if hasattr(cls, "__dataclass_fields__"):
            reconstructed_data = {}
            for key, value in data.items():
                field_info = cls.__dataclass_fields__.get(key)
                if field_info and isinstance(value, dict):
                    # Check if the field type is a JsonModel subclass
                    field_type = field_info.type
                    # Handle Optional types
                    if hasattr(field_type, "__origin__"):
                        # This is a generic type like Optional[X]
                        if hasattr(field_type, "__args__"):
                            # Get the actual type from Optional/Union
                            for arg in field_type.__args__:
                                if arg is not type(None) and issubclass(arg, JsonModel):
                                    field_type = arg
                                    break
                    if isinstance(field_type, type) and issubclass(field_type, JsonModel):
                        reconstructed_data[key] = field_type.from_dict(value)
                    else:
                        reconstructed_data[key] = value
                else:
                    reconstructed_data[key] = value
            return cls(**reconstructed_data)
        return cls(**data)


class VersionedJsonModel(JsonModel):
    """Base class for versioned JSON models with version registry.

    Subclasses should use @dataclass decorator and register their versions
    using the @register(version_string) decorator.

    Each concrete VersionedJsonModel subclass has its own _registry,
    not shared globally.
    """

    _registry: Dict[str, Type["VersionedJsonModel"]] = {}
    _is_base: bool = False  # Flag to distinguish base vs concrete subclasses

    @classmethod
    def register(cls, version: str):
        """Decorator to register a versioned subclass.

        Args:
            version: Version string to register this class under.

        Returns:
            Decorator function.

        Example:
            @MyVersionedModel.register("1.0")
            @dataclass
            class MyModelV1(MyVersionedModel):
                pass
        """

        def decorator(klass: Type[V]) -> Type[V]:
            if cls._registry is VersionedJsonModel._registry:
                # Initialize per-class registry if not already done
                cls._registry = {}
            cls._registry[version] = klass
            return klass

        return decorator

    @classmethod
    def from_dict(cls: Type[V], data: dict) -> V:
        """Create instance from dictionary using version registry.

        Reads data["version"], looks up the registered subclass,
        and delegates to that subclass's from_dict().

        Args:
            data: Dictionary with at minimum a "version" key.

        Returns:
            New instance of the appropriate registered subclass.

        Raises:
            ValueError: If version is not registered or "version" key is missing.
        """
        # If this is a concrete versioned subclass (not a base), use JsonModel's from_dict
        if not cls._is_base and cls._registry:
            # Check if cls is in the registry of its parent (meaning it's a concrete implementation)
            parent = None
            for base in cls.__bases__:
                if hasattr(base, "_registry") and cls in base._registry.values():
                    parent = base
                    break
            if parent:
                # This is a concrete versioned subclass, use JsonModel's from_dict
                return JsonModel.from_dict.__func__(cls, data)

        if "version" not in data:
            raise ValueError(
                f"Missing 'version' key in data. Required for {cls.__name__}"
            )

        version = data["version"]

        if version not in cls._registry:
            available = ", ".join(sorted(cls._registry.keys()))
            raise ValueError(
                f"Unknown version '{version}' for {cls.__name__}. "
                f"Available versions: {available}"
            )

        subclass = cls._registry[version]
        # Use JsonModel's from_dict directly on the concrete subclass to avoid recursion
        return JsonModel.from_dict.__func__(subclass, data)
