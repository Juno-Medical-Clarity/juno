# Tasks: SP6 — Trial Pipeline Optimizations

Source PRD: `.dev/trial-simplify/06-trial-optimizations/PRD.md`. All decisions below
trace to PRD §4 (Architecture Decisions); §9 is `None — all settled` — no open
questions block this work. Tasks are ordered per the PRD's explicit dependency (Task 2
must land before Task 3 so Task 3's effect is measurable); each task is independently
committable, and the full suite (`cd /root/projects/juno/backend && python3 -m pytest
tests/ -q`) should stay green after every task.

**Cross-cutting note:** none of these three tasks touch `frontend/`, `frontend-trial/`,
`.github/workflows/`, `firebase.json`, or any deploy-time config — see PRD §5/§6. Do not
add any file outside `backend/` for any task in this file.

---

### Task 1 — Trim trial grading entries to `combined`-only in `backend/routes/worker.py`

   - Files: `backend/routes/worker.py`, `backend/tests/routes/test_worker.py`
   - Changes: Per PRD §4.1. In `execute_job`'s existing `is_trial` post-processing block
     (currently lines 218–227, right after `output_data["metrics"]["saved_id"] = job_id`
     and before `complete_job(job_id, output_data, name)`):
     ```python
     # current
     if getattr(job, "is_trial", False):
         output_data.get("care_plan", {}).pop("raw", None)
         output_data.get("input", {}).pop("text", None)

     complete_job(job_id, output_data, name)
     ```
     becomes:
     ```python
     # new
     if getattr(job, "is_trial", False):
         output_data.get("care_plan", {}).pop("raw", None)
         output_data.get("input", {}).pop("text", None)

         # Trial UI (ResultScreen.tsx) reads only the two `combined` grading
         # entries (before/after); the other 12 non-`combined` method entries
         # are computed (grading is shared with the main app's per-method
         # breakdown UI) but never rendered anywhere in frontend-trial/.
         # Dropping them here, storage-side only, cuts ~38% off output_data
         # (optimization-findings-2026-09-05.md, Finding 1 / PRD §4.1).
         grading = output_data.get("grading")
         if isinstance(grading, dict):
             entries = grading.get("entries")
             if isinstance(entries, list):
                 grading["entries"] = [
                     e for e in entries
                     if isinstance(e, dict) and e.get("name") == "combined"
                 ]

     complete_job(job_id, output_data, name)
     ```
     Do **not** touch `models/grading.py` or `services/care_plan_pipeline.py` — this is
     a storage-side filter only, exactly per PRD §4.1's "post-processing filter, not a
     threaded flag" decision. Do not change how `grading` gets into `output_data` in the
     first place (that's still `envelope.to_dict()`, unchanged).
   - Test changes (all in `backend/tests/routes/test_worker.py`):
     1. **Update the existing test `test_trial_job_grading_survives_input_and_raw_stripping`**
        (currently around line 627, in the "Trial jobs also drop the full document copy
        at `input.text`" section). It currently asserts
        `saved_output_data["grading"] == _REAL_GRADING_DICT` — this becomes false by
        design once trimming lands (only 2 of `_REAL_GRADING_DICT`'s 14 entries survive).
        Rename it `test_trial_job_grading_trimmed_to_combined_after_input_and_raw_stripping`
        and replace its final assertions:
        ```python
        # remove:
        # assert saved_output_data["grading"] == _REAL_GRADING_DICT

        entries = saved_output_data["grading"]["entries"]
        assert len(entries) == 2
        assert {e["name"] for e in entries} == {"combined"}
        assert {e["target"] for e in entries} == {"before", "after"}

        # Values, not just shape, must be unaffected by trimming: each surviving
        # entry's grade must match what the untrimmed pipeline output originally
        # computed for that (name, target) pair.
        original_combined = {
            (e["name"], e["target"]): e["grade"]
            for e in _REAL_GRADING_DICT["entries"] if e["name"] == "combined"
        }
        for e in entries:
            assert e["grade"] == original_combined[(e["name"], e["target"])]
        ```
        (Keep the rest of the test — fixture setup, `mock_complete.assert_called_once()`,
        etc. — unchanged; only the tail assertions change.)
     2. Add a new test that a **non-trial** job's `output_data["grading"]` is completely
        untouched (all 14 entries survive, byte-identical to what the pipeline produced):
        ```python
        @patch("utils.firebase.firestore.client")
        @patch("routes.worker.complete_job")
        @patch("routes.worker.update_job_stage")
        @patch("routes.worker.fail_job")
        @patch("routes.worker.get_job_doc")
        def test_non_trial_job_completed_output_grading_is_byte_identical(
            mock_get_doc, mock_fail, mock_update_stage, mock_complete, mock_fs_client,
            client_worker,
        ):
            """Non-trial jobs must be provably unaffected by the trial-only grading
            trim: output_data (including the full, untrimmed grading dict) passed to
            complete_job must be identical to what envelope.to_dict() returned."""
            mock_get_doc.return_value = _make_job_doc()  # is_trial defaults False

            care_plan_mock = MagicMock()
            care_plan_mock.to_dict.return_value = {"reason_for_visit": [{"reason": "Hypertension"}]}
            grading_mock = MagicMock()

            def fake_pipeline(text, metrics, grading_enabled, source_kind="text", is_batch=False):
                yield AdapterResult(care_plan=care_plan_mock, grading=grading_mock, raw_text=text, clarified_text="c")

            raw_envelope_dict = {
                "care_plan": {"reason_for_visit": [{"reason": "Hypertension"}]},
                "grading": _REAL_GRADING_DICT,
                "metrics": {"saved_id": None},
            }
            envelope_mock = MagicMock()
            envelope_mock.to_dict.return_value = dict(raw_envelope_dict)

            with patch.dict("routes.worker.PIPELINES", {"v1-2": lambda *a, **kw: fake_pipeline(*a, **kw)}):
                with patch("routes.worker.CarePlanInternal", return_value=envelope_mock):
                    resp = client_worker.post(
                        "/internal/jobs/execute/job-1", headers=QUEUE_HEADER, content_type="application/json",
                    )

            assert resp.status_code == 200
            mock_complete.assert_called_once()
            saved_output_data = mock_complete.call_args.args[1]
            assert saved_output_data["grading"] == _REAL_GRADING_DICT
            assert len(saved_output_data["grading"]["entries"]) == 14
        ```
     3. Add defensive-path tests, each asserting the job still completes successfully
        (`resp.status_code == 200`, `mock_complete.assert_called_once()`) with no
        exception raised, for a **trial** job whose `envelope.to_dict()` returns each of
        these malformed shapes in turn: no `"grading"` key at all; `"grading": None`;
        `"grading": {}` (dict present, no `"entries"` key); `"grading": {"entries": None}`;
        and `"grading": {"entries": [{"name": "combined", "target": "before", "grade": 1}, "not-a-dict", {"name": "smog", "target": "before", "grade": 2}]}`
        (mixed valid/invalid entries — the non-dict entry must simply be dropped, not
        raise, and the one valid non-`combined` entry among them must still be filtered
        out).
   - Acceptance criteria:
     - `cd /root/projects/juno/backend && python3 -m pytest tests/routes/test_worker.py -q`
       passes, including all new/updated tests above.
     - A trial job's completed `output_data["grading"]["entries"]` contains exactly 2
       entries, both `name == "combined"`, one per `target`.
     - **Non-trial jobs' `output_data` is byte-identical to before this task** — i.e.
       `output_data` passed to `complete_job` for a non-trial job equals exactly what
       `envelope.to_dict()` returned, unmodified in any key including `grading`. This is
       asserted directly by the new `test_non_trial_job_completed_output_grading_is_byte_identical`
       test above.
     - No malformed/missing `grading`/`entries` shape raises an exception (5 defensive
       cases above, all returning `200`).
     - `git diff --stat main -- backend/models/grading.py backend/services/care_plan_pipeline.py`
       shows no changes (confirms the "post-processing filter only" scope boundary).

---

### Task 2 — Populate `Metrics.total_duration_ms` in `backend/routes/worker.py`

   - Files: `backend/routes/worker.py`, `backend/tests/routes/test_worker.py`
   - Changes: Per PRD §4.2. `worker.py:88` already computes `start = time.monotonic()`
     for the existing per-stage timeout check — this task only reads that same timer
     back out once, right before the envelope is built. Currently (around line 193-201):
     ```python
     care_plan = pipeline_result.care_plan
     grading   = pipeline_result.grading

     if source_kind == "doc_id":
         input_model = DocIdInput(doc_id=job.input_doc_id)
     else:
         input_model = TextInput(text=text)

     envelope = CarePlanInternal(
         metrics=metrics,
         input=input_model,
         grading=grading,
         care_plan=care_plan,
     )
     ```
     becomes:
     ```python
     care_plan = pipeline_result.care_plan
     grading   = pipeline_result.grading

     if source_kind == "doc_id":
         input_model = DocIdInput(doc_id=job.input_doc_id)
     else:
         input_model = TextInput(text=text)

     # Read back the timeout-check timer (started at `start = time.monotonic()`
     # above) into the field that already exists on Metrics but was never
     # populated anywhere — see PRD §4.2. Purely additive; no gating on is_trial,
     # benefits every caller (trial and main app both).
     metrics.total_duration_ms = (time.monotonic() - start) * 1000.0

     envelope = CarePlanInternal(
         metrics=metrics,
         input=input_model,
         grading=grading,
         care_plan=care_plan,
     )
     ```
     Do not change `backend/models/metrics.py` — the field already exists
     (`total_duration_ms: float | None = None`); this task only assigns it. Do not add
     any new timer; reuse `start` exactly as already computed at line 88.
   - Test changes (in `backend/tests/routes/test_worker.py`):
     - Add a test that a completed job's `output_data["metrics"]["total_duration_ms"]`
       is a positive, non-`None`, non-zero float, using a controllable fake clock so the
       exact value is assertable rather than merely "truthy":
       ```python
       @patch("utils.firebase.firestore.client")
       @patch("routes.worker.complete_job")
       @patch("routes.worker.update_job_stage")
       @patch("routes.worker.fail_job")
       @patch("routes.worker.get_job_doc")
       def test_completed_job_populates_total_duration_ms(
           mock_get_doc, mock_fail, mock_update_stage, mock_complete, mock_fs_client,
           client_worker, monkeypatch,
       ):
           mock_get_doc.return_value = _make_job_doc()
           mock_fs_client.return_value = MagicMock()

           # Two calls to time.monotonic() happen before this task's read-back:
           # once at worker.py:88 (`start`), once at this task's new line. Fake
           # a fixed 2.5s gap between them.
           clock = iter([100.0, 102.5])
           monkeypatch.setattr("routes.worker.time.monotonic", lambda: next(clock))

           care_plan_mock = MagicMock()
           care_plan_mock.to_dict.return_value = {}
           grading_mock = MagicMock()

           def fake_pipeline(text, metrics, grading_enabled, source_kind="text", is_batch=False):
               yield AdapterResult(care_plan=care_plan_mock, grading=grading_mock, raw_text=text, clarified_text="c")

           envelope_mock = MagicMock()
           envelope_mock.to_dict.return_value = {"care_plan": {}, "metrics": {"saved_id": None}}

           with patch.dict("routes.worker.PIPELINES", {"v1-2": lambda *a, **kw: fake_pipeline(*a, **kw)}):
               with patch("routes.worker.CarePlanInternal") as mock_envelope_cls:
                   mock_envelope_cls.return_value = envelope_mock
                   resp = client_worker.post(
                       "/internal/jobs/execute/job-1", headers=QUEUE_HEADER, content_type="application/json",
                   )

           assert resp.status_code == 200
           # Assert on the Metrics instance passed into CarePlanInternal(...),
           # since envelope_mock.to_dict() is a fixed stub in this test.
           passed_metrics = mock_envelope_cls.call_args.kwargs["metrics"]
           assert passed_metrics.total_duration_ms == 2500.0
       ```
       Note: `_check_timeout` also calls `time.monotonic()` once per stage transition
       via `update_job_stage`; since this fake pipeline never advances stages via
       `AdapterStepEvent`, `_check_timeout` is never invoked, so the fake clock's two
       values line up exactly with `start` and this task's new read-back with no extra
       calls to account for. If a future test needs stage events too, extend the
       `clock` iterator accordingly rather than assuming exactly two calls.
     - Add a second test confirming this is unconditional: repeat the same test with
       `_make_trial_job_doc()` instead of `_make_job_doc()` (any `is_trial` job doc) and
       assert `total_duration_ms` is populated there too — regression guard that Task 2
       is not accidentally gated on `is_trial` (PRD §4.2 requires it apply to every
       caller).
   - Acceptance criteria:
     - `cd /root/projects/juno/backend && python3 -m pytest tests/routes/test_worker.py -q`
       passes, including both new tests.
     - `python3 -c "from models.metrics import Metrics; m = Metrics.start('s','v1-2','text'); print(m.total_duration_ms)"`
       still prints `None` (confirms `models/metrics.py` itself is unmodified — only the
       `worker.py` caller changed).
     - A completed job's `output_data["metrics"]["total_duration_ms"]` is a real,
       positive float for both a trial and a non-trial job.

---

### Task 3 — Compute the `before`-grading score concurrently in `backend/services/care_plan_pipeline.py`

   - Files: `backend/services/care_plan_pipeline.py`,
     `backend/tests/care_plan/test_pipeline_executors.py`
   - Depends on: Task 2 (must land first per PRD §1/§4.2, so this task's effect is
     measurable via `total_duration_ms`). Does not depend on Task 1 (disjoint files).
   - Changes: Per PRD §4.3.
     1. Add the import at the top of `backend/services/care_plan_pipeline.py` (alongside
        the existing `from typing import Generator`):
        ```python
        from concurrent.futures import ThreadPoolExecutor
        ```
     2. In `run_care_plan_pipeline` (currently lines 35–132), wrap the existing body in
        a `try/finally` that submits the "before" score computation up front and shuts
        the executor down on every exit path. Current structure:
        ```python
        def run_care_plan_pipeline(
            text: str,
            metrics: Metrics,
            grading_enabled: bool,
            source_kind: str = "upload",
            is_batch: bool = False,
        ) -> Generator[AdapterStepEvent | AdapterResult | AdapterError, None, None]:
            try:
                try:
                    pipeline = CarePlanV1_2Pipeline()
                except Exception as e:
                    yield AdapterError(error_data=build_error_data_from_exc(e))
                    return
                ...
                for event in pipeline.iter_steps(text, wrap_step=wrap_step):
                    ...
                    elif isinstance(event, PipelineRunResult):
                        if grading_enabled:
                            before_score = score_text_safe(text, "before")
                            after_score  = score_text_safe(event.clarified, "after")
                            ...
            except Exception as exc:
                ...
                yield AdapterError(error_data=build_error_data_from_exc(exc))
        ```
        New structure — only three things change: (a) the new executor/future setup
        immediately inside the function before the existing outer `try:`, (b)
        `before_score = score_text_safe(text, "before")` becomes
        `before_score = before_score_future.result()`, and (c) a new `finally:` clause
        after the existing `except Exception as exc:` block:
        ```python
        def run_care_plan_pipeline(
            text: str,
            metrics: Metrics,
            grading_enabled: bool,
            source_kind: str = "upload",
            is_batch: bool = False,
        ) -> Generator[AdapterStepEvent | AdapterResult | AdapterError, None, None]:
            # Kick off the CPU-only "before" grading score immediately: it depends
            # only on `text` (already available, before the pipeline's first LLM
            # call even starts), not on any pipeline step's output — so it runs
            # concurrently with the three sequential Vertex AI calls below instead
            # of serially after all of them (PRD §4.3 / findings doc Finding 3).
            # score_text_safe already swallows its own exceptions and returns None
            # on failure (utils/scoring.py:307-313), so no new exception handling
            # is needed across the thread boundary.
            executor = ThreadPoolExecutor(max_workers=1) if grading_enabled else None
            before_score_future = executor.submit(score_text_safe, text, "before") if executor else None
            try:
                try:
                    pipeline = CarePlanV1_2Pipeline()
                except Exception as e:
                    yield AdapterError(error_data=build_error_data_from_exc(e))
                    return
                ...
                for event in pipeline.iter_steps(text, wrap_step=wrap_step):
                    ...
                    elif isinstance(event, PipelineRunResult):
                        if grading_enabled:
                            before_score = before_score_future.result()
                            after_score  = score_text_safe(event.clarified, "after")
                            ...
            except Exception as exc:
                ...
                yield AdapterError(error_data=build_error_data_from_exc(exc))
            finally:
                if executor is not None:
                    executor.shutdown(wait=True)
        ```
        The `...` sections (step-marker map, `wrap_step`, the `for event in
        pipeline.iter_steps(...)` loop's `StepEvent`/`PipelineStepError` branches, the
        `_grade`/`Markers.Grading.Run.execute(_grade)` body, and the final
        `AdapterResult` yield) are **unchanged** — copy them verbatim from the current
        file. Do not modify `_grade`'s body: it already only ever sees the resolved
        `before_score` value, never the future.
   - Test changes (in `backend/tests/care_plan/test_pipeline_executors.py`, using the
     file's existing `FakePipeline`/`FailingPipeline`/`_make_run_result`/`_make_metrics`
     helpers):
     ```python
     class RaisingConstructorPipeline:
         """Not actually instantiated — CarePlanV1_2Pipeline() itself raises."""
         pass


     def test_grading_enabled_still_computes_before_and_after_scores():
         metrics = _make_metrics()
         mock_scope = _mock_markers()

         with patch("services.care_plan_pipeline.CarePlanV1_2Pipeline", return_value=FakePipeline()), \
              patch("services.care_plan_pipeline.Markers") as mock_markers, \
              patch("services.care_plan_pipeline.score_text_safe") as mock_score, \
              patch("services.care_plan_pipeline.build_grading_with_before_after_score") as mock_build:
             mock_markers.CarePlan.Pipeline.execute.side_effect = lambda fn: fn(mock_scope)
             mock_markers.Grading.Run.execute.side_effect = lambda fn: fn(mock_scope)
             mock_score.side_effect = lambda text, label: {"composite": 50.0, "dimensions": {}}
             mock_build.return_value = MagicMock(entries=[])

             list(run_care_plan_pipeline("plain note", metrics, grading_enabled=True))

         assert mock_score.call_count == 2
         called_args = {c.args for c in mock_score.call_args_list}
         assert ("plain note", "before") in called_args
         assert ("clarified", "after") in called_args


     def test_grading_disabled_never_creates_a_threadpool():
         metrics = _make_metrics()
         mock_scope = _mock_markers()

         with patch("services.care_plan_pipeline.CarePlanV1_2Pipeline", return_value=FakePipeline()), \
              patch("services.care_plan_pipeline.Markers") as mock_markers, \
              patch("services.care_plan_pipeline.ThreadPoolExecutor") as mock_pool:
             mock_markers.CarePlan.Pipeline.execute.side_effect = lambda fn: fn(mock_scope)

             list(run_care_plan_pipeline("plain note", metrics, grading_enabled=False))

         mock_pool.assert_not_called()


     def test_step_error_with_grading_enabled_does_not_hang_or_leak_thread():
         metrics = _make_metrics()
         mock_scope = _mock_markers()

         with patch("services.care_plan_pipeline.CarePlanV1_2Pipeline", return_value=FailingPipeline()), \
              patch("services.care_plan_pipeline.Markers") as mock_markers:
             mock_markers.CarePlan.Pipeline.execute.side_effect = lambda fn: fn(mock_scope)

             events = list(run_care_plan_pipeline("text", metrics, grading_enabled=True))

         error_events = [e for e in events if isinstance(e, AdapterError)]
         assert len(error_events) == 1


     def test_pipeline_constructor_failure_with_grading_enabled_does_not_hang_or_leak_thread():
         metrics = _make_metrics()

         with patch("services.care_plan_pipeline.CarePlanV1_2Pipeline", side_effect=RuntimeError("boom")):
             events = list(run_care_plan_pipeline("text", metrics, grading_enabled=True))

         error_events = [e for e in events if isinstance(e, AdapterError)]
         assert len(error_events) == 1
     ```
     Additionally, **run the two existing marker tests in
     `backend/tests/utils/test_care_plan_markers.py`** —
     `test_grading_run_marker_fired_when_grading_enabled` and
     `test_grading_run_marker_not_fired_when_grading_disabled` — and confirm both still
     pass with zero edits (per PRD §4.3/§7, they patch `score_text_safe` at module level
     with a fixed `return_value`, which continues to resolve correctly whether the call
     happens directly or via `executor.submit(...)`, since Python looks up the
     module-global name at call time inside the running generator, after the patch is
     already active). This is a "confirm unchanged" check, not a code change.
   - Acceptance criteria:
     - `cd /root/projects/juno/backend && python3 -m pytest tests/care_plan/test_pipeline_executors.py -q`
       passes, including all four new tests.
     - `cd /root/projects/juno/backend && python3 -m pytest tests/utils/test_care_plan_markers.py -q`
       passes unmodified.
     - `cd /root/projects/juno/backend && python3 -m pytest tests/ -q` (full suite) is
       green with no new failures anywhere (in particular
       `tests/routes/test_worker.py`, which calls `run_care_plan_pipeline` transitively
       through `PIPELINES["v1-2"]` in several existing tests).
     - `grading_enabled=False` creates no `ThreadPoolExecutor` at all (confirmed by
       `test_grading_disabled_never_creates_a_threadpool`).
     - No test hangs or leaves a dangling thread on either early-return failure path
       (`PipelineStepError`, pipeline-constructor exception) with `grading_enabled=True`.

---

## Post-implementation check

After all three tasks: `cd /root/projects/juno/backend && python3 -m pytest tests/ -q`
should report **more** passing tests than the ~572 baseline (each task adds new tests;
none are removed — Task 1 renames one existing test but keeps it passing) and coverage
should not regress below the ~93% baseline recorded in `README.md`.
