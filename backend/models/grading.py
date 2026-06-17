from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.models.base import JsonModel


@dataclass
class GradingEntry(JsonModel):
    name: str       # "smog" | "flesch_kincaid" | "dale_chall" | "pemat" | "sam" | "cdc_cci" | "combined"
    target: str     # "before" | "after"
    grade: float    # 0-100 normalized score
    grade_breakdown: dict | None = None
    reasoning: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "target": self.target,
            "grade": self.grade,
            "grade_breakdown": self.grade_breakdown,
            "reasoning": self.reasoning,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GradingEntry":
        return cls(
            name=data["name"],
            target=data["target"],
            grade=data["grade"],
            grade_breakdown=data.get("grade_breakdown"),
            reasoning=data.get("reasoning"),
        )


@dataclass
class Grading(JsonModel):
    entries: list[GradingEntry] = field(default_factory=list)
    enabled: bool = True
    graded_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "enabled": self.enabled,
            "graded_at": self.graded_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Grading":
        return cls(
            entries=[GradingEntry.from_dict(e) for e in data.get("entries", [])],
            enabled=data.get("enabled", True),
            graded_at=data.get("graded_at"),
        )
