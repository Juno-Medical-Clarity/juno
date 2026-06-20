"""Base classes for strict JSON-serializable Pydantic models."""

from __future__ import annotations

from typing import Any, ClassVar, Type, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T", bound="JsonModel")


class JsonModel(BaseModel):
    """Strict Pydantic base for all backend models."""

    model_config = ConfigDict(extra="forbid")

    def to_dict(self) -> dict:
        """Convert the model to a JSON-native dictionary."""
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls: Type[T], data: dict) -> T:
        """Validate a dictionary into this model class."""
        return cls.model_validate(data)


VT = TypeVar("VT", bound="VersionedModel")


class VersionedModel(JsonModel):
    """Mixin for model families dispatched by a ``version`` field."""

    version: str
    _registry: ClassVar[dict[str, Type["VersionedModel"]]] = {}
    version_value: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if VersionedModel in cls.__bases__:
            cls._registry = {}
        elif getattr(cls, "version_value", None) is not None:
            cls._registry[cls.version_value] = cls

    @classmethod
    def from_dict(cls: Type[VT], data: dict) -> VT:
        """Dispatch family-base validation to the subclass for ``data['version']``."""
        if cls.version_value is not None:
            return cls.model_validate(data)

        version = data.get("version")
        if version is None:
            raise ValueError(f"Missing 'version' key for {cls.__name__}")

        subclass = cls._registry.get(version)
        if subclass is None:
            available = ", ".join(sorted(cls._registry)) or "(none registered)"
            raise ValueError(
                f"Unknown version {version!r} for {cls.__name__}. Available: {available}"
            )

        return subclass.model_validate(data)  # type: ignore[return-value]
