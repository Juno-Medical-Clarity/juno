# Care-Plan Processing Pipeline

**Scope of this document.** This is a technical reference for the backend pipeline that
turns a submitted clinical document into a patient-friendly care plan — the same
pipeline used by both the authenticated full app (`POST /care_plan/jobs`) and the
public, no-login trial (`POST /trial/jobs`). It covers input handling, async job
orchestration, the five pipeline stages, term detection, readability scoring, error
handling, and observability, as implemented on branch
`users/tejitpabari/trial-optimizations` as of 2026-09-06.

**Out of scope** (acknowledged but not detailed): datasets/Athena presets
(`routes/datasets.py`, `routes/clinician_dataset.py`), the admin surface
(`routes/admin.py`), saved outputs (`routes/saved_outputs.py`), batch jobs
(`routes/batch_jobs.py`, `utils/batch.py`), and the clinician dataset builder. These are
full-app-only surfaces that sit around the same pipeline and job-doc machinery
described here; they are not part of the trial's request path. Frontend behavior,
Firestore/GCS/Cloud Tasks internals, and how Gemini itself reasons are also out of
scope — those are treated as black boxes: this document describes what is sent to them
and what is done with what comes back.

Source pointers use the form `path:line`. Line numbers are for orientation; verify
against the current file.

---

## 1. High-level journey of one document

```
Client                    API service                  Firestore              Worker service (Cloud Run)
  │                       (JUNO_MODE=api)               care_plan_outputs           (JUNO_MODE=worker)
  │  POST /trial/jobs           │                             │                          │
  │  or /care_plan/jobs ───────►│                             │                          │
  │                       resolve input:                      │                          │
  │                       extract text from                   │                          │
  │                       PDF/TXT/DOCX/HTML/                  │                          │
  │                       image (Gemini OCR),                 │                          │
  │                       merge into one PDF                  │                          │
  │                       (upload to GCS)                     │                          │
  │                              │──create job doc───────────►│                          │
  │                              │   status=not_started        │                          │
  │                              │──enqueue Cloud Task────────────────────────────────────►│
  │  ◄── 202 {job_id} ───────────│                             │      (OIDC-signed POST)  │
  │                                                            │                          │
  │  (client listens to the job doc for live status/stage)     │                    mark processing,
  │  ◄─────────────────────────────────────────────────────────── stage=1 ──────────── stage=1
  │                                                            │                          │
  │                                                            │                   resolve input text
  │                                                            │                   (already stored, or
  │                                                            │                    re-fetched from GCS/
  │                                                            │                    Athena for other kinds)
  │                                                            │                          │
  │                                                            │                   run pipeline:
  │                                                            │                    2 detect_terms
  │  ◄─────────────────────────────────────────────────────────── stage=2..5 ────── 3 simplify_language (LLM)
  │                                                            │                    4 clarify_and_action (LLM)
  │                                                            │                    5 structure_document (LLM)
  │                                                            │                          │
  │                                                            │                   compute grading (before/after
  │                                                            │                    readability scores)
  │                                                            │                          │
  │                                                            │◄──complete_job / fail_job │
  │  ◄── (Firestore snapshot: status=completed|error) ─────────│                          │
```

The API service (`JUNO_MODE=api`) and the worker service (`JUNO_MODE=worker`) are the
same Flask application (`backend/app.py`) deployed as two separate Cloud Run services,
distinguished only by which blueprint list they register
(`routes/__init__.py:API_BLUEPRINTS` vs `WORKER_BLUEPRINTS`; `app.py:87-104`). A third
mode, `combined`, registers both and is used for ephemeral PR-preview environments.

---

## 2. Input acquisition & normalization

Implemented in `backend/services/care_plan_input.py`, called from both
`routes/trial.py:_resolve_trial_input` and `routes/care_plan_jobs.py:_resolve_input_for_job`.

### 2.1 Accepted input modes

| Mode | Trial | Main app |
|---|---|---|
| Pasted text | yes | yes |
| File upload(s) | yes (≤5 files) | yes (≤10 files) |
| `doc_id` (re-run on a previously uploaded file) | no — trial has no login, so no prior upload to reference | yes |
| GCS batch dataset / Athena live fetch | no | yes (batch-only, out of scope here) |

### 2.2 Accepted file types and size limits

`Constants.Uploads.ALLOWED_EXTENSIONS` (`utils/constants.py:20-22`): `pdf`, `txt`,
`docx`, `html`/`htm`, and images `png`/`jpg`/`jpeg`/`webp`/`heic`.

| Limit | Main app | Trial |
|---|---|---|
| Max files per request | 10 | 5 |
| Max bytes per file | 10 MB | none (`enforce_per_file_limit=False`) |
| Max aggregate bytes | 25 MB | 10 MB |
| Unusable-file handling | first bad file aborts the whole request | bad files are skipped (`tolerate_unusable_files=True`); request only fails if *no* file yields usable content |

The trial's limits are a deliberate, explicit product decision (more permissive per
file, tighter in aggregate) — see `services/care_plan_input.py:229-256`. A Flask-wide
`MAX_CONTENT_LENGTH` of 30 MB (`app.py:45`) is a coarse upstream safety net above both,
so an oversized request is rejected by Werkzeug (as a clean 413 via a registered
`@app.errorhandler(413)`, `app.py:240-252`) before either route's own checks run.

### 2.3 Text extraction by format

