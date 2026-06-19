# PRD: Grading Rework + Configuration Card (Toggle + Run Grading)

Sub-project 3 of 5. **Depends on Sub-project 1** (the `Grading` stub model, the envelope) and
**Sub-project 2** (the `ConfigurationCard` component, since this sub-project adds a field to it).

## 1. Problem

"Grading" today is the Patient Accessibility Score in `backend/utils/scoring.py`: a composite 0–100
score plus 7 weighted sub-dimensions (`grade_level`, `jargon_density`, `sentence_complexity`,
`passive_voice`, `actionability`, `numeracy_clarity`, `structural_clarity`), each grounded in a named
literacy-research tool (SMOG, Flesch-Kincaid, Dale-Chall, PEMAT, SAM, CDC Clear Communication Index —
see `RESEARCH_BASIS` in `scoring.py`). It's computed silently, twice (`before_score` on the raw input
text, `after_score` on the clarified output text), and bolted onto the result dict. It cannot be
turned off, and there's no way to re-run it after the fact.

You want grading to be its own tracked model — individual **method-level scores** tracked separately
from the combined score, as an extensible array — toggleable per-request (default on), and re-runnable
on demand via a button on the output screen, with each manual re-run overwriting the previous result
(confirmed — no history kept).

## 2. Goals

- Replace the `Grading` stub from Sub-project 1 with the real array-of-entries schema: each of the 6
  validated research tools (SMOG, Flesch-Kincaid, Dale-Chall, PEMAT, SAM, CDC Clear Communication
  Index) becomes its own entry, plus one combined/composite entry, each carrying `name`, `grade`,
  `grade_breakdown`, `reasoning` (and a `target` tag — see below).
- `scoring.py` itself is **not rewritten** — it already computes the composite correctly. This
  sub-project adds (a) a new `backend/utils/scoring_methods.py` that extracts per-method raw scores
  from the same `textstat` calls, and (b) a thin `build_grading()` converter that assembles
  `GradingEntry` objects from both — the composite math is untouched.
- A toggle in the Configuration card (upload screen), default **on**: when off, scoring is skipped
  entirely (saves compute, not just hidden in the UI) and `Grading.entries` stays empty.
- A "Run Grading" button in a Configuration card on the output screen (below the report, before the
  sticky action bar), always present — even if grading already ran — that re-runs grading and
  overwrites the stored result.

## 3. Non-Goals

- Not changing the composite scoring algorithm/weights.
- Not keeping a history of grading re-runs (confirmed: overwrite, not append).
- Not adding LLM-judged/clinical-accuracy grading — "grading" here remains the existing readability
  scoring, just restructured and made controllable. (If you want a second, different kind of grader
  later — e.g. clinical-accuracy-against-source — the array schema is designed to make that additive:
  a new `name` value, no schema change. Worth flagging as a natural future extension, not in scope now.)
- PEMAT, SAM, and CDC CCI are inherently human-rater checklists; the automated scores here are
  honest approximations from automatable signals (bullets, active voice, you-rate, word difficulty,
  sentence length, etc.) — not full checklist runs. Each entry's `reasoning` field documents which
  items/domains could be automated.

## 4. Architecture Decisions

**Why both "before" and "after" survive, even though grading is framed as "grade the generated
report."** The existing before/after comparison (read the original document's score vs. the
simplified report's score) is a genuinely useful, already-built feature — losing it would be a
regression dressed up as a refactor. This sub-project keeps both, modeled as two `target` values
(`"before"`, `"after"`) on each entry, rather than dropping "before" because the literal request text
said "grade the generated report." If you'd rather drop "before" scoring entirely now that it's a
separate, toggleable, named concept, that's a one-line change to the converter — flagged in TASKS.md
as worth a quick confirmation, not blocking the rest of the work.

