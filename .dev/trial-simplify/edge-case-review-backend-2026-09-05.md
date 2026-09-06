# Trial pathway — backend edge-case review (2026-09-05)

Scope: read-only review of the backend half of `/trial/jobs` (POST + DELETE),
the worker (`/internal/jobs/execute/<job_id>`), input resolution, retention,
and firestore.rules, on `users/tejitpabari/trial-optimizations`. No files
were modified. Method: full read of every file in scope plus everything they
call into, cross-checked against `git diff main...HEAD -- backend/`, and
several throwaway scripts under the session scratchpad to verify UTF-8 size
math and actual exception types raised by the PDF library (PyPDF2 3.0.1) —
not guessed.

---

## BLOCKING

### 1. Text-length cap counts characters, not UTF-8 bytes — legal input can blow Firestore's 1 MiB document limit
**Files:** `backend/routes/trial.py:39`, `backend/services/care_plan_input.py:69-70`, `backend/utils/constants.py:27` (`MAX_TEXT_LENGTH = 500_000`)

Both length checks are `len(text) > Constants.Uploads.MAX_TEXT_LENGTH` — a Python
**character** count. Firestore's hard limit is 1,048,576 **bytes** per document
(UTF-8 encoded). Verified empirically (`scratchpad/` script):

| script | 500,000 chars → UTF-8 bytes |
|---|---|
| ASCII | 500,000 B (0.48 MiB) |
| Cyrillic / Hebrew / Arabic / accented Latin | 1,000,000 B (0.95 MiB) |
| CJK | 1,500,000 B (1.43 MiB) |
| text with emoji / supplementary-plane chars | 2,000,000 B (1.9 MiB) |

A trial user pasting (or uploading a document containing) 500,000 characters of
Chinese/Japanese/Korean/Arabic/Hebrew/Russian text, or ordinary text peppered with
emoji, passes both length checks (character count ≤ 500,000) but produces an
`input_text` field that **alone** exceeds — or comes within a few KB of exceeding —
the 1 MiB document limit, before `uid`, `created_at`, `expires_at`, etc. are even
added. `create_job_doc` (`backend/utils/firebase.py:300-306`) then calls `.set(payload)`,
which Firestore rejects. That exception isn't `ValueError`/`FileNotFoundError`/`JunoError`,
so it falls through `create_trial_job`'s specific handlers (`trial.py:82-91`) to the
generic `except Exception: ... INTERNAL_ERROR, 500` at `trial.py:121-123` — the user
gets an opaque "internal error" instead of the same clear "text too long" message an
equivalent-length English submission would never even trigger (since English ASCII
stays under the cap). This is a real health-equity gap in a public healthcare-adjacent
tool: non-English or emoji-containing input silently breaks well before the character
cap that's supposed to be the limiting factor.

This check is shared verbatim with the main app (`backend/routes/care_plan_jobs.py:47-48`),
so it isn't trial-specific, but the trial is the public, no-login surface this review
is scoped to.

**Fix:** enforce the cap on `len(text.encode("utf-8"))`, not `len(text)`, with a byte
budget conservatively under 1 MiB (e.g. 300–400 KB) to leave headroom for the rest of
the document. Apply in both `_resolve_trial_input` and `validate_extracted_text_length`.

---

### 2. A scanned/no-text-layer document silently bypasses EMPTY_DOCUMENT and runs the full LLM pipeline on filler text
**Files:** `backend/services/care_plan_input.py:138,148,153`, `backend/utils/misc.py:106-107` (`source_separator`), `backend/routes/worker.py:142-144`

`resolve_uploaded_files` appends `f"{source_separator(filename)}{extracted_text.strip()}"`
**unconditionally** for every file, and `source_separator` always returns non-empty text
(`f"\n\n--- Source: {filename} ---\n"`) regardless of whether anything was actually
extracted. Only the image path (`extract_text_from_image`, via the OCR model's
`NO_TEXT_FOUND` sentinel) raises `EMPTY_DOCUMENT` for genuinely-empty content.

