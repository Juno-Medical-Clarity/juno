# Tasks: Metrics Wiring (SP-10)

Read `PRD.md` in this folder first. **This sub-project lands after SP-07** (the `simplify/ →
care_plan/` rename) because it references post-rename module paths. All changes are backend-only;
no frontend files are touched.

**Files changed across all tasks:**
- `backend/routes/care_plan.py` — Tasks 1, 2, 3, 4
- `backend/routes/batch.py` — Task 5
- `backend/tests/utils/test_care_plan_markers.py` — Task 6

---

### Task 1 — Extend `run_care_plan_pipeline` signature with `source_kind` and `is_batch`

**Files:** `backend/routes/care_plan.py`

**Current signature** (line 345):
```python
def run_care_plan_pipeline(text: str, metrics: Metrics, grading_enabled: bool) -> Generator[str | tuple, None, None]:
```

**New signature:**
```python
def run_care_plan_pipeline(
    text: str,
    metrics: Metrics,
    grading_enabled: bool,
    source_kind: str = "upload",
    is_batch: bool = False,
) -> Generator[str | tuple, None, None]:
```

No other changes in this task — just the function signature. Both new parameters have defaults so
the existing `_care_plan_stream` call-site at line 533
(`pipeline(text, metrics, grading_enabled=grading_enabled)`) continues to work without change
until Task 2.

**Acceptance criteria:**
- `run_care_plan_pipeline` accepts `source_kind` and `is_batch` as keyword arguments with their
  defaults (`"upload"` and `False`).
- `python -m pytest tests/ -q` still passes (no call-site is broken by this signature extension).

---

### Task 2 — Update `_care_plan_stream` call-site to pass `source_kind`

**Files:** `backend/routes/care_plan.py`

In `_care_plan_stream` (around line 533), `resolved` is already in scope with a `source_kind`
attribute set by `Markers.CarePlan.ReadInput.execute(_read)`. Update the pipeline call to forward it:

**Current** (line 533):
```python
for chunk in pipeline(text, metrics, grading_enabled=grading_enabled):
```

**New:**
```python
for chunk in pipeline(text, metrics, grading_enabled=grading_enabled, source_kind=resolved.source_kind):
```

No other changes in this task.

**Acceptance criteria:**
- `resolved.source_kind` is the only new expression added at this call-site.
- `python -m pytest tests/ -q` passes.
- Running the app and submitting a text input: the `care_plan.pipeline` Cloud Logging event
  contains a `source_kind` field matching the input mode (e.g. `"text"`).

---

### Task 3 — Add `source_kind`, `grading_enabled`, `is_batch` to the pipeline marker

**Files:** `backend/routes/care_plan.py`

Extend `_pipeline_done` (currently lines 465-468) to emit three new dimensions:

**Current:**
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

`source_kind`, `grading_enabled`, and `is_batch` are all parameters of `run_care_plan_pipeline`
(added in Task 1), so they are in scope inside this closure with no additional wiring.

Do NOT add these dimensions to the failure-path marker `_pipeline_fail` (per PRD §4.2 — the
failure path only marks `scope.mark_failed()` and applies JunoContext).

**Acceptance criteria:**
- Three new `scope.add(...)` lines appear in `_pipeline_done` only.
- `_pipeline_fail` is unchanged.
- `python -m pytest tests/ -q` passes.

---

### Task 4 — Wire `Markers.Grading.Run` and add composite/method-count dimensions

**Files:** `backend/routes/care_plan.py`

Replace the bare `build_grading(...)` call (currently lines 459-462) with a
`Markers.Grading.Run.execute(...)` wrapper that captures composite scores and method count.

**Current** (lines 459-462):
```python
if grading_enabled:
    grading = build_grading(before_score, text, after_score, clarified)
else:
    grading = Grading(enabled=False)
```

**New:**
```python
if grading_enabled:
    def _grade(scope):
        JunoContext.from_g(function="grading").apply(scope)
        result = build_grading(before_score, text, after_score, clarified)
        scope.add("before_composite", (before_score or {}).get("composite", 0.0))
        scope.add("after_composite", (after_score or {}).get("composite", 0.0))
        method_names = {e.name for e in result.entries if e.name != "combined"}
        scope.add("grading_method_count", len(method_names))
        return result
    grading = Markers.Grading.Run.execute(_grade)
else:
    grading = Grading(enabled=False)
```

**Dimension derivation (per PRD §4.3):**
- `before_composite` — `before_score["composite"]` (float 0-100); sentinel `0.0` if score is None
  (rare exception path covered by `.get("composite", 0.0)`).
- `after_composite` — same from `after_score`.
- `grading_method_count` — count of distinct method names in `result.entries` excluding `"combined"`;
  under normal operation this is always `6`.

`before_score` and `after_score` are computed just above (lines 443-447) and are guaranteed non-None
when `grading_enabled=True` except on a rare `_score_or_none` exception path.