**`Grading` model (replaces the Sub-project 1 stub):**
```python
@dataclass
class GradingEntry(JsonModel):
    name: str       # "smog" | "flesch_kincaid" | "dale_chall" | "pemat" | "sam" | "cdc_cci" | "combined"
    target: str     # "before" | "after"
    grade: float    # 0-100 normalized score
    grade_breakdown: dict | None = None   # method-specific sub-scores (see below)
    reasoning: str | None = None          # which items/formula this is approximating

@dataclass
class Grading(JsonModel):
    entries: list[GradingEntry] = field(default_factory=list)
    enabled: bool = True
    graded_at: str | None = None    # ISO8601, set whenever grading actually runs (initial or rerun)
```
7 entries per target × 2 targets = 14 entries in the common case (6 methods + 1 combined, for
before and after). When `enabled=False`, `entries=[]` and `graded_at=None`.

**Per-method `grade` normalization and `grade_breakdown` shapes:**

| `name`         | `grade` (0-100)                                                  | `grade_breakdown` keys                                              |
|----------------|------------------------------------------------------------------|---------------------------------------------------------------------|
| `smog`         | `_grade_to_score(smog_grade)` from `scoring.py`; 0 if < 30 sentences | `{ "grade": float, "insufficient_sample": bool }`           |
| `flesch_kincaid` | `flesch_reading_ease` (already 0-100, higher=easier)          | `{ "reading_ease": float, "grade_level": float }`                   |
| `dale_chall`   | linear map: raw ≤ 4.9 → 100, raw ≥ 9.0 → 0                     | `{ "raw_score": float, "grade_range": str }`                        |
| `pemat`        | `(understandability + actionability) / 2`                       | `{ "understandability": int, "actionability": int }`                |
| `sam`          | `total_points / 42 * 100` (of automatable domains)              | `{ "content": int, "literacy_demand": int, "layout_typography": int }` |
| `cdc_cci`      | `items_met / total_applicable * 100`                            | `{ "main_message": int, "behavioral_recommendations": int, "numbers": int, "call_to_action": int }` |
| `combined`     | existing composite (unchanged)                                  | `{ "grade_estimate": float, "label": str, "word_count": int, "dimensions": dict }` |

