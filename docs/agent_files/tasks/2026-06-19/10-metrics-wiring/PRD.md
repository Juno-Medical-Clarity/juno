# PRD: Metrics Wiring (SP-10)

Sub-project 10 of the Juno Phase 4 initiative — a self-contained observability wiring change
with **no dependencies on SP-07 through SP-09** but must land after the SP-07 rename
(`simplify/ → care_plan/`, `V1_2Pipeline → CarePlanV1_2Pipeline`) since this PRD references
post-rename paths. The change is entirely in the backend; the frontend is untouched.

## 1. Problem

The Cloud Monitoring log-based metrics layer (Code Markers → JunoSink → Cloud Logging) has
gaps that make it impossible to answer routine operational questions:

1. **`Markers.Grading.Run` is defined but never called.** `utils/markers/markers.py:31` defines
   `grading.run` but there is zero call-site anywhere in the codebase. Grading duration, success
   rate, and quality improvement are invisible to Cloud Monitoring.

2. **`care_plan.pipeline` is missing three dimensions.** The pipeline-done marker
   (`routes/care_plan.py:465-468`) records only `input_chars`. It cannot answer: is this a batch
   or a single request? Was grading enabled? What was the input source kind?

3. **`care_plan.read_input` is missing two file-related dimensions.** The read-input marker
   (`routes/care_plan.py:502-507`) already records `source_kind` and `input_chars` but cannot
   answer: how many files were uploaded? What file types?

4. **`care_plan.find_medical_terms` emits nothing beyond JunoContext fields.** The term-detection
   marker adds no dimensions at all, so Cloud Monitoring cannot answer: how many medical terms
   were found? How many were candidates for substitution?

Together these gaps mean four dimensions defined in the initiative spec — `source_kind`,
`grading_enabled`, `is_batch`, `file_count`, `file_types`, `term_count`, `substitution_count`,
`before_composite`, `after_composite`, `grading_method_count` — are permanently invisible in
log-based metrics even though the data to compute them is already available at the call site.

## 2. Goals

1. **Wire `Markers.Grading.Run`** around `build_grading()` in `routes/care_plan.py` so grading
   duration, outcome, and quality-improvement scores appear in Cloud Monitoring as `grading.run`
   events.

2. **Add `source_kind`, `grading_enabled`, `is_batch`** to the `care_plan.pipeline` marker so
   every pipeline event is sliceable by input type, grading mode, and batch vs single request.

3. **Add `file_count`, `file_types`** to the `care_plan.read_input` marker for file-upload
   requests, with sensible zero/empty values for non-file modes.

4. **Add `term_count`, `substitution_count`** to the `care_plan.find_medical_terms` marker so
   term complexity is observable per request.

5. **Add `before_composite`, `after_composite`, `grading_method_count`** to the `grading.run`
   marker so readability improvement is captured on every graded run.

6. **Pass `is_batch: bool` and `source_kind: str` into `run_care_plan_pipeline`** cleanly so
   the pipeline marker can record them without depending on Flask `g` or breaking the function's
   existing call-site contract.

7. **Update test coverage** to assert all new dimensions are present in sink events.

## 3. Non-Goals

- No changes to `utils/markers/markers.py` — `Markers.Grading.Run` is already correctly
  defined there; this PRD only wires its call-site.
- No new Cloud Monitoring metrics, dashboards, or log-based metric filters — those are manual
  steps (§8). SP-10 only adds log fields; the operator creates Cloud Monitoring metric descriptors
  from those fields.
- No changes to `JunoContext.apply()` — the context helper already stamps
  `session_id`, `user_id`, `function`, `care_plan_version`, `grading_version`, `input_version`,
  `service`, `environment` on every scope automatically.
- No changes to the grading algorithm, scoring math, or `GradingEntry` shape.
- No frontend changes.
- No changes to the batch grading flow in `models/grading.py` logic — only marker wiring is added.
- `Markers.Grading.Run` is not placed inside `build_grading()` itself (see §4.3 for rationale).

## 4. Architecture Decisions

### 4.1 `routes/care_plan.py` — extend `run_care_plan_pipeline` signature

**Post-SP-07 path:** `routes/care_plan.py` (unchanged name; SP-07 renames the folder not the
route file).