No changes to `build_grading()`, `models/grading.py`, or `Markers.Grading.Run` in
`utils/markers/markers.py` — that marker is already defined at line 31-32.

**Acceptance criteria:**
- `Markers.Grading.Run.execute(...)` appears in `care_plan.py`; the old bare `build_grading(...)`
  call inside the `if grading_enabled:` block is gone.
- `Grading(enabled=False)` path for `grading_enabled=False` is unchanged.
- `python -m pytest tests/ -q` passes.

---

### Task 5 — Add `file_count` and `file_types` to the `read_input` marker

**Files:** `backend/routes/care_plan.py`

Extend `_read` in `_care_plan_stream` (currently lines 502-507) to record file dimensions for
upload requests:

**Current:**
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

`resolved.source_filename` for upload paths is a comma-joined string of original upload filenames
(set by `_resolve_uploaded_files`); splitting on `","` and extracting extensions reconstructs the
per-file type list without modifying `ResolvedInput`.

**Dimension values by source_kind (per PRD §4.4):**

| source_kind | file_count | file_types |
|---|---|---|
| `"text"` | `0` | `""` |
| `"doc_id"` | `0` | `""` |
| `"upload"` (1 PDF) | `1` | `"pdf"` |
| `"upload"` (2 PDFs + 1 TXT) | `3` | `"pdf,pdf,txt"` |

The batch route calls `run_care_plan_pipeline` directly and never hits this `_read` closure.

**Acceptance criteria:**
- Two new `scope.add(...)` calls (`file_count`, `file_types`) appear inside `_read`.
- For `source_kind != "upload"` both dimensions always emit `0` / `""` (no `KeyError` / missing key).
- `python -m pytest tests/ -q` passes.

---

### Task 6 — Update `batch.py` to pass `is_batch=True` and `source_kind="batch_dataset"`

**Files:** `backend/routes/batch.py`

**Current** (line 199):
```python
for chunk in pipeline(text, metrics, grading_enabled):
```

**New:**
```python
for chunk in pipeline(text, metrics, grading_enabled, is_batch=True, source_kind="batch_dataset"):
```

This is the only change in `batch.py`. No other lines in this file are touched.

**Acceptance criteria:**
- `grep "is_batch=True" backend/routes/batch.py` matches exactly one line.
- `grep 'source_kind="batch_dataset"' backend/routes/batch.py` matches exactly one line.
- `python -m pytest tests/ -q` passes.

---

### Task 7 — Add `find_medical_terms` marker dimensions (`term_count`, `substitution_count`)

**Files:** `backend/routes/care_plan.py`

Refactor `_find` in `run_care_plan_pipeline` (currently lines 356-368) to record term dimensions.
The key change is moving `return result` outside the `try/except` so dimensions can be added once
without duplicating `scope.add(...)` calls in each branch:

**Current:**
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

On the exception path (`detect_terms` raises), `result` is set to the empty-list dict, so
`term_count` and `substitution_count` will both be `0` — correct sentinel values for a failed
detection (per PRD §4.5).

**Acceptance criteria:**
- `return result` is a single statement outside the `try/except` block.
- Both `scope.add("term_count", ...)` and `scope.add("substitution_count", ...)` appear once.
- When `detect_terms` raises, `scope.mark_failed()` is still called AND both dims emit `0`.
- `python -m pytest tests/ -q` passes.

---

### Task 8 — Extend `test_care_plan_markers.py` with dimension assertions

**Files:** `backend/tests/utils/test_care_plan_markers.py`

Extend the existing file with the following new tests. The file currently has source-level
assertion functions (`test_no_juno_metrics_in_care_plan`, `test_markers_used`, etc.). Keep all
existing tests; append the new ones below them.

#### 8a — New source-level assertions (append after existing `test_markers_used`)

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

#### 8b — Pipeline marker dimensions (InMemorySink)

These tests use `InMemorySink` from `utils.markers` (see `test_code_markers.py` in the same
folder for the import pattern). Each test must patch `V1_2Pipeline`, `detect_terms`,
`build_glossary_from_simplified_text`, `score_text` (or `_score_or_none`), and `build_grading`
to return minimal stubs, then register `InMemorySink` and exhaust the generator.

```python
def test_pipeline_marker_has_source_kind_grading_enabled_is_batch():
    """run_care_plan_pipeline fires care_plan.pipeline with new dimensions."""
    # Arrange + Act: call run_care_plan_pipeline(text, metrics, grading_enabled=True,
    #                source_kind="upload", is_batch=False) and exhaust the generator.
    # Assert:
    pipeline_events = [e for e in sink.events if e["name"] == "care_plan.pipeline"]
    assert len(pipeline_events) == 1
    dims = pipeline_events[0]["dimensions"]
    assert dims["source_kind"] == "upload"
    assert dims["grading_enabled"] is True
    assert dims["is_batch"] is False

def test_pipeline_marker_batch_dimensions():
    """Dimensions track passed values — not hardcoded literals."""
    # Same setup with is_batch=True, source_kind="batch_dataset".
    dims = pipeline_events[0]["dimensions"]
    assert dims["source_kind"] == "batch_dataset"
    assert dims["is_batch"] is True
```