Note: the `combined` entry's `grade_breakdown.dimensions` includes the full existing 7-dimension
dict from `score_text()` output — this is what powers the "View full breakdown" bars in the frontend
(unchanged from today's display).

**New `scoring_methods.py` (computes per-method scores from text):**
```python
# backend/utils/scoring_methods.py
import textstat
from utils.scoring import _grade_to_score, RESEARCH_BASIS

def score_smog(text: str) -> dict:
    sentence_count = textstat.sentence_count(text)
    if sentence_count < 30:
        return {"grade": 0.0, "insufficient_sample": True, "score": 0}
    grade = textstat.smog_index(text)
    return {"grade": round(grade, 1), "insufficient_sample": False, "score": _grade_to_score(grade)}

def score_flesch_kincaid(text: str) -> dict:
    reading_ease = textstat.flesch_reading_ease(text)
    grade_level = textstat.flesch_kincaid_grade(text)
    return {
        "reading_ease": round(reading_ease, 1),
        "grade_level": round(grade_level, 1),
        "score": max(0, min(100, round(reading_ease))),
    }

def score_dale_chall(text: str) -> dict:
    raw = textstat.dale_chall_readability_score(text)
    grade_range = _dc_grade_range(raw)
    # raw ≤ 4.9 → grade 4 (best), raw ≥ 9.0 → grade 16 (worst)
    grade = max(4.0, min(16.0, raw / 9.0 * 12 + 4))
    return {"raw_score": round(raw, 2), "grade_range": grade_range, "score": _grade_to_score(grade)}

def _dc_grade_range(raw: float) -> str:
    if raw >= 9.0: return "College level"
    if raw >= 8.0: return "11th–12th grade"
    if raw >= 7.0: return "9th–10th grade"
    if raw >= 6.0: return "7th–8th grade"
    if raw >= 5.0: return "5th–6th grade"
    return "4th grade or below"

def score_pemat(dimensions: dict) -> dict:
    """Approximate PEMAT from already-computed dimension scores.

    Understandability items covered: jargon_density (item 3), sentence_complexity (item 8),
    passive_voice (item 14), numeracy_clarity (items 21-22), structural_clarity (items 9-12).
    Actionability items covered: actionability subscale (items 27-33).
    """
    understandability = round((
        dimensions["jargon_density"]["score"] * 0.25 +
        dimensions["sentence_complexity"]["score"] * 0.25 +
        dimensions["passive_voice"]["score"] * 0.20 +
        dimensions["numeracy_clarity"]["score"] * 0.15 +
        dimensions["structural_clarity"]["score"] * 0.15
    ))
    actionability = dimensions["actionability"]["score"]
    combined = round((understandability + actionability) / 2)
    return {"understandability": understandability, "actionability": actionability, "score": combined}

def score_sam(dimensions: dict) -> dict:
    """Approximate automatable SAM domains (Doak et al. 1996).

    Content domain (0-8): reading level + vocabulary match → grade_level + jargon_density
    Literacy demand (0-14): reading level + writing style → grade_level + sentence_complexity + passive_voice
    Layout/typography (0-6): structure → structural_clarity
    """
    content = round(
        (dimensions["grade_level"]["score"] * 0.5 + dimensions["jargon_density"]["score"] * 0.5) / 100 * 8
    )
    literacy_demand = round(
        (dimensions["grade_level"]["score"] * 0.5 +
         dimensions["sentence_complexity"]["score"] * 0.3 +
         dimensions["passive_voice"]["score"] * 0.2) / 100 * 14
    )
    layout_typography = round(dimensions["structural_clarity"]["score"] / 100 * 6)
    total_possible = 8 + 14 + 6  # 28, only automatable domains
    total = content + literacy_demand + layout_typography
    score = round(total / total_possible * 100)
    return {"content": content, "literacy_demand": literacy_demand,
            "layout_typography": layout_typography, "score": score}

def score_cdc_cci(dimensions: dict) -> dict:
    """Approximate CDC Clear Communication Index automatable items.

    Main message: actionability (action-oriented main message)
    Behavioral recommendations: actionability + numeracy_clarity
    Numbers: numeracy_clarity
    Call to action: actionability
    """
    main_message = 1 if dimensions["actionability"]["score"] >= 50 else 0
    behavioral = 1 if (
        dimensions["actionability"]["score"] + dimensions["numeracy_clarity"]["score"]
    ) / 2 >= 50 else 0
    numbers = 1 if dimensions["numeracy_clarity"]["score"] >= 50 else 0
    call_to_action = 1 if dimensions["actionability"]["score"] >= 60 else 0
    items_met = main_message + behavioral + numbers + call_to_action
    score = round(items_met / 4 * 100)
    return {
        "main_message": main_message,
        "behavioral_recommendations": behavioral,
        "numbers": numbers,
        "call_to_action": call_to_action,
        "score": score,
    }

def compute_method_scores(text: str, dimensions: dict) -> dict:
    """Compute all six method-level scores for a given text + precomputed dimension dict."""
    return {
        "smog":           score_smog(text),
        "flesch_kincaid": score_flesch_kincaid(text),
        "dale_chall":     score_dale_chall(text),
        "pemat":          score_pemat(dimensions),
        "sam":            score_sam(dimensions),
        "cdc_cci":        score_cdc_cci(dimensions),
    }
```

**Converter (new function, not a rewrite of `scoring.py`):**
```python
# backend/models/grading.py
from utils.scoring_methods import compute_method_scores

_METHOD_REASONING = {
    "smog":           "SMOG (McLaughlin 1969) — counts polysyllabic words; designed for health materials",
    "flesch_kincaid": "Flesch-Kincaid Reading Ease + Grade Level (1975) — sentence length × syllable load",
    "dale_chall":     "Dale-Chall (1948/1995) — difficult words outside the 3,000 familiar-word list",
    "pemat":          "PEMAT (AHRQ 2013) — automated approximation of items 3,8,14,21-22 (understandability) and 27-33 (actionability)",
    "sam":            "SAM (Doak et al. 1996) — automated approximation of content, literacy demand, and layout/typography domains",
    "cdc_cci":        "CDC Clear Communication Index — automated approximation of main message, behavioral recommendations, numbers, and call-to-action items",
}

def build_grading(before_score: dict | None, after_score: dict | None) -> Grading:
    entries = []
    for target, score in (("before", before_score), ("after", after_score)):
        if score is None:
            continue
        methods = compute_method_scores(
            text=score["_source_text"],   # see note below about passing text through
            dimensions=score["dimensions"],
        )
        for method_name in ("smog", "flesch_kincaid", "dale_chall", "pemat", "sam", "cdc_cci"):
            m = methods[method_name]
            breakdown = {k: v for k, v in m.items() if k != "score"}
            entries.append(GradingEntry(
                name=method_name, target=target, grade=m["score"],
                grade_breakdown=breakdown,
                reasoning=_METHOD_REASONING[method_name],
            ))
        entries.append(GradingEntry(
            name="combined", target=target, grade=score["composite"],
            grade_breakdown={
                "grade_estimate": score["grade_estimate"],
                "label":          score["label"],
                "word_count":     score["word_count"],
                "dimensions":     score["dimensions"],
            },
            reasoning=None,
        ))
    return Grading(entries=entries, enabled=True, graded_at=datetime.now(timezone.utc).isoformat())
```

**Passing text into `build_grading`:** `score_text()` currently returns only the computed scores, not
the source text. Two options:
- (a) Add `"_source_text": text` to the `score_text()` return dict (private key, not a schema change).
- (b) Pass `text` alongside the score dict wherever `build_grading()` is called.

Option (b) is cleaner — callers already have `text`; no mutation of `score_text()`'s contract needed.
Update `build_grading()` signature accordingly:

```python
def build_grading(
    before_score: dict | None, before_text: str | None,
    after_score: dict | None, after_text: str | None,
) -> Grading
```

**Where `before_score`/`after_score` go.** They are **removed** from `SimplifiedCarePlan.data` (no
longer nested under the report) — they exist *only* inside `Grading.entries` now. `simplified_care_plan.raw.text` / `.clarified_text` remain (grading needs them as
input when re-running on demand — see below), but the score numbers themselves move out.

**Request-level toggle.** New field on `POST /simplify`: `grading_enabled` (string `"true"`/`"false"`,
default `"true"` if omitted — matches "by default, should be enabled"). When `"false"`, the route
skips both `score_text()` calls entirely (not just discards the result — actually saves the compute,
per Goals) and builds `Grading()` with `enabled=False`.

**Manual re-run ("Run Grading" button).** New endpoint:
```
POST /simplify/grade
  body: { "saved_id": "<uuid>" }                          — re-grades a persisted output, overwrites it
     OR { "text": "...", "clarified_text": "..." }         — re-grades an ephemeral (unsaved) result
  returns: { "grading": <Grading.to_dict()> }
```
One endpoint, two modes, because not every result has a `saved_id` (results from `doc_id`-sourced
requests are never persisted — see `simplify_v1_2.py`'s existing `if resolved.source_kind ==
"doc_id": ... return` early-exit before the save step). When `saved_id` is given: fetch the Firestore
doc (reuse the existing ownership-check pattern from `saved_outputs.py`'s `_get_doc_or_403`), read
`output_data.simplified_care_plan.raw.text` / `.clarified_text`, run `score_text()` on each, build a
new `Grading` via `build_grading()`, **overwrite** `output_data.grading` in Firestore (per your
decision — no history array, this replaces the prior value), return it. When `text`/`clarified_text`
are given directly instead: compute and return the `Grading` without persisting anywhere (there's
nowhere to persist it to) — the frontend updates its in-memory display only, and a page refresh would
lose that re-grade, which is the correct, expected behavior for an unsaved result.

**Configuration card additions:**
- *Upload screen* (extends the card from Sub-project 2): a checkbox, "Enable grading", default
  checked, wired to the `grading_enabled` request field.
- *Output screen* (new placement — below the rendered report, above the existing sticky
  download/action bar per the layout already established by the recent "move download buttons" fix):
  a "Grading" section inside a Configuration card with a "Run Grading" button. Always rendered,
  whether or not grading already ran for this result (so a user who disabled grading at upload time,
  or wants a fresh score after editing nothing but just double-checking, can trigger it from here).

## 5. API Change Summary

```
POST /simplify
  adds: grading_enabled: "true" | "false"   (default "true")

POST /simplify/grade   (new)
  body: { saved_id } | { text, clarified_text }
  returns: { grading: Grading }
```

## 6. Frontend Change Summary

- `ConfigurationCard` (from Sub-project 2) gains a grading checkbox.
- New `GradingConfigurationCard` (or extend the same component — naming/placement is a small
  judgement call for the implementer) on the output screen with the "Run Grading" button.
- `ReadabilityCard` in `AppointmentNoteV12View.tsx` is **extended, not rewritten**:
  - The **combined entry** drives the existing top-level display (before/after bubbles, grade_estimate,
    jargon %, and the "View full breakdown" bars) — unchanged from today. A new selector
    `patientScoreFromGrading(grading, target)` reconstructs the `PatientScore` shape from the
    `combined` entry's `grade_breakdown.dimensions` dict.
  - Six new **method cards** are rendered below (or inside a collapsible panel within) the combined
    card, one per method (SMOG, Flesch-Kincaid, Dale-Chall, PEMAT, SAM, CDC CCI), each showing:
    - The method name and its 0-100 `grade` score with a color-coded bubble
    - The `grade_breakdown` sub-scores in a compact key→value layout
    - The `reasoning` string as a footnote/tooltip
  - If `grading.entries` is empty (grading disabled), neither the combined card nor method cards render.

**Selector (in `frontend/src/utils/grading.ts`):**
```ts
export function patientScoreFromGrading(grading: Grading, target: 'before' | 'after'): PatientScore | null {
  const combined = grading.entries.find(e => e.name === 'combined' && e.target === target);
  if (!combined?.grade_breakdown?.dimensions) return null;
  const dims = combined.grade_breakdown.dimensions;
  return {
    composite:      combined.grade,
    grade_estimate: combined.grade_breakdown.grade_estimate ?? 0,
    label:          combined.grade_breakdown.label ?? '',
    word_count:     combined.grade_breakdown.word_count ?? 0,
    dimensions:     Object.fromEntries(
      Object.entries(dims).map(([k, v]: [string, any]) => [k, { score: v.score, raw: v.raw, label: v.label, unit: v.unit }])
    ) as PatientScore['dimensions'],
  };
}

export function methodEntriesFromGrading(grading: Grading, target: 'before' | 'after'): GradingEntry[] {
  return grading.entries.filter(e => e.target === target && e.name !== 'combined');
}
```

## 7. Testing

- Unit test `build_grading()` against fixed `before_score`/`after_score` fixtures — assert 14 entries
  (7 per target × 2) with correct `name`/`target` combinations; assert SMOG entry has
  `grade_breakdown.grade` matching `textstat.smog_index(before_text)`.
- Unit test each function in `scoring_methods.py` independently with a known text fixture.
- Route test: `grading_enabled=false` → response `grading.entries == []`, `grading.enabled == false`.
- Route test: `POST /simplify/grade` with a real `saved_id` → Firestore doc's `output_data.grading`
  changes to the new value; calling it twice produces two different `graded_at` timestamps and the
  second overwrites (no array growth).
- Route test: `POST /simplify/grade` with `text`/`clarified_text` only → returns a `Grading`, no
  Firestore write attempted.
- Frontend: manual run — toggle grading off, confirm no readability card renders and no scoring delay;
  toggle on, confirm combined + 6 method cards render; click "Run Grading" on the output screen,
  confirm scores update.

## 8. Manual Intervention Required From You

- **Confirm "before" scoring stays** (PRD.md §4) — default assumption is yes, keep both before/after;
  say so if you'd rather drop "before" now that it's explicitly modeled.
- **Decide placement/wording** for the output-screen Configuration card's grading section (exact
  copy/microcopy is a cosmetic call, not flagged as blocking, but you may want to review wireframe
  before final styling — call out during implementation review, not before starting).
- **PEMAT/SAM/CDC CCI approximation fidelity** — the automated scores are honest approximations, not
  full checklist runs. If you want any of these dropped (showing only the directly-computable tools:
  SMOG, Flesch-Kincaid, Dale-Chall), that's a one-line change to `compute_method_scores()`. The
  three approximated tools are included by default since the scoring code already approximates their
  items — it's just labeling them honestly.