Current signature:
```python
def run_care_plan_pipeline(
    text: str,
    metrics: Metrics,
    grading_enabled: bool,
) -> Generator[str | tuple, None, None]:
```

New signature (two additional keyword-only parameters, both with defaults so existing call-sites
that pass positionally are unaffected):

```python
def run_care_plan_pipeline(
    text: str,
    metrics: Metrics,
    grading_enabled: bool,
    source_kind: str = "upload",
    is_batch: bool = False,
) -> Generator[str | tuple, None, None]:
```

`source_kind` defaults to `"upload"` (the most common non-text, non-doc_id path) so callers that
do not pass it produce a safe dimension value. `is_batch` defaults to `False`.

**Why not read from `g`?** `source_kind` is already set on `resolved` (a local variable in
`_care_plan_stream`) before `run_care_plan_pipeline` is called. Reading it from `g` would require
adding a new `g` attribute just for one marker, which is worse coupling than an explicit parameter.
`is_batch` is a boolean that the batch route knows before calling the pipeline; it is not a property
of the Flask request context that is already populated.

**Callers that must be updated:**

| File | Current call | Updated call |
|---|---|---|
| `routes/care_plan.py` (`_care_plan_stream`) | `pipeline(text, metrics, grading_enabled=grading_enabled)` | `pipeline(text, metrics, grading_enabled=grading_enabled, source_kind=resolved.source_kind)` |
| `routes/batch.py` | `pipeline(text, metrics, grading_enabled)` | `pipeline(text, metrics, grading_enabled, is_batch=True)` |

`_care_plan_stream` has `resolved` in scope at the call-site so `resolved.source_kind` is
directly available; no new variable or `g` attribute is needed.

### 4.2 `routes/care_plan.py` — pipeline marker dimensions

**Current** (lines 465-468):
```python
def _pipeline_done(scope):
    JunoContext.from_g(function="pipeline").apply(scope)
    scope.add("input_chars", len(text))
Markers.CarePlan.Pipeline.execute(_pipeline_done)
```

**New:**
```python
def _pipeline_done(scope):
    JunoContext.from_g(function="pipeline").apply(scope)
    scope.add("input_chars", len(text))
    scope.add("source_kind", source_kind)
    scope.add("grading_enabled", grading_enabled)
    scope.add("is_batch", is_batch)
Markers.CarePlan.Pipeline.execute(_pipeline_done)
```

`source_kind`, `grading_enabled`, and `is_batch` are all in scope because they are parameters of
`run_care_plan_pipeline`. No data-flow changes needed; the closure captures them directly.

The failure-path marker (lines 475-478) does not add these dimensions because the scope may not
have completed the computation that proves their values are valid; the failure path only marks
`scope.mark_failed()` and applies JunoContext.

### 4.3 `routes/care_plan.py` — grading marker placement

**Decision: wrap in `routes/care_plan.py`, not inside `models/grading.py`.**

Rationale: `build_grading()` is a pure function that constructs a `Grading` model. It has no
knowledge of request context, pipeline flags, or composite scores. Wrapping it inside
`build_grading()` itself would require passing marker dimensions (`before_composite`,
`after_composite`) into the function as side-effect outputs, conflating model construction with
observability. The route already knows the values: `before_score["composite"]` and
`after_score["composite"]` are available as local variables immediately after
`build_grading()` returns (or can be read from the passed-in score dicts before the call).

**New code** (replaces the current `build_grading(...)` call in `run_care_plan_pipeline`):

```python
if grading_enabled:
    def _grade(scope):
        JunoContext.from_g(function="grading").apply(scope)
        result = build_grading(before_score, text, after_score, clarified)
        # Composite scores: read from the score dicts (already computed above);
        # 0.0 sentinel if a score is missing (should not occur when grading_enabled=True).
        scope.add("before_composite", (before_score or {}).get("composite", 0.0))
        scope.add("after_composite", (after_score or {}).get("composite", 0.0))
        # Count methods that produced entries for target="before" (one entry per method per target).
        # 7 entries per target: 6 named methods + "combined". method_count excludes "combined".
        method_names = {e.name for e in result.entries if e.name != "combined"}
        scope.add("grading_method_count", len(method_names))
        return result
    grading = Markers.Grading.Run.execute(_grade)
else:
    grading = Grading(enabled=False)
```

