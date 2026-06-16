"""SimplifiedCarePlan versioned model.

Carries the pipeline-produced dict across versions 1.0, 1.1, and 1.2.
All three versions map to the same Python class; the class is registered
three times in the VersionedJsonModel registry.
"""

from dataclasses import dataclass

from backend.models.base import VersionedJsonModel


@dataclass
class SimplifiedCarePlan(VersionedJsonModel):
    """Versioned wrapper around the pipeline-produced care plan dict.

    Attributes:
        version: One of "1.0", "1.1", or "1.2".
        data: The pipeline-produced dict (structured/terms/raw/scores fields).
              Stored internally keyed as "data"; flattened on serialisation.
    """

    version: str
    data: dict

    @classmethod
    def from_pipeline_result(cls, version: str, data: dict) -> "SimplifiedCarePlan":
        """Construct from a pipeline output dict and an explicit version string.

        Args:
            version: One of "1.0", "1.1", "1.2".
            data: The raw pipeline output dict (without a "version" key).

        Returns:
            A new SimplifiedCarePlan instance.
        """
        return cls(version=version, data=data)

    def to_dict(self) -> dict:
        """Serialise to a flat dict with "version" as a sibling of all data keys.

        The frontend expects fields like doc_type, diagnosis, terms, etc. at the
        top level alongside "version" — NOT nested under a "data" key.

        Returns:
            {"version": self.version, **self.data}
        """
        return {"version": self.version, **self.data}

    @classmethod
    def from_dict(cls, data: dict) -> "SimplifiedCarePlan":
        """Deserialise from a flattened dict produced by to_dict().

        Splits the incoming dict into the "version" field and everything else
        (which becomes the internal data dict).

        Args:
            data: Flattened dict with at minimum a "version" key.

        Returns:
            A new SimplifiedCarePlan instance.

        Raises:
            ValueError: If "version" is not present in data.
            KeyError: If the version string is not registered.
        """
        if "version" not in data:
            raise ValueError(f"Missing 'version' key in data. Available keys: {list(data.keys())}")
        version = data["version"]
        rest = {k: v for k, v in data.items() if k != "version"}
        # Look up the registered class for this version (may differ in future).
        registered_cls = cls._registry[version]
        return registered_cls(version=version, data=rest)


# Register the same class for all three supported versions by writing directly
# into the registry dict.  Using the register() decorator would set
# SimplifiedCarePlan._is_registered = True on the class itself, which causes
# VersionedJsonModel.from_dict to skip version dispatch and fall back to the
# plain JsonModel.from_dict path — bypassing SimplifiedCarePlan.from_dict.
for _version in ("1.0", "1.1", "1.2"):
    SimplifiedCarePlan._registry[_version] = SimplifiedCarePlan
