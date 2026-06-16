# Tasks: Grading Rework + Configuration Card

Read `PRD.md` in this folder first.

---

### Task 1 — `GradingEntry` + real `Grading` model

**File:** `backend/models/grading.py` (replaces the Sub-project 1 stub)

Implement `GradingEntry` and `Grading` exactly per PRD.md §4. `Grading` keeps `JsonModel` (not
versioned, per the user's explicit "no version, always latest" instruction). `to_dict()` should
produce `{"entries": [...], "enabled": bool, "graded_at": str | null}` with each entry as a flat dict.

**Acceptance criteria:** Round-trips via `to_dict()`/`from_dict()`. `Grading()` (no args) produces
`{"entries": [], "enabled": True, "graded_at": None}` (matches the dataclass defaults — note this
default differs slightly from PRD's "disabled means enabled=False": the *default* enabled flag is
`True` per "by default grading should be enabled", but an *empty* Grading before any scoring has run
also looks like this; routes are responsible for setting `enabled=False` explicitly when the toggle
is off, not relying on the bare default).

**Depends on:** Sub-project 1 Task 1 (`JsonModel` base class must exist).

---

### Task 2 — `build_grading()` converter

**File:** `backend/models/grading.py` (same file as Task 1)

Implement `build_grading(before_score: dict | None, after_score: dict | None) -> Grading` exactly per
PRD.md §4's code sketch. Import `score_text`'s output shape from `backend/utils/scoring.py` — do not
modify `scoring.py` itself.

⚠️ Before writing this, confirm with the user (PRD.md §8) whether "before" scoring should be kept. If
they say drop it, this function takes only `after_score` and the `for target, score in (...)` loop
becomes a single pass — a small change, don't block on it, just confirm the answer first since it
changes the function signature.

**Acceptance criteria:** Given the existing `score_text()` output fixtures (check `backend/tests/` for
existing scoring tests to reuse as fixtures), `build_grading(before, after)` produces 16 entries (or 8
if "before" is dropped) with correct `name`/`target`/`grade` values matching the source dicts exactly.

**Depends on:** Task 1.

---

### Task 3 — Wire `grading_enabled` toggle + `build_grading()` into the v1-2 route

**File:** `backend/routes/simplify_v1_2.py`

1. Read `grading_enabled = (request.form.get("grading_enabled", "true").lower() != "false")` (or JSON
   equivalent for `doc_id` requests — match whatever pattern Sub-project 2 Task 1 used for reading
   `version`).
2. Where `before_score = _score_or_none(text, "before")` and `after_score = _score_or_none(clarified,
   "after")` currently run unconditionally, gate both behind `if grading_enabled:` — when disabled,
   leave both as `None` and skip the calls entirely (this is the actual compute saving from PRD.md
   §4, not just hiding the result).
3. Remove `before_score`/`after_score` from the dict passed into
   `SimplifiedCarePlan.from_pipeline_result(...)` (per PRD.md §4 — they no longer live on the care
   plan).
4. Build `grading = build_grading(before_score, after_score) if grading_enabled else Grading(enabled=False)`.
5. Pass `grading` into the `SimplifyOutput(...)` construction (replacing the Sub-project 1 stub
   `Grading()`).

**Acceptance criteria:** With `grading_enabled` omitted or `"true"`, response `grading.entries` has 16
entries (or 8, per Task 2's confirmed scope) and `simplified_care_plan` has no `before_score`/
`after_score` keys. With `grading_enabled="false"`, `grading == {"entries": [], "enabled": false,
"graded_at": null}` and the route runs measurably faster (no `score_text()` calls — can verify via
the existing per-step duration logging from Sub-project 1's `Metrics.step_durations_ms`, there should
be no scoring-related step entries when disabled).

**Depends on:** Tasks 1, 2; Sub-project 1 Tasks 5–7 (envelope must exist); Sub-project 2 Task 1 (for
the form-vs-JSON field reading pattern to copy).

---

### Task 4 — Apply the same wiring to v1 and v1-1 routes

**Files:** `backend/routes/simplify.py`, `backend/routes/simplify_v1_1.py`

Same change as Task 3, adapted to each route. v1 (`simplify.py`) currently computes `before_score`/
`after_score` the same way (lines ~144–149, ~199–204) — same gating logic applies.

**Acceptance criteria:** Same as Task 3, for each route.

**Depends on:** Task 3 (copy the pattern once it's proven there).

---

### Task 5 — New endpoint: `POST /simplify/grade`

**File:** `backend/routes/simplify.py` (add to the existing blueprint, or a new `routes/grading.py` —
implementer's call; if a new file, register its blueprint in `routes/__init__.py`)

Implement exactly per PRD.md §4 "Manual re-run":
```python
@simplify_bp.route("/simplify/grade", methods=["POST"])
@verify_firebase_token
def grade_output(user_id: str):
    body = request.get_json(silent=True) or {}
    saved_id = body.get("saved_id")
    if saved_id:
        db = _db()  # reuse the pattern from saved_outputs.py
        doc, err = _get_doc_or_403(db, saved_id, user_id)  # import/reuse from saved_outputs.py, don't duplicate
        if err:
            return err
        data = doc.to_dict()
        raw = data["output_data"]["simplified_care_plan"]["raw"]
        before = score_text(raw["text"])
        after = score_text(raw["clarified_text"])
        grading = build_grading(before, after)
        doc.reference.update({"output_data.grading": grading.to_dict(), "updated_at": ...})
        return jsonify({"grading": grading.to_dict()})
    text, clarified_text = body.get("text"), body.get("clarified_text")
    if not text or not clarified_text:
        return jsonify({"error": "Provide saved_id, or both text and clarified_text"}), 400
    grading = build_grading(score_text(text), score_text(clarified_text))
    return jsonify({"grading": grading.to_dict()})
```
(Move `_get_doc_or_403` to a shared location, e.g. `backend/utils/firestore_helpers.py`, if it's
currently private to `saved_outputs.py` — don't duplicate the ownership-check logic in two files.)

**Acceptance criteria:** Per PRD.md §7's three route tests for this endpoint.

**Depends on:** Tasks 1, 2.

---

### Task 6 — Frontend: grading toggle in `ConfigurationCard`

**File:** `frontend/src/components/ConfigurationCard.tsx` (from Sub-project 2 Task 4)

Add a `gradingEnabled: boolean` / `onGradingEnabledChange` prop pair and a checkbox, default checked,
above or below the version dropdown (implementer's call on layout). Wire the upload submit handler in
`SimplifyPage.tsx` to send `grading_enabled` alongside `version`.

**Acceptance criteria:** Submitting with the box unchecked sends `grading_enabled=false`; the response
has empty grading entries (verified via Task 3/4's backend behavior).

**Depends on:** Sub-project 2 Task 4 (the card must exist); Task 3/4 (backend must read the field).

---

### Task 7 — Frontend: `patientScoreFromGrading` selector + `ReadabilityCard` call-site update

**Files:** `frontend/src/utils/grading.ts` (new), `frontend/src/components/AppointmentNoteV12View.tsx`

1. In `grading.ts`:
   ```ts
   export function patientScoreFromGrading(grading: Grading, target: 'before' | 'after'): PatientScore | null {
     const entries = grading.entries.filter(e => e.target === target);
     if (entries.length === 0) return null;
     const combined = entries.find(e => e.name === 'combined');
     const dims = entries.filter(e => e.name !== 'combined');
     return {
       composite: combined?.grade ?? 0,
       grade_estimate: combined?.grade_breakdown?.grade_estimate ?? 0,
       label: combined?.grade_breakdown?.label ?? '',
       word_count: combined?.grade_breakdown?.word_count ?? 0,
       dimensions: Object.fromEntries(dims.map(d => [d.name, { score: d.grade, raw: d.grade_breakdown?.raw, label: d.grade_breakdown?.label, unit: d.grade_breakdown?.unit }])) as PatientScore['dimensions'],
     };
   }
   ```
2. At the call site (wherever `AppointmentNoteV12View` currently reads `result.before_score`/
   `result.after_score` to decide whether to render `ReadabilityCard` — find via
   `grep -n "before_score\|after_score" frontend/src/components/AppointmentNoteV12View.tsx`), replace
   with `patientScoreFromGrading(output.grading, 'before')` / `'after'`, and only render
   `ReadabilityCard` when both are non-null.

**Acceptance criteria:** Visual output of `ReadabilityCard` is pixel-identical to before this change
when grading is enabled; disappears entirely when grading is disabled. No changes needed inside
`ReadabilityCard` itself.

**Depends on:** Task 3 (response shape), Task 10's types (see below — actually depends on Sub-project
1 Task 10/11 having defined `Grading`/`SimplifyOutput` TS types; if those aren't done yet, define the
minimal `Grading`/`GradingEntry` TS interfaces inline here instead of blocking on it).

---

### Task 8 — Frontend: output-screen Configuration card with "Run Grading" button

**File:** new component, e.g. `frontend/src/components/OutputGradingCard.tsx`, rendered in the result
view below the report and above the existing sticky download bar (see the layout established by the
"move download buttons" change — find the relevant container in the result page/component).

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
(Match existing auth-header/fetch conventions used elsewhere in the page rather than inventing a new
pattern — check how the SSE submit request sends its auth header and mirror it.)

**Acceptance criteria:** Button is visible regardless of whether grading already ran. Clicking it
updates the displayed `ReadabilityCard` with fresh scores (manual check via `/run`).

**Depends on:** Task 5, Task 7.

---

### Task 9 — Tests

Cover PRD.md §7 in full: `build_grading()` unit test, three route tests for `/simplify/grade`, and the
`grading_enabled=false` route test for at least the v1-2 route.

**Depends on:** Tasks 1–5.

---

## Summary of what requires you (not a dev agent)

1. **Before Task 2:** confirm whether "before" (input-text) scoring should be kept alongside "after"
   (report) scoring, or dropped now that grading is an explicit, named, toggleable concept.
2. **Cosmetic, non-blocking:** review the output-screen Configuration card's copy/placement once Task
   8 has a first pass — not required before starting, just before calling it final.