**Dimension derivation:**

| Dimension | Source |
|---|---|
| `before_composite` | `before_score["composite"]` (float, 0-100) |
| `after_composite` | `after_score["composite"]` (float, 0-100) |
| `grading_method_count` | `len({e.name for e in result.entries if e.name != "combined"})` — number of distinct named methods (excludes the combined aggregate); under normal conditions this is 6 |

`before_score` and `after_score` are computed just above the old `build_grading()` call; they
are guaranteed non-None when `grading_enabled=True` (each falls back to `None` via
`_score_or_none` only on exception, which is rare; the `.get("composite", 0.0)` sentinel covers
that case safely).

### 4.4 `routes/care_plan.py` — read_input marker dimensions

**Current** (lines 502-507):
```python
def _read(scope):
    JunoContext.from_g(function="read_input").apply(scope)
    resolved = _resolve_input()
    scope.add("source_kind", resolved.source_kind)
    scope.add("input_chars", len(resolved.text))
    return resolved
resolved = Markers.CarePlan.ReadInput.execute(_read)
```

**New:**
```python
def _read(scope):
    JunoContext.from_g(function="read_input").apply(scope)
    resolved = _resolve_input()
    scope.add("source_kind", resolved.source_kind)
    scope.add("input_chars", len(resolved.text))
    # File dimensions: meaningful only for upload source_kind.
    # file_count = 0 for text/doc_id; file_types = "" for non-file modes.
    if resolved.source_kind == "upload" and resolved.source_filename:
        filenames = [f.strip() for f in resolved.source_filename.split(",") if f.strip()]
        scope.add("file_count", len(filenames))
        extensions = ",".join(
            f.rsplit(".", 1)[1].lower() if "." in f else ""
            for f in filenames
        )
        scope.add("file_types", extensions)
    else:
        scope.add("file_count", 0)
        scope.add("file_types", "")
    return resolved
resolved = Markers.CarePlan.ReadInput.execute(_read)
```

**Why derive from `resolved.source_filename`?** `source_filename` for upload paths is set to
`", ".join(filenames)` by `_resolve_uploaded_files` (lines 181-185). It is already a
comma-joined list of the original upload filenames with extensions, so splitting on `", "` and
extracting extensions reconstructs the per-file type list without modifying `ResolvedInput`.

**Dimension values by source_kind:**

| source_kind | file_count | file_types |
|---|---|---|
| `"text"` | `0` | `""` |
| `"doc_id"` | `0` | `""` |
| `"upload"` (1 PDF) | `1` | `"pdf"` |
| `"upload"` (2 PDFs + 1 TXT) | `3` | `"pdf,pdf,txt"` |
| `"batch_dataset"` (batch route) | `0` | `""` (batch never hits this read_input marker) |

Note: the batch route in `routes/batch.py` does NOT call `_care_plan_stream`; it calls
`run_care_plan_pipeline` directly, so the read_input marker is never fired for batch runs. The
`file_count=0` and `file_types=""` sentinel values are only relevant for the single-request text
and doc_id modes.

### 4.5 `routes/care_plan.py` — find_medical_terms marker dimensions

**Current** (lines 356-368):
```python
def _find(scope):
    JunoContext.from_g(function="find_medical_terms").apply(scope)
    try:
        return detect_terms(text)
    except Exception as exc:
        logger.exception("care_plan: term detection failed - continuing with empty terms")
        scope.mark_failed()
        return {
            "substitution_candidates": [],
            "preserve_and_define_terms": [],
            "abbreviations": [],
        }
term_data = Markers.CarePlan.FindMedicalTerms.execute(_find)
```