For PDF/TXT/DOCX/HTML, no such check exists: `extract_text_from_pdf`
(`backend/utils/pdf.py:20-30`) just returns `""` for a scanned/image-only PDF with no
text layer (extremely common — any document scanned via a phone "scan to PDF" app), and
a blank `.docx`/`.txt`/`.html` behaves the same way. `combined_text` ends up as e.g.
`"--- Source: scan.pdf ---"` — non-empty, trivially under the length cap, so
`validate_extracted_text_length` passes. The job is created and enqueued. In the worker,
`if not text.strip(): fail_job(EMPTY_DOCUMENT)` (`worker.py:142-144`) also passes, because
`text.strip()` is that same non-whitespace separator line. **There is no minimum-content
guard anywhere in `care_plan/v1_2/pipeline.py`** (grepped for `EMPTY_DOCUMENT`/length
checks — none found). The full 5-stage LLM pipeline runs on essentially "--- Source:
scan.pdf ---" and — rather than failing — very plausibly returns `status: completed`
with an LLM-fabricated "care plan" (diagnosis, medications, etc.) hallucinated from
near-nothing, which the user has no reason to distrust.

Confirmed no test covers this: `tests/routes/test_trial.py` only has a regression test
for the image-OCR EMPTY_DOCUMENT path (line 104), nothing for PDF/TXT/DOCX with no
extractable text.

**Fix:** apply the same "meaningful content" check to the *extracted* text per file,
before appending the separator (e.g. check `extracted_text.strip()` is non-empty and
raise/skip if not, mirroring the image path), and/or check `combined_text` against the
extracted content only (excluding separator scaffolding) before validating length.

---

### 3. The retention backstops this design relies on were never deployed
**Files:** `backend/services/retention.py` (code, correct in isolation), cross-checked against `.dev/trial-simplify/gcp-verification-2026-09-05.md` (same-day, this repo)

The code-level cleanup is fine on the happy path: `worker.py`'s `finally` block deletes
the trial's GCS input PDF after the pipeline runs (`worker.py:267-269`), and
`delete_trial_job` deletes it explicitly on user-initiated cleanup (`trial.py:152-156`).
But neither runs if the job never reaches either of those points — Cloud Tasks
exhausting retries, a crashed container before the `finally` block, or a user who
uploads and then just never opens the result tab. The two backstops this design
document (`05-retention-automation/PRD.md`) calls for are:
- A GCS lifecycle rule deleting anything under `care_plan_trial/` after 1 day.
- A scheduled Cloud Run Job (`cleanup_anonymous_users`, using `retention.py`) deleting
  stale anonymous Firebase Auth accounts.

Per this repo's own same-day verification doc, **neither exists in production**:
`gcloud storage buckets describe ... lifecycle` → `null`; `gcloud run jobs list` → the
cleanup job was never deployed; the Cloud Scheduler API is disabled; the scheduler
invoker service account doesn't exist. Only the Firestore TTL policies (on
`care_plan_outputs.expires_at` and `trial_rate_limits.expires_at`) are confirmed active.

Net effect for a public release: any trial upload whose job doesn't reach a terminal
worker state or an explicit DELETE — timeouts, crashes, abandoned tabs, Cloud Tasks
giving up — leaves the uploaded document (potential PHI-bearing content: real clinical
notes users paste in to try the product) in GCS **permanently**, with no automatic
deletion path at all. Likewise every trial visitor's anonymous Firebase Auth account
persists forever. This directly contradicts the "no-retention trial" premise the product
is being described as to users.

**Fix:** this is an infra/deploy gap, not a code bug — run the `05-retention-automation`
PRD's §8 setup checklist (GCS lifecycle rule + Cloud Run Job + Scheduler + IAM binding)
before public release. The code in `retention.py` and `scripts/cleanup_anonymous_users.py`
needs no changes.

---

## SHOULD FIX

### 4. Top-level `input_text` is never cleared for trial jobs, undermining the SP6 size-safety claim
**Files:** `backend/routes/worker.py:224-233` vs `backend/routes/trial.py:45,65` / `backend/utils/firebase.py:300-306,321-335`

The SP6 comment at `worker.py:224-230` says trimming is done "so completed trial docs
stay well under Firestore's 1 MiB doc limit" and pops two things: `care_plan.raw` (which
contains `text`/`simplified_text`/`clarified_text` — see
`models/care_plan/versions/v1_2.py:102-105`) and `input.text`, both **inside**
`output_data`. But the JobDoc's own **top-level** `input_text` field — set once at job
creation (`trial.py:45` for pasted text, `trial.py:65` for uploads) via `create_job_doc`'s
`.set()` — is a completely separate field from `output_data.input.text`, and is never
touched again. `complete_job` (`firebase.py:321-335`) does a partial `.update()`, so it
merges `output_data` etc. into the *existing* document rather than replacing it — the
original, full-length `input_text` survives untouched for the entire 1-hour trial TTL.
So the actual field that's popped (`output_data.input.text`) is a second, smaller-impact
copy; the largest copy of the raw input is exactly the one that's kept. This means the
"stay under 1 MiB" mitigation is only partially effective, and directly compounds
Finding 1: a near-cap multi-byte submission that manages to squeak under 1 MiB at
creation time can still be pushed over the limit by `complete_job`'s `.update()` adding
`output_data` on top of the still-present `input_text`.