#### 8c — Read-input marker dimensions

```python
def test_read_input_marker_file_upload_dimensions():
    """read_input marker records file_count and file_types for upload source_kind."""
    # Arrange: mock _resolve_input() to return a ResolvedInput with
    #   source_kind="upload", source_filename="report.pdf, labs.txt"
    dims = ...  # InMemorySink event for "care_plan.read_input"
    assert dims["file_count"] == 2
    assert dims["file_types"] == "pdf,txt"

def test_read_input_marker_text_mode_zero_file_dims():
    """read_input marker records file_count=0 and file_types='' for text source."""
    # source_kind="text" → file_count=0, file_types=""
    assert dims["file_count"] == 0
    assert dims["file_types"] == ""
```

#### 8d — Find-medical-terms marker dimensions

```python
def test_find_medical_terms_marker_term_dims():
    """find_medical_terms marker records term_count and substitution_count."""
    # Arrange: mock detect_terms() to return:
    #   {"substitution_candidates": ["hypertension", "myocardial"],
    #    "preserve_and_define_terms": ["ECG"],
    #    "abbreviations": ["BP"]}
    assert dims["term_count"] == 3        # 2 substitution + 1 preserve
    assert dims["substitution_count"] == 2

def test_find_medical_terms_marker_empty_on_failure():
    """find_medical_terms marker records zeros when detect_terms raises."""
    # Arrange: mock detect_terms() to raise RuntimeError.
    # Assert: marker fires (success=False) and dims have term_count=0, substitution_count=0.
    assert dims["term_count"] == 0
    assert dims["substitution_count"] == 0
```

#### 8e — Grading.Run marker dimensions

```python
def test_grading_run_marker_fired_when_grading_enabled():
    """Markers.Grading.Run fires with before/after composite and method count."""
    # Arrange: mock build_grading() to return a Grading with 14 entries
    #   (6 named + "combined") × 2 targets; mock before_score["composite"]=72.5,
    #   after_score["composite"]=85.0.
    grading_events = [e for e in sink.events if e["name"] == "grading.run"]
    assert len(grading_events) == 1
    dims = grading_events[0]["dimensions"]
    assert dims["before_composite"] == 72.5
    assert dims["after_composite"] == 85.0
    assert dims["grading_method_count"] == 6

def test_grading_run_marker_not_fired_when_grading_disabled():
    """Markers.Grading.Run must not fire when grading_enabled=False."""
    grading_events = [e for e in sink.events if e["name"] == "grading.run"]
    assert len(grading_events) == 0
```

#### 8f — Batch route test (add to existing `tests/routes/test_batch_route.py`, or here)

```python
def test_batch_passes_is_batch_true_and_source_kind(monkeypatch):
    """routes/batch.py calls run_care_plan_pipeline with is_batch=True and
    source_kind='batch_dataset'."""
    calls = []
    def fake_pipeline(text, metrics, grading_enabled, is_batch=False, source_kind="upload"):
        calls.append({"is_batch": is_batch, "source_kind": source_kind})
        return iter([])
    # monkeypatch run_care_plan_pipeline in routes.batch, then call
    # create_care_plan_batch with a minimal valid request.
    assert calls[0]["is_batch"] is True
    assert calls[0]["source_kind"] == "batch_dataset"
```

**Acceptance criteria:**
- All new test functions are collected by pytest (`python -m pytest tests/utils/test_care_plan_markers.py -v`
  shows them).
- Three new source-level assertions pass immediately after Tasks 1-7 are done.
- InMemorySink tests pass (mock all external I/O — no real LLM, no Flask, no Firestore).
- `test_grading_run_marker_not_fired_when_grading_disabled` confirms zero `grading.run` events.

---

## Summary of what requires you (not a dev agent)

1. **Cloud Monitoring metric descriptors** — after SP-10 lands, the new log fields appear
   automatically in Cloud Logging via `JunoSink`. You must manually create or update log-based
   metrics in the Cloud Monitoring console (§8 of the PRD):
   - Update `juno_marker_duration_ms` to add label extractors for `source_kind`, `grading_enabled`,
     `is_batch` (from `care_plan.pipeline` events) and `file_count` (from `care_plan.read_input`).
   - Create a new `grading_run_composite_improvement` log-based metric (or dashboard chart) using
     `before_composite` and `after_composite` from `grading.run` events.
   - Optionally add `term_count` / `substitution_count` labels to the
     `care_plan.find_medical_terms` metric filter.
   No code changes are needed; these are Cloud Console configuration steps.

2. **Verify SP-07 has landed** before this sub-project is implemented — SP-10 references
   post-rename paths (`routes/care_plan.py`). If SP-07 is not yet merged, the dev agent should
   be briefed on the correct current paths.
