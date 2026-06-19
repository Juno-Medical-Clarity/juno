"""Base classes for JSON-serializable models with optional versioning."""

import dataclasses
import typing
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
            # Use get_type_hints to resolve postponed/string annotations
            try:
                resolved_hints = typing.get_type_hints(cls)
            except Exception:
                resolved_hints = {}

            reconstructed_data = {}
            for key, value in data.items():
                field_info = cls.__dataclass_fields__.get(key)
                if field_info and isinstance(value, dict):
                    # Use resolved type hint if available, fall back to field_info.type
                    field_type = resolved_hints.get(key, field_info.type)
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

    Each direct subclass of VersionedJsonModel gets its own _registry
    automatically via __init_subclass__.
    """

    _registry: Dict[str, Type["VersionedJsonModel"]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Give each direct subclass of VersionedJsonModel its own empty registry."""
        super().__init_subclass__(**kwargs)
        # Only give a fresh registry to classes whose immediate parent is
        # VersionedJsonModel (i.e. the "base" model classes), not to concrete
        # registered subclasses whose parent is already a subclass.
        if VersionedJsonModel in cls.__bases__:
            cls._registry = {}

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
            cls._registry[version] = klass
            # Mark as a concrete registered subclass so from_dict skips dispatch
            klass._is_registered = True
            return klass

        return decorator

    @classmethod
    def from_dict(cls: Type[V], data: dict) -> V:
        """Create instance from dictionary using version registry.

        Reads data["version"], looks up the registered subclass,
        and delegates to that subclass's from_dict().

        If called directly on a concrete registered subclass, skips version
        dispatch and falls back to JsonModel.from_dict.

        Args:
            data: Dictionary with at minimum a "version" key.

        Returns:
            New instance of the appropriate registered subclass.

        Raises:
            ValueError: If version is not registered or "version" key is missing.
        """
        # If this is a concrete registered subclass, skip version dispatch
        if getattr(cls, "_is_registered", False):
            return JsonModel.from_dict.__func__(cls, data)  # type: ignore[attr-defined]

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
        return JsonModel.from_dict.__func__(subclass, data)  # type: ignore[attr-defined]
