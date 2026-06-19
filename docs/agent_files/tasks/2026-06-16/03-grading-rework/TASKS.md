# Tasks: Grading Rework + Configuration Card

Read `PRD.md` in this folder first.

---

### Task 1 — `GradingEntry` + real `Grading` model

**File:** `backend/models/grading.py` (replaces the Sub-project 1 stub)

Implement `GradingEntry` and `Grading` exactly per PRD.md §4. `Grading` keeps `JsonModel` (not
versioned, per the user's explicit "no version, always latest" instruction). `to_dict()` should
produce `{"entries": [...], "enabled": bool, "graded_at": str | null}` with each entry as a flat dict.

**Acceptance criteria:** Round-trips via `to_dict()`/`from_dict()`. `Grading()` (no args) produces
`{"entries": [], "enabled": True, "graded_at": None}`.

**Depends on:** Sub-project 1 Task 1 (`JsonModel` base class must exist).

---

### Task 2 — `scoring_methods.py`: per-method score extraction

**File:** `backend/utils/scoring_methods.py` (new file)

Implement the six scorer functions and `compute_method_scores()` exactly per PRD.md §4's code sketch:
- `score_smog(text)` — `textstat.smog_index`, `_grade_to_score` from `scoring.py`
- `score_flesch_kincaid(text)` — `textstat.flesch_reading_ease` + `textstat.flesch_kincaid_grade`
- `score_dale_chall(text)` — `textstat.dale_chall_readability_score` + `_dc_grade_range`
- `score_pemat(dimensions)` — weighted combination of existing dimension scores (items 3,8,14,21-22,27-33)
- `score_sam(dimensions)` — content + literacy_demand + layout_typography domains
- `score_cdc_cci(dimensions)` — main_message + behavioral_recommendations + numbers + call_to_action
- `compute_method_scores(text, dimensions)` — calls all six, returns a dict keyed by method name

Each scorer returns a dict with a `"score"` key (0-100 normalized) plus method-specific breakdown
keys (everything except `"score"` goes into `GradingEntry.grade_breakdown`).

Import `_grade_to_score` from `utils.scoring` (it's already defined there — don't duplicate it).

**Acceptance criteria:** Given a known text fixture, `compute_method_scores()` returns a dict with
exactly the six method keys; each has a `"score"` key in [0, 100]; SMOG entry with < 30 sentences
sets `insufficient_sample: True` and `score: 0`; FK entry's `score` equals `round(flesch_reading_ease)`
clamped to [0, 100].

**Depends on:** Sub-project 1 Task 1 (for `JsonModel`); `scoring.py` (imports `_grade_to_score`).

---

### Task 3 — `build_grading()` converter

**File:** `backend/models/grading.py` (same file as Task 1)

Implement `build_grading()` with the updated signature per PRD.md §4:
```python
def build_grading(
    before_score: dict | None, before_text: str | None,
    after_score: dict | None, after_text: str | None,
) -> Grading
```

For each target with a non-None score:
1. Call `compute_method_scores(text, score["dimensions"])` to get the 6 method scores.
2. Append one `GradingEntry` per method (name, target, grade=m["score"],
   grade_breakdown={k:v for k,v if k != "score"}, reasoning=`_METHOD_REASONING[method_name]`).
3. Append the `"combined"` entry: grade=score["composite"], grade_breakdown includes `grade_estimate`,
   `label`, `word_count`, and the full `dimensions` dict (this is what powers the frontend's
   "View full breakdown" bars).

⚠️ Before writing, confirm with the user (PRD.md §8) whether "before" scoring should be kept.
If they say drop it, this function takes only `after_score`/`after_text` — a small change, don't
block on it, just confirm first since it changes the signature.

**Acceptance criteria:** `build_grading(before_score, before_text, after_score, after_text)` produces
14 entries (7 per target × 2 targets): 6 method entries + 1 combined, names are exactly
`("smog", "flesch_kincaid", "dale_chall", "pemat", "sam", "cdc_cci", "combined")`. The combined
entry's `grade_breakdown["dimensions"]` contains all 7 dimension dicts from `score_text()`. The SMOG
entry's `grade_breakdown["grade"]` matches `textstat.smog_index(before_text)`.

**Depends on:** Tasks 1, 2.

---

### Task 4 — Wire `grading_enabled` toggle + `build_grading()` into the v1-2 route

**File:** `backend/routes/simplify_v1_2.py`

1. Read `grading_enabled = (request.form.get("grading_enabled", "true").lower() != "false")`.
2. Gate both `score_text()` calls behind `if grading_enabled:` — when disabled, leave both as `None`
   and skip calls entirely (actual compute saving per PRD.md §2, not just hidden in UI).
3. Update the `build_grading()` call to pass text alongside score dicts (PRD.md §4 updated signature):
   `build_grading(before_score, raw_text, after_score, clarified_text)`.
4. Remove `before_score`/`after_score` from the dict passed into `SimplifiedCarePlan.from_pipeline_result(...)`.
5. Build `grading = build_grading(...) if grading_enabled else Grading(enabled=False)`.
6. Pass `grading` into `SimplifyOutput(...)`.

**Acceptance criteria:** With `grading_enabled` omitted or `"true"`, response `grading.entries` has
14 entries (or 7 if "before" is dropped) and `simplified_care_plan` has no `before_score`/
`after_score` keys. With `grading_enabled="false"`, `grading == {"entries": [], "enabled": false, "graded_at": null}`.

**Depends on:** Tasks 1–3; Sub-project 1 Tasks 5–7 (envelope must exist); Sub-project 2 Task 1.

---

### Task 5 — Apply the same wiring to v1 and v1-1 routes

**Files:** `backend/routes/simplify.py`, `backend/routes/simplify_v1_1.py`

Same change as Task 4, adapted to each route.

**Acceptance criteria:** Same as Task 4, for each route.

**Depends on:** Task 4 (copy the pattern once it's proven there).

---

### Task 6 — New endpoint: `POST /simplify/grade`

**File:** `backend/routes/simplify.py` (add to the existing blueprint, or new `routes/grading.py` —
implementer's call; if a new file, register its blueprint in `routes/__init__.py`)

Implement exactly per PRD.md §4 "Manual re-run". When `saved_id` is given: fetch Firestore doc
(reuse `_get_doc_or_403` from `saved_outputs.py` — move to `backend/utils/firestore_helpers.py` if
currently private, don't duplicate), read `raw.text` + `raw.clarified_text`, call `score_text()` on
both, build `Grading` via `build_grading(before, raw_text, after, clarified_text)`, overwrite
`output_data.grading` in Firestore, return it. When `text`/`clarified_text` given directly: compute
and return without persisting.

**Acceptance criteria:** Per PRD.md §7's three route tests for this endpoint.

**Depends on:** Tasks 1–3.

---

### Task 7 — Frontend: grading toggle in `ConfigurationCard`

**File:** `frontend/src/components/ConfigurationCard.tsx` (from Sub-project 2 Task 4)

Add a `gradingEnabled: boolean` / `onGradingEnabledChange` prop pair and a checkbox, default checked.
Wire the upload submit handler in `SimplifyPage.tsx` to send `grading_enabled` alongside `version`.

**Acceptance criteria:** Submitting with the box unchecked sends `grading_enabled=false`; response has
empty grading entries.

**Depends on:** Sub-project 2 Task 4 (the card must exist); Tasks 4/5 (backend must read the field).

---

### Task 8 — Frontend: `patientScoreFromGrading` + `methodEntriesFromGrading` selectors

**File:** `frontend/src/utils/grading.ts` (new)

Implement both selectors exactly per PRD.md §6:
- `patientScoreFromGrading(grading, target)` — extracts `PatientScore` from the `combined` entry's
  `grade_breakdown.dimensions`; returns `null` if entries empty.
- `methodEntriesFromGrading(grading, target)` — returns the 6 non-combined entries for that target.

**Depends on:** Task 4 (response shape must be stable); Sub-project 1 TS types for `Grading`/`GradingEntry`
(or define minimal inline interfaces if those aren't ready yet).

---

### Task 9 — Frontend: update `ReadabilityCard` call-site + add method cards

**File:** `frontend/src/components/AppointmentNoteV12View.tsx`

1. At the call site (line ~181), replace `result.before_score`/`result.after_score` with
   `patientScoreFromGrading(output.grading, 'before')` / `'after'`; only render `ReadabilityCard`
   when both are non-null. `ReadabilityCard` itself is **not changed** — it still receives the same
   `PatientScore` shape and renders identically.

2. Below `ReadabilityCard`, render a `MethodGradingCards` component (new, in same file or a new
   `MethodGradingCards.tsx`) that maps over `methodEntriesFromGrading(grading, 'after')` and renders
   one card per method showing:
   - Method name + color-coded score bubble (reuse `scoreColor()`)
   - `grade_breakdown` sub-scores as a compact key → value list
   - `reasoning` as a small footnote

   For "before vs after" on method scores, show both targets side-by-side (same pattern as combined
   card's before → after comparison) when both are available.

**Acceptance criteria:** Combined card pixel-identical to pre-change when grading enabled. Six method
cards appear below it. All cards disappear when grading disabled (empty entries). No changes inside
`ReadabilityCard` itself.

**Depends on:** Tasks 6, 8.

---

### Task 10 — Frontend: output-screen Configuration card with "Run Grading" button

**File:** `frontend/src/components/OutputGradingCard.tsx` (new), rendered in result view below
the report and above the sticky download bar.

```tsx
function OutputGradingCard({ output, onGraded }: { output: SimplifyOutput; onGraded: (g: Grading) => void }) {
  const [loading, setLoading] = useState(false);
  async function runGrading() {
    setLoading(true);
    const body = output.metrics.saved_id
      ? { saved_id: output.metrics.saved_id }
      : { text: output.simplified_care_plan.raw?.text, clarified_text: output.simplified_care_plan.raw?.clarified_text };
    const res = await fetch(`${API_BASE}/simplify/grade`, { method: 'POST', headers: {...authHeaders, 'Content-Type': 'application/json'}, body: JSON.stringify(body) });
    const { grading } = await res.json();
    onGraded(grading);
    setLoading(false);
  }
  return (
    <section className="glass-card configuration-card">
      <h2>Configuration</h2>
      <div className="config-field">
        <span>Grading</span>
        <button onClick={runGrading} disabled={loading}>{loading ? 'Grading…' : 'Run Grading'}</button>
      </div>
    </section>
  );
}
```
Match existing auth-header/fetch conventions used elsewhere.

**Acceptance criteria:** Button visible regardless of whether grading already ran. Clicking it updates
both the combined `ReadabilityCard` and the six method cards with fresh scores.

**Depends on:** Task 6, Task 9.

---

### Task 11 — Tests

Cover PRD.md §7 in full:
- Unit tests for each function in `scoring_methods.py` with a known text fixture.
- Unit test `build_grading()` — 14 entries with correct names/targets; combined entry has `dimensions`.
- Route test: `grading_enabled=false` → empty entries on the v1-2 route.
- Three route tests for `POST /simplify/grade` (saved_id path, text/clarified_text path, overwrite check).

**Depends on:** Tasks 1–6.

---

## Summary of what requires you (not a dev agent)

1. **Before Task 3:** confirm whether "before" (input-text) scoring should be kept alongside "after"
   (report) scoring, or dropped now that grading is an explicit, named, toggleable concept.
2. **Optional (PRD.md §8):** confirm whether the three approximated tools (PEMAT, SAM, CDC CCI)
   should all be shown, or only the directly-computable ones (SMOG, FK, Dale-Chall). Default: include
   all six with honest "approximation" labels in `reasoning`.
3. **Cosmetic, non-blocking:** review the output-screen Configuration card copy/placement once Task 10
   has a first pass — not required before starting, just before calling it final.