`extract_text_from_bytes` (`services/care_plan_input.py:135-216`) dispatches on file
extension:

- **TXT** — decoded as UTF-8 with `errors="replace"`.
- **PDF** — `PyPDF2.PdfReader`, page text concatenated (`utils/pdf.py:20-30`).
  `FileNotDecryptedError` is distinguished from other `PyPdfError` subclasses so a
  password-protected PDF gets its own message rather than being lumped in with a
  corrupt/garbage file.
- **DOCX** — `python-docx`, paragraph text joined with newlines, non-`RuntimeError`
  parse failures reclassified as `FILE_PARSE_FAILED`.
- **HTML/HTM** — `BeautifulSoup` (stdlib `html.parser`): `<script>`/`<style>` removed,
  inline formatting tags (`<b>`, `<span>`, etc.) unwrapped so words don't get spurious
  newlines between them, text taken from `<body>` (or the whole document as fallback).
- **Images** (`png`/`jpg`/`jpeg`/`webp`/`heic`) — routed to `utils/image_ocr.py`
  (§2.4).

Every extractor is wrapped so library-specific exceptions (PyPDF2's `PdfReadError`,
python-docx's zip/XML errors, etc.) are reclassified into a `JunoError` with
`ErrorCode.FILE_PARSE_FAILED` and an actionable message, rather than surfacing as an
uncaught 500.

### 2.4 Image path (Gemini vision OCR)

`utils/image_ocr.py:extract_text_from_image`:

1. The image bytes are decode-verified with `PIL.Image.verify()` first — a corrupt or
   mislabeled file is rejected with `FILE_PARSE_FAILED` before any Vertex AI call is
   spent on it.
2. If the image's longest edge exceeds 2048 px, it is downscaled (best-effort; on any
   decode error during downscaling, the original bytes are sent unchanged).
3. The (possibly downscaled) image bytes plus a fixed instruction prompt
   (`Constants.Llm.IMAGE_OCR_PROMPT`, `utils/constants.py:227-241`) are sent to Gemini
   via `LLMClient.generate_text_from_image` (a single multimodal call: one `Part` built
   from the image bytes + MIME type, plus the text prompt).
4. **What is asked for:** transcribe *all* visible text verbatim — headers, medication
   names/dosages, dates, numbers, line breaks — without summarizing, interpreting, or
   commenting on the image. If no legible text is present, the model is instructed to
   return the exact literal token `NO_TEXT_FOUND` and nothing else.
5. **What is done with the response:** if the response (stripped, case-insensitive)
   equals `NO_TEXT_FOUND`, this is raised as `ErrorCode.EMPTY_DOCUMENT`. Otherwise the
   returned text is treated exactly like text extracted from any other format and
   flows into the same downstream checks.

This call uses the pipeline's "long-form" token budget (`MAX_TOKENS_LONG_FORM` =
65,536, vs. the default 8,192) because a dense scanned page can produce a lot of
transcribed text.

### 2.5 Multiple files → one combined document

`resolve_uploaded_files` (`services/care_plan_input.py:219-388`) iterates the uploaded
files, and for each one that yields usable content:

- Appends its extracted text to a running `combined_text`, prefixed with a
  `--- Source: <filename> ---` separator (`utils/misc.py:source_separator`).
- Adds it to a list of "merge candidates" for the audit-copy PDF: PDF/TXT/image bytes
  are merged as-is (TXT and images are first rendered to PDF pages via `reportlab`);
  DOCX/HTML sources are merged as a rendered PDF page **of their extracted text**, not
  of their original formatting (`text_artifact_filename`, `utils/pdf.py:_txt_to_pdf`,
  `_image_to_pdf`, `merge_pdfs`).

The combined text (not the merged PDF) is what the pipeline actually processes. The
merged PDF (`upload_combined_pdf`, `services/care_plan_input.py:24-39`) is uploaded to
GCS purely as a stored, re-downloadable copy of the original submission — main-app
uploads go to `care_plan/{uid}/inputs/{uuid}.pdf`, trial uploads to a visually distinct
`care_plan_trial/{uid}/inputs/{uuid}.pdf` prefix specifically so a GCS lifecycle rule
can target only trial uploads without touching main-app data. If merging fails for any
reason, the failure is logged and swallowed — the job proceeds on extracted text alone,
with no merged PDF stored.

### 2.6 Empty / illegible document detection

There are three independent layers, because there is no single choke point every input
source passes through:

1. **Per-file** (`resolve_uploaded_files`): after extraction, if the stripped text is
   under `Constants.Uploads.MIN_MEANINGFUL_CONTENT_CHARS` (20 characters), the file is
   rejected with `ErrorCode.EMPTY_DOCUMENT` — this catches a scanned/no-text-layer PDF,
   a blank DOCX/TXT/HTML, etc. Under `tolerate_unusable_files` (trial only), the file is
   skipped instead of aborting the request.
2. **Image-specific**: the `NO_TEXT_FOUND` sentinel check in §2.4, which fires before
   the length check would even see the (very short) sentinel text.
3. **Defensive floor in the worker** (`routes/worker.py:182-192`): after
   `resolve_input_from_job_doc` resolves the final text for *any* source kind
   (including `gcs_batch_dataset` and Athena fetches, which don't go through
   `resolve_uploaded_files` at all), the same 20-character floor is re-checked
   immediately before the pipeline runs. This is the backstop that guarantees no
   source kind can silently reach the LLM pipeline on essentially nothing.