**New:**
```python
def _find(scope):
    JunoContext.from_g(function="find_medical_terms").apply(scope)
    try:
        result = detect_terms(text)
    except Exception as exc:
        logger.exception("care_plan: term detection failed - continuing with empty terms")
        scope.mark_failed()
        result = {
            "substitution_candidates": [],
            "preserve_and_define_terms": [],
            "abbreviations": [],
        }
    # term_count = substitution_candidates + preserve_and_define_terms
    # (abbreviations are not medical-term findings in the metric sense)
    substitution_count = len(result.get("substitution_candidates", []))
    preserve_count = len(result.get("preserve_and_define_terms", []))
    scope.add("term_count", substitution_count + preserve_count)
    scope.add("substitution_count", substitution_count)
    return result
term_data = Markers.CarePlan.FindMedicalTerms.execute(_find)
```

**Dimension derivation:**

| Dimension | Formula |
|---|---|
| `term_count` | `len(substitution_candidates) + len(preserve_and_define_terms)` |
| `substitution_count` | `len(substitution_candidates)` |

`abbreviations` is excluded from `term_count` because it represents a distinct detection class
(not terms that require simplification or definition) and was intentionally excluded in the
initiative specification.

The refactor moves `return result` to a separate line so dimensions can be added after the
try/except without duplicating the scope calls in each branch.

### 4.6 `routes/batch.py` — pass `is_batch=True`

**Current** (line 199):
```python
for chunk in pipeline(text, metrics, grading_enabled):
```

**New:**
```python
for chunk in pipeline(text, metrics, grading_enabled, is_batch=True, source_kind="batch_dataset"):
```

No other changes to `routes/batch.py`. The batch route constructs its own `Metrics` and
`input_model` directly; it does not go through `_care_plan_stream` or the `read_input` marker.

### 4.7 `utils/markers/markers.py` — no changes

`Markers.Grading.Run` at line 31 is already defined with name `"grading.run"`. Zero edits
required in this file. The file is read-only for SP-10.

### 4.8 Summary: new dimensions per marker

| Marker | Existing dims (beyond JunoContext) | New dims added by SP-10 |
|---|---|---|
| `care_plan.pipeline` | `input_chars` | `source_kind`, `grading_enabled`, `is_batch` |
| `care_plan.read_input` | `source_kind`, `input_chars` | `file_count`, `file_types` |
| `care_plan.find_medical_terms` | (none) | `term_count`, `substitution_count` |
| `grading.run` | (marker never fired — now wired) | `before_composite`, `after_composite`, `grading_method_count` |

### 4.9 Files touched

| File (post-SP-07 path) | Change |
|---|---|
| `backend/routes/care_plan.py` | Extend `run_care_plan_pipeline` signature; update 4 marker closures; wire `Markers.Grading.Run` |
| `backend/routes/batch.py` | Pass `is_batch=True` to `run_care_plan_pipeline` |
| `backend/tests/utils/test_care_plan_markers.py` | Add dimension assertions (see §7) |

No other files change.

## 5. API Change Summary

N/A — SP-10 adds log fields only. No HTTP request or response shape changes.

## 6. Frontend Change Summary

N/A — SP-10 is entirely backend observability. No frontend files change.

## 7. Testing

All new tests go in `backend/tests/utils/test_care_plan_markers.py` alongside the existing
source-level assertions. Use `InMemorySink` from `utils.markers` to capture events without Flask.

### 7.1 Pipeline marker dimensions

```python
def test_pipeline_marker_has_source_kind_grading_enabled_is_batch():
    """run_care_plan_pipeline fires care_plan.pipeline with new dimensions."""
    # Arrange: patch V1_2Pipeline, detect_terms, build_glossary, score_text, build_grading
    # to return minimal stubs. Register InMemorySink.
    sink = InMemorySink()
    register_sink(sink)
    # Act: call run_care_plan_pipeline(text, metrics, grading_enabled=True,
    #                                   source_kind="upload", is_batch=False)
    # and exhaust the generator.
    # Assert:
    pipeline_events = [e for e in sink.events if e["name"] == "care_plan.pipeline"]
    assert len(pipeline_events) == 1
    dims = pipeline_events[0]["dimensions"]
    assert dims["source_kind"] == "upload"
    assert dims["grading_enabled"] is True
    assert dims["is_batch"] is False
```

Repeat with `is_batch=True` and `source_kind="text"` to verify the dimensions track the passed
values, not hardcoded literals.

### 7.2 Read-input marker dimensions (file upload)