It also means a "no-retention" trial keeps the user's full raw pasted/extracted text
readable in Firestore (and pushed to the frontend's live snapshot listener on every
resync) for the whole job lifetime, when the design intent (per the same comment) was
clearly to drop it.

**Fix:** in the same `is_trial` branch, also strip/blank the top-level `input_text`
field via an additional `.update({"input_text": firestore.DELETE_FIELD})` (or set to
`None`) in `complete_job`/`fail_job` for trial jobs — it's write-once (by
`create_job_doc`), read-once (by `resolve_input_from_job_doc` at worker start,
`care_plan_input.py:197-201`), and never needed again after that point.

---

### 5. A lone UTF-16 surrogate in the JSON `text` body crashes job creation with an uncaught encode error
**Files:** `backend/routes/trial.py:36-51`, `backend/utils/firebase.py:300-306`

`json_data.get("text")` comes straight from `request.get_json(silent=True)`, i.e.
Python's stdlib `json.loads`. Verified empirically: `json.loads('{"text": "\\ud800"}')`
happily decodes into a Python `str` containing an **unpaired surrogate** codepoint —
JSON's escape syntax permits this even though it isn't a valid Unicode scalar value.
That string cannot be UTF-8 encoded (`s.encode("utf-8")` raises
`UnicodeEncodeError: 'utf-8' codec can't encode character '\ud800' ... surrogates not
allowed`), and Firestore's client eventually needs to UTF-8-encode every string field
(over gRPC/protobuf) to write it. So a POST to `/trial/jobs` with
`Content-Type: application/json` and body `{"text": "...\ud800..."}` sails through
`_resolve_trial_input`'s `.strip()` and length check (neither validates encodability),
into `create_job_doc`'s `.set(payload)` — which raises an exception not caught by any
of `create_trial_job`'s specific handlers, falling to the generic `except Exception:`
→ 500 (`trial.py:121-123`), with a full traceback logged server-side on every occurrence.
This is trivially reachable by any anonymous caller (no exploit sophistication needed),
though bounded by the 5-requests/hour/IP rate limit, so its abuse ceiling is low —
still, it's also reachable by accident (some client-side Unicode-handling bugs produce
unpaired surrogates from clipboard paste of certain characters).

**Fix:** validate that `text_input.encode("utf-8", errors="strict")` succeeds (or
proactively sanitize with `errors="replace"`/`"surrogatepass"`-then-clean) before
returning from `_resolve_trial_input`, raising the existing `ValueError` path (400) on
failure instead of letting it reach Firestore.

---

### 6. Corrupt / zero-byte / encrypted / mislabeled-extension PDFs 500 instead of returning a clean validation error
**Files:** `backend/services/care_plan_input.py:88-89` (`extract_text_from_pdf` call site), `backend/routes/trial.py:82-91`

`extract_text_from_bytes` calls `extract_text_from_pdf(file_bytes)` with no
try/except, and `resolve_uploaded_files`/`_resolve_trial_input` don't catch anything
from PyPDF2 either. Verified concretely against the actual installed PyPDF2 3.0.1 in
this repo's venv:

| input | exception raised |
|---|---|
| zero-byte `.pdf` | `PyPDF2.errors.EmptyFileError: Cannot read an empty file` |
| garbage bytes with a `.pdf` extension (e.g. a mislabeled zip/txt) | `PyPDF2.errors.PdfReadError: EOF marker not found` |
| a genuinely password-protected PDF (built with `pypdf.PdfWriter.encrypt(...)`, then read back) | `PyPDF2.errors.FileNotDecryptedError: File has not been decrypted` |

None of these are `ValueError`, `FileNotFoundError`, or `JunoError`, so all three fall
through `create_trial_job`'s specific handlers to the generic 500 at `trial.py:121-123`
— a user who uploads a corrupted, empty, or password-protected PDF (all realistic,
non-malicious scenarios) gets an opaque "internal error" instead of an actionable
"file is corrupted/encrypted, please try again" 400.