### 2.7 Text normalization for term matching

Separately from extraction, `utils/text_normalization.py:normalize_text` (NFKD-decompose
→ strip non-ASCII marks → lowercase → collapse whitespace) is applied before every
deterministic term/abbreviation lookup in §6, so matching is accent- and
case-insensitive and whitespace-tolerant. This is unrelated to the byte/char length
caps below — it never touches the text actually sent to the LLM steps.

### 2.8 Length caps: characters, bytes, and why both

`validate_extracted_text_length` (`services/care_plan_input.py:91-133`) enforces two
independent caps on every path — pasted text, extracted file text, and re-extracted
`doc_id` text — before any job is created or pipeline step runs:

- **`MAX_TEXT_LENGTH`** = 500,000 Python characters (codepoints).
- **`MAX_TEXT_BYTES`** = 350,000 UTF-8-encoded bytes.

The byte cap exists because Firestore's 1 MiB per-document limit is a *byte* limit, not
a character count: 500,000 characters of CJK text is ~1.5 MB once UTF-8-encoded, well
past the character cap's own limit, silently bypassing it. Both checks must pass. A
related check, `validate_text_storable`, rejects text containing an unpaired UTF-16
surrogate codepoint or an embedded NUL byte — both are valid Python `str` content that
cannot be UTF-8-encoded for a Firestore write, which otherwise surfaces as an uncaught
`UnicodeEncodeError` deep inside job creation.

**Global vs. trial-only, and a real cross-check against the `.dev` planning docs:**
these two caps are enforced on *every* caller — trial and main app alike — via the
shared `validate_extracted_text_length` function, called from both
`routes/trial.py:_resolve_trial_input` and `routes/care_plan_jobs.py:_resolve_input_for_job`.
This contradicts a line in `.dev/trial-simplify/README.md`'s "Locked Decisions" section
("Paste-text cap... No server-side text-length limit exists to mirror it") — that line
was accurate when written, but a same-day edge-case-review pass (referenced in the same
README under "SP6 branch... deep edge-case review") added these server-side caps
afterward, and the Locked Decisions bullet was never updated to reflect it. The code on
this branch does enforce a server-side limit, on both trial and main app. The README's
own "Consolidated Open Questions" / closing section separately flags this as an
unresolved product question: `MAX_TEXT_BYTES` narrows the main app's effective ceiling
from 500,000 characters to ~350,000 bytes for documents that previously fit, and that
narrowing was not an explicit design goal — it's a side effect of a check added for the
trial's Firestore-size safety.

---

## 3. Job creation and async orchestration

### 3.1 Why async

A full pipeline run makes three sequential Gemini calls (steps 3–5) plus term
detection, easily taking longer than a typical HTTP request budget is comfortable
holding open. Both `POST /care_plan/jobs` and `POST /trial/jobs` return `202 {job_id}`
immediately after creating a Firestore job document and enqueuing a Cloud Task; the
actual pipeline execution happens later, in a separate worker request.

### 3.2 The Firestore job document as a state machine

Every job (main app and trial) is one document in the `care_plan_outputs` collection,
typed by `models/job.py:JobDoc`. Firestore wire field names are fixed (frontend and
security-rule dependency) — `JobDoc` uses `extra="ignore"` so unrelated fields written
by other code paths don't break validation.

**Statuses** (`models/api_response.py:StatusEnum`, as actually used for job lifecycle):

```
not_started ──(worker picks up task)──► processing ──► completed
                                              │
                                              └────────► error
```

(`StatusEnum` also defines a `success` member, but that value is used for the generic
`ApiResponse` HTTP envelope status, not for job-doc lifecycle — no job document is ever
written with `status="success"`.)

**Key fields:**