```python
def test_read_input_marker_file_upload_dimensions():
    """read_input marker records file_count and file_types for upload source_kind."""
    # Arrange: mock _resolve_input() to return a ResolvedInput with
    #   source_kind="upload", source_filename="report.pdf, labs.txt"
    # Assert on the InMemorySink event for "care_plan.read_input":
    dims = ...
    assert dims["file_count"] == 2
    assert dims["file_types"] == "pdf,txt"
```

```python
def test_read_input_marker_text_mode_zero_file_dims():
    """read_input marker records file_count=0 and file_types='' for text source."""
    # source_kind="text" → file_count=0, file_types=""
    dims = ...
    assert dims["file_count"] == 0
    assert dims["file_types"] == ""
```

### 7.3 Find-medical-terms marker dimensions

```python
def test_find_medical_terms_marker_term_dims():
    """find_medical_terms marker records term_count and substitution_count."""
    # Arrange: mock detect_terms() to return:
    #   {"substitution_candidates": ["hypertension", "myocardial"],
    #    "preserve_and_define_terms": ["ECG"],
    #    "abbreviations": ["BP"]}
    # Assert:
    dims = ...
    assert dims["term_count"] == 3      # 2 substitution + 1 preserve
    assert dims["substitution_count"] == 2
```

```python
def test_find_medical_terms_marker_empty_on_failure():
    """find_medical_terms marker records zeros when detect_terms raises."""
    # Arrange: mock detect_terms() to raise RuntimeError.
    # Assert: marker fires (success=False) and dims have term_count=0, substitution_count=0.
    dims = ...
    assert dims["term_count"] == 0
    assert dims["substitution_count"] == 0
```

### 7.4 Grading.Run marker dimensions

```python
def test_grading_run_marker_fired_when_grading_enabled():
    """Markers.Grading.Run fires with before/after composite and method count."""
    # Arrange: mock build_grading() to return a Grading with 14 entries
    #   (6 named + "combined") × 2 targets; mock before_score/after_score
    #   to have composite=72.5 and composite=85.0 respectively.
    # Assert:
    grading_events = [e for e in sink.events if e["name"] == "grading.run"]
    assert len(grading_events) == 1
    dims = grading_events[0]["dimensions"]
    assert dims["before_composite"] == 72.5
    assert dims["after_composite"] == 85.0
    assert dims["grading_method_count"] == 6
```

```python
def test_grading_run_marker_not_fired_when_grading_disabled():
    """Markers.Grading.Run must not fire when grading_enabled=False."""
    # Arrange: run pipeline with grading_enabled=False.
    grading_events = [e for e in sink.events if e["name"] == "grading.run"]
    assert len(grading_events) == 0
```

### 7.5 Source-level assertions (extend existing file)

Extend `test_care_plan_markers.py` with three new grep-style source-level checks:

```python
def test_grading_run_marker_called():
    assert "Markers.Grading.Run" in _SOURCE, \
        "Markers.Grading.Run must be called in care_plan.py"

def test_is_batch_param_present():
    assert "is_batch" in _SOURCE, \
        "is_batch parameter must appear in care_plan.py"

def test_source_kind_param_in_pipeline():
    assert "source_kind" in _SOURCE, \
        "source_kind must be added to run_care_plan_pipeline"
```

### 7.6 Batch route test

```python
def test_batch_passes_is_batch_true(monkeypatch):
    """routes/batch.py must call run_care_plan_pipeline with is_batch=True."""
    calls = []
    def fake_pipeline(text, metrics, grading_enabled, is_batch=False):
        calls.append({"is_batch": is_batch})
        return iter([])

    # monkeypatch run_care_plan_pipeline in routes.batch
    # call create_care_plan_batch with a minimal valid request
    assert calls[0]["is_batch"] is True
```

## 8. Manual Intervention Required From You

After SP-10 lands, the new log fields (`source_kind`, `grading_enabled`, `is_batch`, `file_count`,
`file_types`, `term_count`, `substitution_count`, `before_composite`, `after_composite`,
`grading_method_count`) appear automatically in Cloud Logging via the existing JunoSink emission
path. However, **Cloud Monitoring log-based metrics are not automatically created** — they must
be defined manually in the Cloud Monitoring console:

