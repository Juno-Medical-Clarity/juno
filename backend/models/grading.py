"""Grading stub model — placeholder for sub-project 3's real schema."""

from dataclasses import dataclass, field

from backend.models.base import JsonModel


@dataclass
class Grading(JsonModel):
    entries: list[dict] = field(default_factory=list)