| Field | Meaning |
|---|---|
| `uid`, `created_at`/`updated_at` | ownership and bookkeeping |
| `status`, `stage` (1–5), `started_at`, `completed_at` | lifecycle |
| `output_data` | the completed `CarePlanInternal` envelope (§5), only set on success |
| `error_data` | structured error (§9), only set on failure |
| `input_source_kind` | `text` \| `upload` \| `doc_id` \| `gcs_batch_dataset` \| `athena_encounter` \| `athena_clinical_doc` |
| `input_text`, `input_doc_id`, `input_pdf_gcs_uri` | how to resolve the actual document text |
| `input_version` | pipeline version string, e.g. `"v1-2"` — **hard-coded** for trial jobs (§9's cross-reference), client-settable (defaulting to `"v1-2"`) for main-app jobs via `SingleJobRequest.version` |
| `grading_enabled` | whether to compute readability scores; always `true` for trial, defaults `true` but is client-settable for the main app |
| `is_trial`, `expires_at` | trial-only: marks the doc for the 1-hour TTL and for trial-specific output trimming |
| `skipped_files` | trial-only: filenames tolerated-skipped from a multi-file upload as individually unusable |
| `batch_run_id`, `batch_group_id`, `dataset_*`, `athena_*` | batch/dataset/Athena provenance — out of scope here |

### 3.3 Cloud Tasks handoff

`utils/cloud_tasks.py:enqueue_job` builds an HTTP task targeting
`{WORKER_URL}/internal/jobs/execute/{job_id}`, signed with an OIDC token for
`WORKER_SERVICE_ACCOUNT` whose audience is that exact URL, with a
`dispatch_deadline` of `Constants.Deadlines.JOB_TIMEOUT_SECONDS_SINGLE` (300s) for a
single job or `JOB_TIMEOUT_SECONDS_BATCH` (900s) for a batch item. Trial jobs use a
separate Cloud Tasks queue (`CLOUD_TASKS_QUEUE_TRIAL`) from main-app jobs
(`CLOUD_TASKS_QUEUE`), so trial traffic can't starve main-app job dispatch or vice
versa. `enqueue_job_safe` wraps this so a missing config var or a dispatch failure
returns a clean `INTERNAL_ERROR` response rather than an uncaught exception —
`routes/trial.py` deliberately validates this config *before* writing the job doc, so a
misconfigured queue never orphans a Firestore document with no task behind it (the
main-app route does not have this ordering guarantee).

### 3.4 The worker endpoint

`POST /internal/jobs/execute/<job_id>` (`routes/worker.py:41-319`) is reachable only
via Cloud Tasks:

1. Requires an `X-CloudTasks-QueueName` header (a cheap signal it's coming from Cloud
   Tasks, not a stray public request) — its absence is a 403 with no further work.
2. Verifies the OIDC bearer token Cloud Tasks attached (`verify_oidc_token`,
   `utils/firebase.py:180-238`): signature/issuer/expiry via `google-auth`,
   `email_verified` must be true, the token's `email` must match
   `WORKER_SERVICE_ACCOUNT` if set, and `aud` must equal the exact request URL. This can
   be disabled via `WORKER_VERIFY_OIDC=false` for local/dev use only.
3. Loads the job doc; if it doesn't exist, returns 200 (nothing to do — treated as
   already-handled rather than an error, since a missing doc is not something retrying
   would fix).

### 3.5 Idempotency and the processing lease

Cloud Tasks is at-least-once delivery, so the same task can be redelivered while a
prior attempt is still running or has crashed silently. `routes/worker.py:68-111`
handles this with a lease pattern:

- If `job.status` is already `completed` or `error`, return 200 immediately — the job
  is done, redelivering the task should not re-run anything.
- If `job.status == "processing"` and `started_at` is set, compute how long the prior
  attempt has been running (`now - started_at`). If that's still under the job's own
  internal deadline (`SINGLE_JOB_INTERNAL_DEADLINE_S` = 270s, or
  `BATCH_ITEM_INTERNAL_DEADLINE_S` = 870s for a batch item), the redelivery is treated
  as a no-op and returns 200 without touching the pipeline — this is what prevents a
  redelivered task from re-running (and re-billing) the entire multi-call LLM pipeline
  a second time.
- If the lease has expired (elapsed time exceeds the internal deadline), the prior
  attempt is presumed crashed or killed before reaching a terminal state, and this
  delivery is allowed to run the job fresh, exactly like a first attempt — so a
  transient crash doesn't permanently strand a job in `processing`.

Once past this gate, the worker writes `status="processing", started_at=now, stage=1`
directly via Firestore (`routes/worker.py:116-123`) — this corresponds conceptually to
`Constants.Pipeline.PIPELINE_V1_2_STEPS.READ_NOTE` ("Reading your note"), though there
is no dedicated pipeline code marker for it; it is simply the state the job is in
between being picked up and the term-detection step starting.

A separate `_check_timeout` closure (`routes/worker.py:127-136`) is invoked on every
stage transition during pipeline execution; if the wall-clock time since the worker
started exceeds the internal deadline, the job is failed with `ErrorCode.JOB_TIMEOUT`
at the current stage and the handler returns 200 (Cloud Tasks will not retry a 200).
Genuinely unexpected exceptions (the outer `except Exception` in `execute_job`) return
500 instead, which is the one path where Cloud Tasks' own queue-level retry policy
(not itself part of this codebase) may redeliver — the lease check above is what makes
that safe.

Across a single successful job, the worker writes to Firestore approximately seven
times: job creation, the `processing`/stage-1 transition, one write per stage
transition into steps 2–5 (four writes), and the final `complete_job` write. This is
intentional, not redundant — each stage write is what keeps the client-visible
progress indicator (e.g. "Organizing your care plan") showing as active for the
duration of that step's LLM call.

---

## 4. The pipeline stages

The pipeline itself lives in two layers:

- **`backend/care_plan/v1_2/pipeline.py`** (`CarePlanV1_2Pipeline`) — the pure
  algorithm: what each step computes, in what order, with what fallback behavior on
  failure. No Flask, no Firestore, no tracing.
- **`backend/services/care_plan_pipeline.py`** (`run_care_plan_pipeline`) — the
  adapter that wraps each step with observability (Markers/tracing spans), runs
  grading, and translates the pipeline's own event types into `Adapter*` events the
  worker consumes.

`backend/care_plan/interface.py:CarePlanPipeline` is the abstract base every pipeline
version implements (`run()` for a plain call, `iter_steps()` for step-by-step
progress); `v1-2` is currently the only registered version
(`routes/worker.py:37`: `PIPELINES = {Constants.Pipeline.PIPELINE_VERSION_V1_2: run_care_plan_pipeline}`).

**A naming note, verified against the code, worth being precise about:** the pipeline
*version* string is `"v1-2"` (`Constants.Pipeline.PIPELINE_VERSION_V1_2`,
`utils/constants.py:164`); the care-plan *output schema* version is the distinct string
`"1.2"` (`Constants.Schema.CARE_PLAN_VERSION` / `Constants.Pipeline.CARE_PLAN_VERSIONS.V1_2`,
`utils/constants.py:16,187-188`). They happen to correspond to the same release but are
not the same field or the same value, and both appear in job docs and output.