**Fix:** wrap the `extract_text_from_bytes` call (or specifically the PDF/DOCX/image
branches) in a `try/except Exception` that re-raises as `ValueError` with a clear
message, consistent with how `UNSUPPORTED_FILE_TYPE` is already handled via `JunoError`.

---

### 7. Worker idempotency guard doesn't cover "processing" — a Cloud Tasks redelivery can re-run the whole pipeline (and re-bill the LLM)
**File:** `backend/routes/worker.py:67-69`

```python
if job.status in ("completed", "error"):
    logger.info(...); return "", 200
```
This only short-circuits a **second** delivery of a job that already reached a
terminal state. If a first worker attempt sets `status: "processing"`
(`worker.py:76-81`) and then dies before reaching `complete_job`/`fail_job` — container
OOM-kill, an uncaught exception whose own `fail_job` call in the `except` block also
fails (e.g. because the doc was concurrently deleted — see below), or simply a 5xx
returned to Cloud Tasks after partial work — Cloud Tasks' documented "at least once"
delivery will redeliver the task, and this second (or later) delivery will see
`status == "processing"` (not `completed`/`error`), skip the idempotency check, and
re-run **the entire 5-stage LLM pipeline from scratch**, including all Vertex AI calls,
a second time. There's no staleness check (e.g. "processing but `started_at` is older
than the deadline, so treat as abandoned and safe to retry" vs. "processing and fresh,
so skip"), and no transactional claim/lock on the job before starting work. This is a
real, if lower-probability (retry-triggered, not attacker-triggered), duplicate-LLM-cost
and wasted-compute bug — exactly the scenario the pipeline needs to be resilient to
given Cloud Tasks' delivery semantics.

**Fix:** either (a) transactionally claim the job (e.g. `update` with a precondition
that `status != "processing"`, or a monotonic `attempt` counter) before starting
pipeline work, or (b) treat "processing" as re-runnable only once `started_at` is older
than `deadline_s`, otherwise return 200 without re-running (accepting that a truly stuck
job stays stuck until its own timeout is hit some other way).

---

### 8. One bad file in a multi-file trial upload aborts the entire submission, discarding already-good extracted text
**File:** `backend/services/care_plan_input.py:111-146`

