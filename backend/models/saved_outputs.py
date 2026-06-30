"""Request models for saved-outputs endpoints."""
from typing import Optional

from pydantic import BaseModel, field_validator


class RenameOutputRequest(BaseModel):
    name: Optional[str] = None
    comment: Optional[str] = None
    note: Optional[str] = None
    grading: Optional[dict] = None

    @field_validator("name", mode="before")
    @classmethod
    def name_stripped(cls, v):
        if v is None:
            return v
        stripped = str(v).strip()
        if not stripped:
            raise ValueError("name cannot be empty or whitespace")
        if len(stripped) > 200:
            raise ValueError("name exceeds 200 character limit")
        return stripped

    @field_validator("comment", "note", mode="before")
    @classmethod
    def str_fields_max_len(cls, v, info):
        if v is None:
            return v
        if not isinstance(v, str):
            raise ValueError(f"{info.field_name} must be a string")
        if len(v) > 2000:
            raise ValueError(f"{info.field_name} exceeds 2000 character limit")
        return v

    @field_validator("grading", mode="before")
    @classmethod
    def grading_must_be_dict(cls, v):
        if v is not None and not isinstance(v, dict):
            raise ValueError("grading must be an object")
        return v