The five named steps (`Constants.Pipeline.PIPELINE_V1_2_STEPS`,
`utils/constants.py:166-182`) are:

| # | Name | Label shown to user | LLM call? | On failure |
|---|---|---|---|---|
| 1 | `READ_NOTE` | "Reading your note" | no | n/a — not emitted by `iter_steps`; see §3.5 |
| 2 | `DETECT_TERMS` | "Finding difficult and medical terms" | no | non-fatal: falls back to empty term lists |
| 3 | `SIMPLIFY_LANGUAGE` | "Simplifying language" | yes | **fatal**: `PipelineStepError`, pipeline aborts |
| 4 | `CLARIFY_AND_ACTION` | "Clarifying actions and numbers" | yes | non-fatal: falls back to step 3's output |
| 5 | `STRUCTURE_DOCUMENT` | "Organizing your care plan" | yes | **fatal**: `PipelineStepError`, pipeline aborts |

This is the README's rough description ("extract text → detect medical terms →
simplify language → clarify actions → structure output") verified precisely against
`care_plan/v1_2/pipeline.py:158-273`, with one correction: there is no separate
"extract text" pipeline step — text extraction happens entirely in §2, before the
pipeline is ever invoked; the pipeline's first real step is term detection.

### 4.1 Step 2 — `detect_terms` (deterministic, no LLM)

**Input:** the resolved plain text. **What it does:** runs three independent,
dictionary-based lookups (§6) against a normalized copy of the text: AHRQ
plain-language substitution candidates, Michigan medical-dictionary terms to preserve
and define, and local abbreviation expansions. **Output:** a dict with
`substitution_candidates`, `preserve_and_define_terms`, and `abbreviations` lists,
which become inputs to the next two LLM prompts. **Failure mode:** each of the three
lookups is individually wrapped in `try/except`; a failure in one logs and continues
with an empty list for that category rather than aborting — deterministic
dictionary lookups against static, checked-in JSON data are not expected to fail, but
the code treats them as non-critical regardless.

### 4.2 Step 3 — `simplify_language` (LLM)

**Input:** the original text plus the three term-detection lists, formatted into
compact prompt sections (`utils/term_detection.py:format_*_for_prompt`, each capped at
30–60 items to bound prompt size). **Prompt** (`care_plan/v1_2/prompts/simplify_language.txt`):
rewrite the note to roughly a 6th-grade reading level, using the detected
plain-language substitutions where they fit, preserving detected medical terms
verbatim (they're defined separately in the glossary, not inline), expanding detected
abbreviations, using short sentences and active voice and "you"/"your", never adding
diagnosis/advice/urgency not in the source, and never including patient-identifying
details. Output is plain text only, no preamble. **Output:** a plain-text string
(`self._generate_text`, temperature 0.3, the long-form 65,536-token budget since this
rewrites the entire document). **Failure mode:** any exception (LLM error, safety
block, invalid response) is fatal — logged and re-raised as a `PipelineStepError`,
aborting the whole run. There is no partial/fallback simplified text.

### 4.3 Step 4 — `clarify_and_action` (LLM)

**Input:** step 3's simplified text, plus up to 30 detected abbreviations (formatted
as an optional expansion reminder section if any remain unexpanded).
**Prompt** (`care_plan/v1_2/prompts/clarify_and_action.txt`): rewrite in active voice
addressed to "you", start every patient action with a clear verb (Take / Call /
Schedule / Ask / Bring / Watch / Avoid / Continue / Stop), never fabricate numbers or
convert vague wording into an exact number the source doesn't contain, never add
urgency not implied by the source, and break multi-step instructions into separate
steps. **Output:** plain text (temperature 0.2, long-form budget). **Failure mode:**
non-fatal — an exception here is logged and the pipeline falls back to using step 3's
simplified text unchanged for every subsequent stage (structuring, and the "after"
readability score). A user whose document hits this failure gets a completed care
plan that skipped only the action-clarification pass, not an error.

### 4.4 Step 5 — `structure_document` (LLM)

**Input:** step 4's output (or step 3's, if step 4 failed), plus a JSON schema derived
at import time from the `CarePlanV1_2` Pydantic model (with `terms`, `raw`, and `note`
fields excluded — those are populated separately, not by this LLM call).
**Prompt** (`care_plan/v1_2/prompts/structure_note.txt`): return JSON only, matching
the given schema; use only information present in the source text; every medication
needs a `why` explaining the reason *for this patient*; every warning sign needs a
`what_to_do` and an urgency classification (`emergency` / `call_doctor` / `monitor` /
`normal_side_effect`); the summary must be exactly 3 sentences (why came in / main
conclusion / most important next step); exactly 3 patient-facing questions must be
generated; low-priority details go in a separate `low_priority` array; active voice,
"you", no abbreviations, 20 words per sentence max. **Output:** JSON
(`self._generate_json`, temperature 0.2, long-form budget — chosen deliberately because
this is the last LLM step, and hitting the default 8,192-token cap here would mean
every earlier step already ran to completion before the user sees a failure). The
returned dict is validated against `CarePlanV1_2` via Pydantic; a schema mismatch
raises `ErrorCode.PIPELINE_VALIDATION_FAILED`, and a non-dict response raises
`ErrorCode.LLM_INVALID_JSON`. **Failure mode:** fatal — any exception here (LLM error,
JSON parse failure, schema validation failure) aborts the run as a `PipelineStepError`.