`resolve_uploaded_files` iterates all uploaded files in one loop and calls
`extract_text_from_bytes` on each in sequence (line 137). If any single file raises
(most notably `JunoError(EMPTY_DOCUMENT)` from `extract_text_from_image` on a
blank/blurry image — but also any of Finding 6's PDF exceptions), the exception
propagates immediately out of the loop, discarding all text already extracted from
prior files in the same request. A common real scenario: a user uploads a 5-page
scanned document as 5 image files, and one page happens to be a blank divider or came
out blurry — the *entire* 5-page submission fails with "Image contained no readable
text", even though 4 of the 5 pages had perfectly good content, forcing the user to
identify and remove the one bad file and resubmit. Since trial allows at most 5 files
(`Constants.Trial.MAX_FILE_COUNT`), this is a realistic multi-page-upload failure mode,
not an edge case.

**Fix:** collect per-file extraction failures without aborting the whole batch — skip
files that raise `EMPTY_DOCUMENT`/extraction errors (optionally surfacing which
filenames were skipped) and only fail the whole request if *no* file yields any usable
text.

---

## NICE TO HAVE

### 9. Rate-limit IP hashing degrades to unsalted SHA-256 if `TRIAL_RATE_LIMIT_SALT` is unset
**File:** `backend/utils/rate_limit.py:113-117`

`_hash_ip` only logs a warning and proceeds with an empty HMAC key if the salt env var
isn't set — it doesn't fail closed. An unsalted `hmac.new(b"", ip, sha256)` is
trivially reversible against the small IPv4 address space (rainbow-table/brute-force),
so if this env var is ever missing in production, the `trial_rate_limits` collection's
document IDs effectively become a reversible IP log. This can't be confirmed or denied
from the backend code alone (it depends on deployment config outside this repo's
backend/ tree), so flagging as a hardening item: consider failing closed (or falling
back to a process-local random salt, which still beats none) rather than silently
degrading.

### 10. Raw `str(exception)` text can end up in `error_data.details`, which the client reads
**File:** `backend/errors/exceptions.py:104-127,182-189`

`_classify_exc`'s fallback case returns `str(exc)` as the `detail`, which
`build_error_data_from_exc` (called from `worker.py:259` on any unhandled exception)
stores verbatim into `error_data.details` on the Firestore job doc — a field the
frontend's live listener reads. For most exceptions this is an innocuous library/network
error string, but some exception types (e.g. certain Pydantic `ValidationError`s) embed
the actual invalid value in their message. No concrete leak of document content was
found in this review, but as defense-in-depth for a "no PHI ever leaves the pipeline"
posture, consider truncating/allow-listing `error_data.details` for `UNKNOWN_ERROR`-class
failures rather than passing through arbitrary exception text.

---

## Verified safe (checked, not a finding)

- **Anonymous-token isolation:** every non-trial route (`clinician_dataset.py`,
  `care_plan_jobs.py`, `datasets.py`, `batch_jobs.py`, `saved_outputs.py`,
  `grading.py`) uses bare `@verify_firebase_token` (`allow_anonymous=False` by
  default); only `trial.py`'s two routes opt into `allow_anonymous=True`. An
  anonymous trial token cannot reach any main-app route.
- **firestore.rules ownership check:** `allow get` requires `request.auth.uid ==
  resource.data.uid` (or `resource.data.shared == true`, which is hard-coded `False`
  at creation for every job via `JobDoc.for_single` and never flipped by any trial
  code path) — an anonymous user cannot read another user's job doc even if they
  guess a job_id (128-bit UUID4, not enumerable in practice). `allow write: if
  false` means clients can never write directly regardless.
- **No doc resurrection on delete-mid-processing race:** every worker write after
  creation (`update_job_stage`, `complete_job`, `fail_job`) uses Firestore
  `.update()`, which fails with `NotFound` on a deleted document rather than
  recreating it. If a user's tab-close DELETE races the worker, the worker's
  subsequent writes 500 (causing one wasted Cloud Tasks retry that then correctly
  no-ops via `get_job_doc(job_id) is None` → `return "", 200`), but the doc is never
  resurrected and no data is corrupted.
- **GCS cleanup is best-effort and idempotent:** `delete_gcs_object` swallows
  `NotFound` and logs (never raises) on any other failure, so double-delete (e.g. via
  both the DELETE route and the worker's `finally` block) is harmless.
- **Whitespace-only pasted text:** `.strip()` in `_resolve_trial_input` reduces it to
  `""`, which is treated as "no text provided" and falls through to the files-required
  400, not silently accepted as empty input.
- **CORS:** explicit origin allow-list (no wildcard), `supports_credentials=False`;
  cross-origin access to non-trial routes is additionally blocked by the anonymous-token
  check above even if a request got past CORS.
- **SP6 concurrent before-score change (`care_plan_pipeline.py`):**
  `score_text_safe` already catches all its own exceptions and returns `None`
  (`utils/scoring.py:307-313`), so `before_score_future.result()` cannot raise from
  inside the submitted work; the `ThreadPoolExecutor` is created/shut down
  (`wait=True`) around the same try/finally that already wrapped the pipeline, so a
  pipeline failure before `PipelineRunResult` still cleanly waits for and discards the
  in-flight before-score future. No new race or exception-swallowing was introduced by
  this diff.
- **`total_duration_ms` population (`worker.py:205`):** computed once, synchronously,
  right before serialization — no race with the timeout-check timer it reads from.

---

## Summary

| # | Severity | Title |
|---|---|---|
| 1 | BLOCKING | Character-count text cap doesn't bound Firestore's byte-based 1 MiB limit |
| 2 | BLOCKING | No-text-layer documents bypass EMPTY_DOCUMENT, LLM runs on filler text |
| 3 | BLOCKING | GCS lifecycle + anon-account cleanup automation never deployed |
| 4 | SHOULD FIX | Top-level `input_text` never cleared for trial jobs |
| 5 | SHOULD FIX | Lone surrogate in JSON `text` crashes job creation |
| 6 | SHOULD FIX | Corrupt/zero-byte/encrypted PDFs 500 instead of 400 |
| 7 | SHOULD FIX | Worker idempotency gap on "processing" status (duplicate LLM run) |
| 8 | SHOULD FIX | One bad file aborts an entire multi-file upload |
| 9 | NICE TO HAVE | Rate-limit IP hash degrades to unsalted if env var unset |
| 10 | NICE TO HAVE | Raw exception text can reach `error_data.details` |
