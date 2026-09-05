# Trial pathway — scenario validation (2026-09-05)

Scope: release-confidence validation of the trial pathway (`POST /trial/jobs` →
`services/care_plan_input.py` → Firestore `care_plan_outputs` doc → Cloud Tasks →
`routes/worker.py` → `services/care_plan_pipeline.py` → results → `DELETE /trial/jobs/<id>`)
on `users/tejitpabari/trial-optimizations`, per the 11 scenarios specified for this run.

**Method.** New end-to-end tests in
`backend/tests/routes/test_trial_e2e_scenarios.py` (38 tests) drive the REAL Flask
routes (`routes/trial.py`, `routes/worker.py`) and the real helper chain
(`services/care_plan_input.py`, `utils/firebase.py`'s job-lifecycle functions,
`utils/pdf.py`, `utils/misc.py`) end to end, with only external services mocked:
an in-memory `FakeFirestoreClient` stands in for `utils.firebase.firestore_client()`
so `create_job_doc`/`get_job_doc`/`complete_job`/`fail_job`/`update_job_stage` are the
real functions operating on real in-memory state (including `firestore.DELETE_FIELD`
and NotFound-on-missing-doc semantics); GCS and Cloud Tasks are mocked at their module
boundary; the LLM/Vertex pipeline is overridden with a fake generator yielding **real**
Pydantic `CarePlanV1_2`/`Grading` model instances (not `MagicMock`s) so
`output_data == envelope.to_dict()` is genuine serialization, except in scenario 9
where only the Vertex-call-level methods are mocked so the real exception
classification path is exercised. Degenerate-input fixtures (scanned/no-text-layer PDF,
corrupt PDF, encrypted PDF, ZIP-as-PDF, blank DOCX, real JPEGs) are generated
programmatically, not committed as binaries.

All 38 new tests pass, alongside the full existing relevant suite (204 tests total
across `test_trial_e2e_scenarios.py` + `test_trial.py` + `test_worker.py` +
`tests/services/` + `tests/care_plan/`), plus `tests/models/` (69) and
`tests/routes/test_care_plan_jobs.py` (20) re-run as a blast-radius check on the two
backend fixes below.

---

## Bugs found and fixed

### 1. A single unusable file in a "tolerant" trial upload lost its specific error message
**Files:** `backend/services/care_plan_input.py` (`resolve_uploaded_files`)