### 4.5 Post-processing (no LLM call, not a numbered step)

After step 5 succeeds, `care_plan/v1_2/pipeline.py:242-264` re-runs the Michigan
medical-term detector against the **clarified** text (step 4's output, not the
original) to build the final glossary — this means the glossary only contains terms
that actually survived into the rewritten text, not every term detected in the
original. The structured JSON, the glossary, and the three raw text artifacts
(original, simplified, clarified) are merged into one dict and validated into a
`CarePlanV1_2` model. The `raw` artifacts block is dropped from trial output before
storage (§5).

---

## 5. Output shape

The worker composes a `CarePlanInternal` envelope (`models/care_plan/envelope.py`):
`metrics` (timing/version metadata), `input` (a `TextInput` or `DocIdInput`
discriminated union — never both text and a doc reference), `grading`, and `care_plan`
(the typed `CarePlanV1_2`, or a version-appropriate sibling for a future pipeline
version). `envelope.to_dict()` is what is written to `output_data` on the job doc.

**Trial-only trimming**, applied to `output_data` after serialization, immediately
before `complete_job` (`routes/worker.py:272-297`):

- `care_plan.raw` (the original/simplified/clarified text artifacts) is dropped — the
  trial UI never reads it, and keeping it would double the size of every completed
  trial document unnecessarily.
- `input.text` is dropped from the envelope's serialized copy (the top-level
  `input_text` field on the job doc itself is separately cleared by `complete_job`'s
  `clear_input_text` flag, in the same Firestore update).
- `grading.entries` is filtered down to only the two entries named `"combined"` (one
  `target="before"`, one `target="after"`) — see §7.

None of this trimming touches what is *computed*; it is a storage-side filter applied
after the fact, so main-app jobs (which never set `is_trial`) are byte-for-byte
unaffected.

---

## 6. Medical term detection and the jargon database

`utils/jargon_db.py` loads three static, checked-in JSON files at process start
(`backend/data/jargon/*.json`, cached via `functools.lru_cache`) and builds normalized
lookup tables from them:

- **AHRQ plain-language terms** (`ahrq_plain_language.json`) — jargon → suggested
  plain-language replacement, used as substitution candidates in the simplify prompt.
- **Michigan medical dictionary** (`michigan_medical_dictionary.json`) — terms with
  full definitions (and optional image/alt-text), used both to tell the simplify step
  *not* to rewrite them inline, and to build the final glossary.
- **Local abbreviations** (`abbreviations.json`) — a flat map of abbreviation →
  expansion.

Each source is expanded into alias rows at load time via
`utils/text_normalization.py:term_aliases` (splits comma-separated source entries,
expands parentheticals like `"stroke (CVA)"` into `stroke`, `stroke CVA`, and `CVA`,
and splits slash alternatives like `"pain/discomfort"`) and, for the medical
dictionary, further expanded with conservative English inflections
(`inflected_aliases` — pluralization and simple verb-form generation for plain
alphabetic, non-acronym aliases only, to limit false positives). Rows are sorted
longest-alias-first so a multi-word match (e.g. "shortness of breath") is preferred
over a shorter substring match (e.g. "breath") within the same text.

Matching itself is a normalized substring search with word-boundary anchoring
(`contains_normalized_term`), not an LLM call — this is a fully deterministic step,
which is why its failure mode (§4.1) is "continue with nothing found" rather than
anything more elaborate. Abbreviation matching additionally tolerates dotted and
undotted spellings of the same acronym (`a.b.c.` / `a.b.c` / `abc`) via a generated
regex per abbreviation.

The final glossary shape written to output (`build_terms_glossary`,
`jargon_db.py:279-294`) is a dict keyed by the term's display string, each value
`{definition, source, imgUrl, altText}` — built only from terms that survive
re-detection against the clarified text (§4.5), so it reflects what's actually in the
patient-facing document, not everything found in the original.

---

## 7. Scoring / grading

`grading_enabled` gates whether readability scores are computed at all; it is always
`true` for trial jobs and defaults `true` (but is client-settable) for the main app.

### 7.1 The composite 0–100 score

`utils/scoring.py:score_text` computes seven weighted dimension scores from a piece of
text, using only automatable, no-LLM signals:

| Dimension | Weight | What it measures |
|---|---|---|
| Grade level | 0.25 | Consensus of SMOG (if ≥30 sentences), Flesch-Kincaid, and an approximate Dale-Chall grade |
| Jargon density | 0.20 | `textstat` difficult-word ratio |
| Sentence complexity | 0.15 | Average words per sentence |
| Passive voice | 0.10 | Passive-construction ratio (spaCy `en_core_sci_sm` dependency parse if available, else a regex heuristic) |
| Actionability | 0.10 | "you"/"your" rate, imperative-sentence rate, bullet presence |
| Numeracy clarity | 0.10 | Count of vague quantifiers ("some", "several", etc.) and raw unlabeled fractions |
| Structural clarity | 0.10 | Average words per paragraph, with a bonus for bulleted/numbered structure |