1. **Create or update the `juno_marker_duration_ms` log-based metric** to add the new dimension
   labels: `source_kind`, `grading_enabled`, `is_batch` (from `care_plan.pipeline` events) and
   `file_count` (from `care_plan.read_input` events). Label extraction uses
   `jsonPayload.source_kind`, `jsonPayload.grading_enabled`, etc.

2. **Create a new `grading_run_composite_improvement` log-based metric** (or a custom dashboard
   chart) using the `grading.run` events' `before_composite` and `after_composite` fields to
   visualize readability improvement per request.

3. **Optional:** add `term_count` and `substitution_count` labels to the
   `care_plan.find_medical_terms` filter if per-session term complexity tracking is desired.

No code changes are required for the above; they are Cloud Console configuration steps.

## 9. Open Questions & Decisions

1. **Where to fire `Markers.Grading.Run` — route vs. `build_grading()` internals.**
   `[RESOLVED: Fire in routes/care_plan.py, wrapping the build_grading() call. build_grading()
   stays a pure model-construction function. The marker closure captures before_score and
   after_score from the enclosing route scope and reads composite values after the call returns.
   See §4.3.]`

2. **How to pass `source_kind` into `run_care_plan_pipeline` without `g`.**
   `[RESOLVED: Add source_kind: str = "upload" as a keyword parameter to
   run_care_plan_pipeline. The _care_plan_stream caller already has resolved.source_kind in scope
   and passes it explicitly. The batch route does not call _care_plan_stream, so it does not
   need to supply source_kind; the default "upload" is not accurate for batch, but source_kind on
   the pipeline marker is less important for batch runs than is_batch=True. See §4.1 and §4.4,
   note on batch_dataset. See Open Q3 for a possible improvement.]`

3. **Should batch runs set `source_kind="batch_dataset"` on the pipeline marker?**
   `[RESOLVED: (a) — also pass source_kind="batch_dataset" from routes/batch.py at the run_care_plan_pipeline call-site (§4.6). This is a one-line addition alongside is_batch=True and produces accurate dimensions in Cloud Monitoring queries.]`

4. **`file_count` and `file_types` for the `doc_id` case — single file but `source_kind="doc_id"`.**
   `[RESOLVED: doc_id resolves to a single file fetched from GCS but we classify it as
   source_kind="doc_id", not "upload". Per §4.4, file_count=0 and file_types="" for doc_id mode.
   The rationale: doc_id is a re-retrieval of a previously uploaded file, not a new upload event.
   Counting it as a file upload would conflate the two distinct input modes in dashboard queries.
   If a future requirement wants to count doc_id file types, add a file_count=1 branch for
   source_kind="doc_id"; that is a one-line change.]`

5. **`grading_method_count` formula — should it count unique method names or total entries?**
   `[RESOLVED: Count distinct method names excluding "combined", i.e.
   len({e.name for e in result.entries if e.name != "combined"}). Under normal operation this is
   always 6 (smog, flesch_kincaid, dale_chall, pemat, sam, cdc_cci). Counting total entries
   would double-count because build_grading produces one entry per method per target ("before"
   and "after"). The dimension is most useful as a flag for partial grading (e.g., some methods
   failing), so method-name cardinality is the correct unit. See §4.3.]`

6. **`before_composite` and `after_composite` when a score is None (exception path).**
   `[RESOLVED: Use .get("composite", 0.0) sentinel. When grading_enabled=True but _score_or_none
   returns None for one target (a rare exception path), composite defaults to 0.0. This is
   preferable to omitting the dimension entirely, which would make the event unqueryable in
   Cloud Monitoring. 0.0 is clearly distinguishable from any real composite score in monitoring
   queries. See §4.3.]`

7. **Should the failure-path pipeline marker also emit `source_kind`, `grading_enabled`, `is_batch`?**
   `[DEFERRED: The failure-path marker fires when an unexpected exception is raised before the
   pipeline completes. At that point source_kind, grading_enabled, and is_batch are all in scope
   (they are parameters). Adding them to the failure marker would make failure events filterable
   by the same dimensions as success events. However, the failure path is exceptional and low
   volume, so the benefit is minor. A future developer may add them with a one-line scope.add
   per dimension; this PRD does not require it.]`
