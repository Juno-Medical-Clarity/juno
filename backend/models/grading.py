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


_METHOD_REASONING = {
    "smog":           "SMOG (McLaughlin 1969) — counts polysyllabic words; designed for health materials",
    "flesch_kincaid": "Flesch-Kincaid Reading Ease + Grade Level (1975) — sentence length × syllable load",
    "dale_chall":     "Dale-Chall (1948/1995) — difficult words outside the 3,000 familiar-word list",
    "pemat":          "PEMAT (AHRQ 2013) — automated approximation of items 3,8,14,21-22 (understandability) and 27-33 (actionability)",
    "sam":            "SAM (Doak et al. 1996) — automated approximation of content, literacy demand, and layout/typography domains",
    "cdc_cci":        "CDC Clear Communication Index — automated approximation of main message, behavioral recommendations, numbers, and call-to-action items",
}


def build_grading(
    before_score: dict | None, before_text: str | None,
    after_score: dict | None, after_text: str | None,
) -> Grading:
    from utils.scoring_methods import compute_method_scores

    entries = []
    for target, score, text in (
        ("before", before_score, before_text),
        ("after", after_score, after_text),
    ):
        if score is None or text is None:
            continue
        methods = compute_method_scores(text, score["dimensions"])
        for method_name in ("smog", "flesch_kincaid", "dale_chall", "pemat", "sam", "cdc_cci"):
            m = methods[method_name]
            breakdown = {k: v for k, v in m.items() if k != "score"}
            entries.append(GradingEntry(
                name=method_name,
                target=target,
                grade=m["score"],
                grade_breakdown=breakdown,
                reasoning=_METHOD_REASONING[method_name],
            ))
        entries.append(GradingEntry(
            name="combined",
            target=target,
            grade=score["composite"],
            grade_breakdown={
                "grade_estimate": score["grade_estimate"],
                "label":          score["label"],
                "word_count":     score["word_count"],
                "dimensions":     score["dimensions"],
            },
            reasoning=None,
        ))
    return Grading(
        entries=entries,
        enabled=True,
        graded_at=datetime.now(timezone.utc).isoformat(),
    )