Each dimension is normalized to 0–100 by its own linear mapping (e.g. grade 4 → 100,
grade 16 → 0), then combined by the weights above and rounded to an integer
**composite** score, labeled `"Patient-friendly"` (≥70), `"Moderate"` (≥40), or
`"Hard to read"` (below). A `low_confidence: true` flag is added when the sample is
under 30 words or 3 sentences — the sub-scores are still returned, just flagged as
less reliable on a short sample.

### 7.2 Before / after

`services/care_plan_pipeline.py:run_care_plan_pipeline` computes:

- **`before`** — from the raw input text, as submitted (before any pipeline step runs).
- **`after`** — from `event.clarified`, i.e. **step 4's output** (clarify_and_action),
  not the final structured JSON from step 5. This is a specific, verifiable detail: the
  readability score reflects the plain-language prose the pipeline produced, not the
  medications/warnings/etc. list structure that step 5 derives from it.

As an optimization (not a behavior change), the `before` score is computed on a
background thread (`ThreadPoolExecutor(max_workers=1)`) started at the very top of
`run_care_plan_pipeline`, since it only depends on the already-available input text —
it overlaps with the three sequential Vertex AI calls in steps 3–5 instead of running
serially after them. `score_text_safe` never raises (it wraps `score_text` and returns
`None` on any failure), so this introduces no new exception path across the thread
boundary; the executor is joined via `.shutdown(wait=True)` in a `finally` block on
every exit path, including early pipeline failure.

### 7.3 `scoring_methods.py` — the six named methods

In addition to the composite score, `build_grading_with_before_after_score`
(`models/grading.py:28-68`) computes six separate named method scores per target
(before/after), each an approximation of a published health-literacy instrument built
from the same underlying dimension scores, not a re-implementation of the original
instrument:

- **SMOG** — direct `textstat.smog_index`, `insufficient_sample=True` if under 30
  sentences (real SMOG requires 30).
- **Flesch-Kincaid** — `textstat`'s reading ease and grade level directly.
- **Dale-Chall** — `textstat`'s raw score, mapped to an approximate grade range label.
- **PEMAT** — a weighted blend of jargon density, sentence complexity, passive voice,
  numeracy, and structural clarity for "understandability", averaged with the
  actionability dimension for the combined score. This approximates PEMAT items 3, 8,
  14, 21–22, 9–12 (understandability) and 27–33 (actionability); it is not the real
  PEMAT instrument, which requires a trained human rater.
- **SAM** — an approximation of the automatable SAM domains (content, literacy demand,
  layout/typography) from the same dimension scores.
- **CDC CCI** — four pass/fail checks (main message, behavioral recommendations,
  numbers, call to action) derived from thresholds on actionability/numeracy.

Each of these plus the composite produces one `GradingEntry` per target, for 7 × 2 = 14
entries total per graded job (`models/grading.py:34-63`).

### 7.4 Trial-specific trimming to `combined`-only

The trial UI (`ResultScreen.tsx`, per the code comment at `routes/worker.py:283-288`)
only ever reads the two `combined` entries (before/after composite). Rather than
change what's computed — `models/grading.py` and the scoring pipeline are shared
verbatim with the main app's own per-method grading UI (`routes/grading.py`) — the
worker filters `output_data["grading"]["entries"]` down to `name == "combined"` only,
storage-side, for trial jobs (`routes/worker.py:289-296`). This is a deliberate,
documented trade-off (`.dev/trial-simplify/06-trial-optimizations/PRD.md §4.1/§4.4`):
computing all 14 entries costs at most tens of milliseconds of CPU, so skipping the
computation itself was judged not worth touching shared grading code for; the ~38%
payload reduction from *not storing* the other 12 entries was judged worth a small,
narrowly-scoped filter. Main-app jobs are untouched — the filter only runs inside the
`if is_trial:` branch.

---

## 8. Observability

Every pipeline run carries three correlation IDs — `trace_id` (one HTTP request),
`span_id` (one operation within a request), and `session_id` (an application-level ID
spanning multiple requests in one user session, set from the `X-Session-Id` header or
generated). Pipeline steps 3–5 (the LLM calls) and the term-detection step are wrapped
in named "code markers" (`utils/markers`) that emit timing and success/failure metrics
under names like `care_plan.simplify_language`, `care_plan.clarify_actions`,
`care_plan.structure_note`, `care_plan.find_medical_terms`, and `care_plan.pipeline`
for the run as a whole (`services/care_plan_pipeline.py:60-65,127`); simplify_language
and clarify_actions additionally get manual OpenTelemetry spans
(`care_plan.simplify_language`, `care_plan.clarify_actions`) with `session.id`
attached. Grading gets its own marker (`grading.run`), and the worker's dispatch and
per-stage Firestore writes get `worker.job_execute` / `worker.job_stage`.

The full field reference, query recipes, and how to add a new marker live in
`docs/logging.md` — that document is the source of truth for observability and is not
duplicated here.

---

## 9. Error taxonomy

All backend errors funnel through `backend/errors/` (`errors/codes.py` for the pure
data — every `ErrorCode` plus its `ErrorInfo` metadata — and `errors/exceptions.py` for
the logic: `JunoError`, classifiers, and response builders).

