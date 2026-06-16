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

You want grading to be its own tracked model — individual dimension scores tracked separately from
the combined score, as an extensible array — toggleable per-request (default on), and re-runnable on
demand via a button on the output screen, with each manual re-run overwriting the previous result
(confirmed — no history kept).

## 2. Goals

- Replace the `Grading` stub from Sub-project 1 with the real array-of-entries schema: each of the 7
  research-based dimensions becomes its own entry, plus one combined/composite entry, each entry
  carrying `name`, `grade`, `grade_breakdown`, `reasoning` (and a `target` tag — see below).
- `scoring.py` itself is **not rewritten** — it already computes exactly the right numbers; this
  sub-project adds a thin converter from its existing output shape into the new `Grading` entries,
  so the well-tested scoring math isn't touched.
- A toggle in the Configuration card (upload screen), default **on**: when off, scoring is skipped
  entirely (saves compute, not just hidden in the UI) and `Grading.entries` stays empty.
- A "Run Grading" button in a Configuration card on the output screen (below the report, before the
  sticky action bar), always present — even if grading already ran — that re-runs grading and
  overwrites the stored result.

## 3. Non-Goals

- Not changing the scoring algorithm/weights.
- Not keeping a history of grading re-runs (confirmed: overwrite, not append).
- Not adding LLM-judged/clinical-accuracy grading — "grading" here remains the existing readability
  scoring, just restructured and made controllable. (If you want a second, different kind of grader
  later — e.g. clinical-accuracy-against-source — the array schema is designed to make that additive:
  a new `name` value, no schema change. Worth flagging as a natural future extension, not in scope now.)

## 4. Architecture Decisions

**Why both "before" and "after" survive, even though grading is framed as "grade the generated
report."** The existing before/after comparison (read the original document's score vs. the
simplified report's score) is a genuinely useful, already-built feature — losing it would be a
regression dressed up as a refactor. This sub-project keeps both, modeled as two `target` values
(`"before"`, `"after"`) on each entry, rather than dropping "before" because the literal request text
said "grade the generated report." If you'd rather drop "before" scoring entirely now that it's a
separate, toggleable, named concept, that's a one-line change to the converter (Task 2) — flagged in
TASKS.md as worth a quick confirmation, not blocking the rest of the work.

**`Grading` model (replaces the Sub-project 1 stub):**
```python
@dataclass
class GradingEntry(JsonModel):
    name: str                       # "grade_level" | "jargon_density" | ... | "combined"
    target: str                     # "before" | "after"
    grade: float                    # 0-100
    grade_breakdown: dict | None = None   # e.g. {"raw": 7.2, "unit": "grade"} or {"label": "Patient-friendly", "word_count": 412}
    reasoning: str | None = None    # research citation string, when available

@dataclass
class Grading(JsonModel):
    entries: list[GradingEntry] = field(default_factory=list)
    enabled: bool = True
    graded_at: str | None = None    # ISO8601, set whenever grading actually runs (initial or rerun)
```
8 entries per target × 2 targets = 16 entries in the common case (7 dimensions + 1 combined, for
before and after). When `enabled=False`, `entries=[]` and `graded_at=None`.

**Converter (new function, not a rewrite of `scoring.py`):**
```python
# backend/models/grading.py
def build_grading(before_score: dict | None, after_score: dict | None) -> Grading:
    entries = []
    for target, score in (("before", before_score), ("after", after_score)):
        if score is None:
            continue
        for dim_name, dim in score["dimensions"].items():
            entries.append(GradingEntry(
                name=dim_name, target=target, grade=dim["score"],
                grade_breakdown={"raw": dim["raw"], "unit": dim["unit"], "label": dim["label"]},
                reasoning=score["research_basis"].get(dim_name),
            ))
        entries.append(GradingEntry(
            name="combined", target=target, grade=score["composite"],
            grade_breakdown={"grade_estimate": score["grade_estimate"], "label": score["label"], "word_count": score["word_count"]},
            reasoning=None,
        ))
    return Grading(entries=entries, enabled=True, graded_at=datetime.now(timezone.utc).isoformat())
```

**Where `before_score`/`after_score` go.** They are **removed** from `SimplifiedCarePlan.data` (no
longer nested under the report) — they exist *only* inside `Grading.entries` now. This is the actual
substance of "split into multiple parts, each with its own model": no field should be duplicated
across two models. `simplified_care_plan.raw.text` / `.clarified_text` remain (grading needs them as
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
- `ReadabilityCard` in `AppointmentNoteV12View.tsx` (currently takes `before`/`after` `PatientScore`
  props sourced from `result.before_score`/`result.after_score`) is **not rewritten** — instead, a new
  small selector `patientScoreFromGrading(grading, target): PatientScore | null` reconstructs the same
  `PatientScore` shape `ReadabilityCard` already expects, from `grading.entries` filtered by `target`.
  This keeps the existing, already-working rendering code untouched and limits the diff to the call
  site. If `grading.entries` is empty (grading disabled), the caller doesn't render `ReadabilityCard`
  at all.

## 7. Testing

- Unit test `build_grading()` against a fixed `before_score`/`after_score` fixture (use `scoring.py`'s
  existing test fixtures if present) — assert 16 entries with the right `name`/`target` combinations.
- Route test: `grading_enabled=false` → response `grading.entries == []`, `grading.enabled == false`.
- Route test: `POST /simplify/grade` with a real `saved_id` → Firestore doc's `output_data.grading`
  changes to the new value; calling it twice produces two different `graded_at` timestamps and the
  second overwrites (no array growth).
- Route test: `POST /simplify/grade` with `text`/`clarified_text` only → returns a `Grading`, no
  Firestore write attempted.
- Frontend: manual run — toggle grading off, confirm no readability card renders and no scoring delay;
  toggle on, confirm it renders; click "Run Grading" on the output screen, confirm scores update.

## 8. Manual Intervention Required From You

- **Confirm "before" scoring stays** (PRD.md §4) — default assumption is yes, keep both before/after;
  say so if you'd rather drop "before" now that it's explicitly modeled.
- **Decide placement/wording** for the output-screen Configuration card's grading section (exact
  copy/microcopy is a cosmetic call, not flagged as blocking, but you may want to review wireframe
  before final styling — call out during implementation review, not before starting).