Finding 8 from the earlier edge-case review (already fixed on this branch) made trial
uploads tolerate per-file failures rather than aborting the whole batch. But it also
had a side effect nobody had tested: when a request has **exactly one file** and that
file is corrupt/encrypted/a mislabeled ZIP/an unsupported type, the loop "skips" it
(recording only a filename in `skipped_files`) and falls through to the bottom
`if not filenames:` check, which always raised a generic
`EMPTY_DOCUMENT` ("None of the uploaded files contained readable text... make sure the
file contains selectable text, not a scanned image"). For a genuinely
password-protected or corrupt single-file upload, this is actively misleading — it
tells the user their scan has no text layer when the real problem is that the file
couldn't be opened at all. Scenario 5's degenerate-input tests
(`test_corrupt_pdf_returns_clean_error`, `test_password_protected_pdf_returns_clean_error`,
`test_zip_disguised_as_pdf_returns_clean_error`) caught this directly.

**Fix:** `resolve_uploaded_files` now tracks the actual exception object alongside each
skipped filename (`skipped_errors`). When every file failed AND there was only one file
in the request, it re-raises that file's own specific, already-classified error
(`FILE_PARSE_FAILED` with "password-protected"/"corrupted" detail, `UNSUPPORTED_FILE_TYPE`,
etc.) instead of the generic `EMPTY_DOCUMENT`. A genuine multi-file all-bad batch (≥2
files) is unaffected and still raises the generic `EMPTY_DOCUMENT` — this exactly
matches scenario 6's own spec ("all 5 unusable → single clean EMPTY_DOCUMENT error").
Verified against the existing `tests/services/test_care_plan_input.py` suite (all
still pass unchanged — no existing test covered the single-file-tolerant-failure case).

### 2. `skipped_files` was computed and unit-tested but never reached the client
**Files:** `backend/models/job.py` (`JobDoc`), `backend/routes/trial.py`
(`_resolve_trial_input`)

`resolve_uploaded_files` has computed and returned `ResolvedInput.skipped_files` since
Finding 8 landed, and it's unit-tested at that layer
(`tests/services/test_care_plan_input.py`) — but `routes/trial.py`'s
`_resolve_trial_input` never included it in the dict passed to `JobDoc.for_single`, and
`JobDoc` had no field for it at all. So a partial-failure batch (scenario 6: "5 files,
2 unusable, succeeds using 3 good ones") silently dropped which files were skipped —
neither the POST response nor the Firestore job doc ever recorded it, so no future
frontend UI could tell the user "we skipped `blank.txt` and `corrupt.pdf`."

**Fix:** added `skipped_files: list[str] = []` to `JobDoc` (harmless, additive — default
`[]` for every non-trial job and every trial job with nothing skipped) and populated it
from `resolved.skipped_files` in `_resolve_trial_input`'s upload branch. Verified via
`test_two_of_five_unusable_succeeds_with_skipped_files_reported`, which asserts
`doc["skipped_files"] == ["blank.txt", "corrupt.pdf"]` after a full create→doc-inspect
cycle. This is additive-only; no existing field was renamed or restructured, so
`firestore.rules` and the frontend's existing field reads are unaffected.

Both fixes are commits `<see final commit list below>`.

---

## Scenario-by-scenario results

### 1. Typical discharge summary (~8-page text-layer PDF-equivalent) → completed doc
**PASS.** Full chain (create → worker → completed doc → delete) exercised with a
realistic multi-page discharge-summary text and a realistically-sized `CarePlanV1_2`
output (6 medications, 3 tests, 2 procedures, 2 warning signs, 12 glossary terms, plus
`RawArtifacts`) and full 14-entry `Grading` (12 per-method + 2 combined).

- Completed doc's `output_data.grading.entries` contains **exactly 2 entries**, both
  `name == "combined"` — the 12 non-combined per-method entries are stripped.
- `output_data.care_plan` has no `raw` key.
- `output_data.input.text` is `None` (popped).
- Top-level `input_text` is **absent entirely** (`firestore.DELETE_FIELD`'d by
  `complete_job`).
- No single field's leaf string value exceeds 1500 bytes.
- **Measured completed-doc size: 9,124 bytes** (~0.87% of the 1 MiB Firestore document
  limit) — via UTF-8-encoded-JSON-length proxy (see caveat below).
- `DELETE` afterward returns 204 and the doc is gone.

### 2. Phone photos of a paper after-visit summary (3 JPEGs, OCR path) → completed doc
**PASS.** 3 real JPEGs (generated via PIL) with `extract_text_from_image` mocked to
return distinct per-page OCR text. All 3 pages' text lands in the combined
`input_text` at creation; the job completes normally through the same worker path as
scenario 1, and `input_text` is cleared on completion.

### 3. Mixed batch (5 files, ~10 MB) — succeeds under, clean 400 over, clean 400 at 6 files
**PASS**, with one construction note. A 5-file batch (PDF, DOCX, 2 JPEGs, TXT) padded to
just under the trial's 10 MB aggregate cap succeeds (202, doc created). Padding had to
go **after each JPEG's end-of-image marker**, not into the `.txt` file — padding the
`.txt` file inflates the *extracted text* itself (a completely different, much lower
350,000-byte cap) rather than just the *file size* (the 10 MB cap), which is itself a
useful confirmation that these two limits are independent and both correctly enforced
at their own layer. Verified empirically that PIL still decodes a JPEG with 2 MiB of
trailing garbage bytes appended (real image content up to the EOI marker, garbage
after) — this is a legitimate way to pad file *size* without touching extracted *text*.
- Just over 10 MB (5 files): clean `400 INPUT_VALIDATION_ERROR`, never 413, never 500.
- 6 files: clean `400 INPUT_VALIDATION_ERROR`.

### 4. Non-English / emoji-heavy input near the limits
**PASS.**
- CJK text under the 500,000-char cap but over the 350,000-byte cap (3 bytes/char):
  clean 400.
- Arabic (RTL) text over the byte cap: clean 400.
- Emoji (`😀`, U+1F600, a UTF-16 surrogate pair, 4 UTF-8 bytes/char) over the byte cap:
  clean 400.
- Mixed CJK + Arabic + emoji + combining-diacritic text engineered to sit just under
  **both** caps: **202**, completes, and the finished doc stays under 1 MiB.
- NUL byte and a lone UTF-16 surrogate (via raw JSON `\ud800`, which `json.loads`
  permits even though it can't be UTF-8 encoded) in pasted text: both clean 400, no
  leaked internals.
- Plain combining diacritics alone (valid Unicode, no cap issue): accepted normally —
  confirms the byte-cap logic isn't over-triggering on any multi-byte content.

**Measured completed-doc size (worst case): 17,671 bytes** — this run deliberately
combined the near-max-byte multibyte input (349,998 of 350,000 bytes) with the
**larger** "dense" output fixture (14 medications, 7 tests, etc.) to stress both ends
at once. The number is small **specifically because the near-max input text never
appears in the final doc at all** — see the important finding below.

**Important finding (not a bug, a confirmation):** because trial `complete_job`/`fail_job`
now clear the top-level `input_text` field (Finding 4 fix, already landed on this
branch) *and* `output_data.input.text` is popped in `routes/worker.py`, **the final
completed/failed trial doc's size is now independent of the input size entirely** — a
500,000-character input and a 20-character input produce the same-sized completed doc
(bounded only by the structured output). This is a strong confirmation the Finding
1+4 fixes together close the original Firestore-write-failure bug: there is no
remaining code path in this branch where a near-cap `input_text` and a full
`output_data` coexist in the same persisted document.

**Size-measurement caveat:** `_doc_size_bytes` uses UTF-8-encoded-JSON length as a proxy
for Firestore's actual wire size (protobuf field/type overhead differs from JSON, and
this proxy isn't exact), but it's a conservative, reasonable regression signal for
"stays comfortably under 1 MiB," which both measurements (9,124 and 17,671 bytes) do
by roughly two orders of magnitude of headroom.

### 5. Degenerate inputs
**PASS** (with the Finding 1 bugfix above making 3 of these cases correctly classified
rather than merely "not a 500"). All produce a clean 4xx, never 500, never
`"Traceback"`/library internals in the response body:

| Input | Result |
|---|---|
| Scanned PDF, no text layer | 422 `EMPTY_DOCUMENT` |
| Zero-byte file | 4xx (no leak) |
| Corrupt PDF (garbage bytes) | 422 `FILE_PARSE_FAILED` *(was `EMPTY_DOCUMENT` before fix #1)* |
| Password-protected PDF | 422 `FILE_PARSE_FAILED`, "password-protected" detail *(was `EMPTY_DOCUMENT` before fix #1)* |
| `.pdf` that's actually a ZIP | 422 `FILE_PARSE_FAILED` *(was `EMPTY_DOCUMENT` before fix #1)* |
| Blank DOCX | 422 `EMPTY_DOCUMENT` |
| Whitespace-only pasted text | 400 (falls through to "no input provided") |
| Pasted text with a NUL byte | 400 `INPUT_VALIDATION_ERROR` |
| Pasted text with a lone UTF-16 surrogate | 400 `INPUT_VALIDATION_ERROR` |

### 6. Partial-failure batch
**PASS** (after fix #2 above made `skipped_files` actually observable). 5 files (3
good `.txt`, 1 blank, 1 corrupt PDF) → 202, job doc's `input_text` contains all 3 good
notes' content, and `skipped_files == ["blank.txt", "corrupt.pdf"]`. All 5 unusable →
single clean 422 `EMPTY_DOCUMENT` (no partial/duplicate errors).

### 7. Filename hostility
**PASS**, with one method note. Unicode/emoji filename (`患者記録😀report.txt`), a
255-char filename, and a path-traversal filename (`../../etc/passwd.txt`) were all
driven through the real HTTP route: in every case the GCS blob path (asserted via the
mocked `bucket.blob()` call) is built purely from `{prefix}/{user_id}/inputs/{uuid}.pdf`
— the filename never appears in it, so no traversal or injection is structurally
possible regardless of what a filename contains.

The "filename with a newline or quote" case could **not** be constructed as an
HTTP-transport-level test: verified empirically that Werkzeug's own multipart
encoder/parser (both the test client's, and per RFC 2046 any compliant real one)
truncates the filename at an embedded, unescaped `"` and cannot carry a raw CR/LF in a
`Content-Disposition` header field at all — this is enforced by the HTTP multipart
format itself, not something the application needs to separately defend against for
that exact raw-byte case. What *is* meaningfully testable is the application's
handling once such a string is a parsed `.filename` value (e.g. a non-browser HTTP
client that doesn't escape it) — driven directly against the real
`resolve_uploaded_files()` with a hostile filename object, confirming it's handled as
plain string data (survives into the combined text via `source_separator`, never used
as a dict/mapping key) with no crash.

### 8. Lifecycle races
**PASS**, all three sub-cases:
- **DELETE mid-worker-write:** simulated the DELETE landing exactly between the
  worker's `get_job_doc` and `complete_job` (a fake pipeline that deletes the doc from
  the fake Firestore store before yielding its result). `complete_job`'s `.update()`
  against the now-missing doc raises `NotFound` (mirrors real Firestore semantics); the
  outer handler's own best-effort `fail_job` also fails against the missing doc
  (swallowed); worker returns 500. Critically: **the doc is not resurrected** (confirmed
  absent from the store afterward) and **GCS cleanup still ran** (the worker's own
  `finally` block calls `delete_gcs_object` regardless of the exception above it) — not
  orphaned.
- **Redelivery while lease is fresh:** a job left at `status="processing"`,
  `started_at` 10s ago (well within the 270s single-job budget) → worker returns 200
  as a pure no-op; the pipeline function is **never invoked** (confirmed via a call
  counter) — no duplicate LLM billing.
- **Redelivery after lease expiry:** same setup but `started_at` 300s ago (past the
  270s budget) → worker treats the prior attempt as abandoned, **does** run the
  pipeline (exactly once), and completes normally.

### 9. Failure surfaces
**PASS** for the three classifiable LLM failures; **documented, not "fixed"** for the
hard-kill case (see below — this is out of scope for a backend-code fix, it's an
inherent property of "the process died").
- **429 (`google.api_core.exceptions.ResourceExhausted`)** raised from the real
  pipeline's `_generate_text` (only the Vertex-call boundary mocked, not
  `PIPELINES`) → real `care_plan/v1_2/pipeline.py` → `services/care_plan_pipeline.py`
  → `errors.build_error_data_from_exc` classification chain runs for real → job doc:
  `status="error"`, `error_data.code == "VERTEX_QUOTA_EXCEEDED"`, `input_text` cleared.
- **Timeout (`DeadlineExceeded`)** → same real chain → `error_data.code ==
  "VERTEX_DEADLINE_EXCEEDED"`.
- **Malformed JSON** (`JunoError(LLM_INVALID_JSON)` from the structuring step) →
  `error_data.code == "LLM_INVALID_JSON"`, no raw exception text in the persisted
  `error_data`.
- **Hard-kill (worker process dies mid-job):** no code path in this repo flips a
  `"processing"` job to a terminal state on its own if the process that set it dies
  before reaching `complete_job`/`fail_job` — confirmed by construction (a job doc set
  to `"processing"` with no corresponding worker request ever made stays
  `"processing"` — there is nothing else that would touch it). Two things eventually
  rescue this in production, verified from the code that implements them (not
  exercised end-to-end from this backend suite, since one lives in `frontend-trial/`):
  (a) if Cloud Tasks redelivers the task, `routes/worker.py`'s processing-lease check
  (scenario 8, `SINGLE_JOB_INTERNAL_DEADLINE_S = 270`s) treats a stale lease as
  abandoned and retries; (b) independently,
  `frontend-trial/src/components/ProcessingScreen.tsx`'s client-side
  `WATCHDOG_TIMEOUT_MS = 6 * 60 * 1000` (6 minutes) fires and shows the user a rescue
  message regardless of what the backend does. **Not independently verified**: whether
  Cloud Tasks' actual configured retry policy for the `care-plan-jobs-trial` queue
  guarantees a redelivery within any particular window — that's queue configuration in
  GCP, outside this backend code review's reach.

### 10. Rate limiting
**PASS.**
- **Burst, real `check_rate_limit()`/`_check_and_increment` logic** (only the
  Firestore persistence call chain faked, not the rate-limiter's own counting logic):
  the first `RATE_LIMIT_PER_IP_PER_HOUR` (5) requests from one IP pass the limiter
  (they then fail at auth with 401, since this test targets the limiter specifically,
  not full auth); the 6th and 7th are blocked with `429` **before auth even runs**
  (`rate_limit_trial` wraps `verify_firebase_token`).
- **Proxy-hop selection cannot be bypassed by a spoofed `X-Forwarded-For`:** with this
  deployment's real 1-trusted-hop topology, `get_client_ip()` always takes the
  rightmost value (Google-appended, un-spoofable) — verified that a client-prepended
  fake IP to the left of the real one has no effect on which value is selected.
- **Rate limiter's own Firestore call failing → fails OPEN, not 500:** `check_rate_limit`
  raising `RuntimeError` still lets the request proceed into (and correctly fail) the
  normal auth check (401), never a 500 — this is a documented, deliberate product
  choice (`rate_limit_trial`'s own comment: availability over strict enforcement for a
  free-feature abuse guard).

### 11. Access control
**PASS at the route level; NOT independently executed against a live Firestore
emulator** — see caveat below.
- Anonymous user B's token cannot `DELETE` user A's trial job doc: `403`, doc
  untouched, GCS delete never invoked.
- Anonymous user A can `DELETE` their own job doc: `204`, doc removed.
- `firestore.rules` was reviewed **statically** (read directly): `allow get` requires
  `request.auth.uid == resource.data.uid` (or the hard-coded-`false`-at-creation
  `shared` flag, never flipped by any trial code path), `allow list` requires the same
  uid match, `allow write: if false` unconditionally (server writes go through the
  Admin SDK, which bypasses rules entirely — consistent with how the app itself
  writes). This logically matches the route-level behavior verified above. **No
  Firestore emulator or `@firebase/rules-unit-testing` harness exists in this repo**
  (`firebase.json` has no `emulators` block, and `firebase-tools` is installed but
  unconfigured for this purpose) — standing one up was judged out of scope for this
  test-writing pass; this scenario's rules-file conclusion is a static read, not a
  live-executed test, and should be flagged as such rather than treated as
  emulator-verified.

---

## Ambiguities flagged (not silently resolved)

- **Scenario 5 vs. scenario 6 interaction (now resolved by fix #1 above):** whether a
  single unusable file in a "tolerant" trial upload should surface its own specific
  error or the generic multi-file `EMPTY_DOCUMENT` was genuinely ambiguous before this
  run (no existing test covered it either way). Resolved by fix #1's reasoning
  (single-file re-raises the specific error; ≥2-file all-bad still gets the generic
  message, matching scenario 6's explicit spec) rather than guessed.
- **Scenario 9's hard-kill "how long until rescued"** is explicitly a frontend +
  infra (Cloud Tasks queue retry policy) question, not something a backend-only test
  suite can execute end-to-end. Documented above rather than asserted as tested.
- **Scenario 11's firestore.rules verification** is static, not emulator-executed, per
  explicit task allowance for this case.

---

## Test run summary

```
backend/tests/routes/test_trial_e2e_scenarios.py .................................... [38 passed]
backend/tests/routes/test_trial.py + test_worker.py + tests/services/ + tests/care_plan/ [204 passed total]
backend/tests/models/                                                                  [69 passed]
backend/tests/routes/test_care_plan_jobs.py                                            [20 passed]
```

All green. No test was left failing or skipped.

## Files touched

- `backend/tests/routes/test_trial_e2e_scenarios.py` — new, 38 tests (this deliverable).
- `backend/models/job.py` — added `JobDoc.skipped_files` field (additive).
- `backend/routes/trial.py` — populate `skipped_files` from `resolved.skipped_files`.
- `backend/services/care_plan_input.py` — single-unusable-file re-raises its specific
  error instead of a generic `EMPTY_DOCUMENT`.