**Categories** (`errors/codes.py`): LLM generation failures (mapped 1:1 from Vertex AI
`FinishReason` values — `LLM_MAX_TOKENS`, `LLM_SAFETY_BLOCKED`, `LLM_INVALID_JSON`,
etc.), Vertex AI API-level errors (`VERTEX_QUOTA_EXCEEDED`, `VERTEX_DEADLINE_EXCEEDED`,
etc., mapped from `google.api_core.exceptions`), pipeline/processing errors
(`FILE_PARSE_FAILED`, `EMPTY_DOCUMENT`, `PIPELINE_VALIDATION_FAILED`, `JOB_TIMEOUT`),
auth, resource, input-validation, batch, grading/saving, a system catch-all
(`UNKNOWN_ERROR`, `INTERNAL_ERROR`), Athena, and rate limiting.

**What's user-visible vs. internal:** every `ErrorInfo` carries both a `message`
(developer-facing, technical) and a `user_hint` (plain-English, safe to show a
non-technical patient-adjacent user), plus `retryable` (whether retrying the same
request is likely to help) and an HTTP status. `make_error_response` builds the public
`ApiResponse` shape (`{status, error: {code, message, user_hint, retryable, details,
timestamp, path}, requestId}`) for HTTP routes. `build_error_data`/
`build_error_data_from_exc` build the equivalent dict for a Firestore job's
`error_data` field, which the frontend reads via its live listener rather than an HTTP
response.

**A specific, deliberate leak-prevention detail:** `build_error_data_from_exc`
(`errors/exceptions.py:182-205`) strips the `detail` string for anything that
classifies as `UNKNOWN_ERROR` — the one branch where the underlying exception's own
message was never written or curated by this codebase, and so isn't guaranteed safe to
show a public client (some exception types, e.g. certain Pydantic validation errors,
embed the actual invalid value in their message). A `JunoError`'s own `detail` string
*is* shown, because it was written by our code specifically to be shown. The full
exception is still captured server-side via `logger.exception` regardless.

`JunoError` (`errors/exceptions.py:50-70`) is the structured exception type raised
throughout the pipeline and input-handling code — it carries an `ErrorCode`, an
optional `detail` string, and the original exception (if any) for logging. Anything
that isn't a `JunoError` or a recognized `google.api_core.exceptions.GoogleAPICallError`
classifies as `UNKNOWN_ERROR`.

---

## 10. Known limits and sharp edges

Sourced from the edge-case review
(`.dev/trial-simplify/edge-case-review-backend-2026-09-05.md`) and the test suite; all
of the following are either fixed-and-tested on this branch, or explicitly deferred and
called out as such.

- **Rate limiting is a fixed wall-clock-hour window, not sliding** (`utils/rate_limit.py:166-178`,
  documented in its own docstring as a known, accepted limitation). An IP sending 5
  requests just before the top of the hour and 5 more just after can get 10 through
  within seconds of the boundary.
- **The trial's rate limiter fails open**: a transient Firestore error during the rate
  check is caught and the request is allowed through (`utils/rate_limit.py:194-210`) —
  a deliberate availability-over-strict-enforcement choice for an abuse guard on a free
  feature, not a security boundary.
- **`X-Forwarded-For` trust assumes exactly one trusted proxy hop** (`utils/rate_limit.py:30-69`),
  correct for this deployment's current direct-Cloud-Run topology with no external load
  balancer in front of it. This is `TRIAL_TRUSTED_PROXY_HOPS`-overridable, but would
  need to change if that topology ever changes (documented open item, deferred by
  design in `.dev/trial-simplify/README.md`'s Consolidated Open Questions).
- **The `MAX_TEXT_BYTES` cap narrows the main app's effective text ceiling** as a side
  effect (§2.8) — flagged in the planning docs as an unresolved product question, not
  fixed on this branch.
- **A merged-PDF failure is silent** (`services/care_plan_input.py:368-373`): if
  `merge_pdfs` raises for any reason, the exception is logged and the job proceeds with
  `combined_pdf_bytes=None` — no audit copy of the original upload is stored, but the
  user sees no error, since the extracted text (what the pipeline actually needs) is
  unaffected.
- **`clarify_and_action` failing degrades silently, not visibly**: per §4.3, if step 4
  fails, the completed care plan is built from step 3's simplified-but-not-yet-clarified
  text with no indication to the user that this fallback occurred.
- **Deterministic term detection can miss or over-match**: the AHRQ/Michigan/abbreviation
  lookups are substring matches over a fixed, checked-in dictionary — a term not in the
  dictionary is never flagged for preservation/definition, and inflection generation
  (`inflected_aliases`) is a conservative heuristic, not a real morphological analyzer,
  so unusual word forms can be missed.
- **Glossary re-detection uses the clarified text, not the original** (§4.5) — by
  design, but it means a term detected in the source document that the LLM rewrote away
  entirely will not appear in the final glossary even though it was in the original
  note.
- **Retention automation for the trial (Firestore native TTL, the anonymous-user
  cleanup Cloud Run Job) is described in the planning docs as not yet deployed as of
  the last recorded status in `.dev/trial-simplify/README.md`** — the GCS lifecycle
  rule half is recorded as done, but the Firestore TTL and Cloud Scheduler pieces are
  recorded as outstanding, owner-only infrastructure steps. This document cannot verify
  live infrastructure state from the code alone; treat the `.dev/` README as the source
  of truth for what has actually been deployed, and confirm current status
  independently before relying on it.
- **Legal-copy review is explicitly called out in the planning docs as the one item
  gating trial launch** — unrelated to the pipeline itself, noted here only because it
  appears in the same planning documents this review consulted.
