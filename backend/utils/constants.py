from enum import Enum, StrEnum


class _GradingMethodBase:
    def __init__(self, value: str, description: str):
        self.value = value
        self.description = description


class Constants:

    class Schema:
        SUMMARY_SCHEMA_VERSION_1_2: str = "1.2"
        INPUT_VERSION: str = "1.0"
        GRADING_VERSION: str = "1.0"
        CARE_PLAN_VERSION: str = "1.2"

    class Uploads:
        IMAGE_EXTENSIONS: frozenset[str] = frozenset({"png", "jpg", "jpeg", "webp", "heic"})
        ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
            {"pdf", "txt", "docx", "html", "htm"} | IMAGE_EXTENSIONS
        )
        MAX_FILE_BYTES: int = 10 * 1024 * 1024        # unchanged, PRD §4.7
        MAX_FILE_COUNT: int = 10                       # unchanged
        MAX_AGGREGATE_FILE_BYTES: int = 25 * 1024 * 1024
        UPLOAD_PREFIX: str = "care_plan-uploads"
        MAX_TEXT_LENGTH: int = 500_000                 # Upper bound on extracted/pasted
                                                        # document text, enforced up front
                                                        # (before any job is enqueued or
                                                        # pipeline step runs) in
                                                        # _resolve_trial_input,
                                                        # _resolve_input_for_job, and
                                                        # services.care_plan_input. Not
                                                        # meant to be a practical limit on
                                                        # real clinical documents -- an
                                                        # ordinary multi-page note is a few
                                                        # thousand characters, and even a
                                                        # very long chart is well under
                                                        # 100K. 500K characters (~125K
                                                        # tokens at ~4 chars/token) covers
                                                        # roughly 150+ pages of dense text
                                                        # while leaving enormous headroom
                                                        # inside gemini-3.5-flash's ~1M-token
                                                        # input context; it exists only to
                                                        # fail fast on a pathological input
                                                        # (e.g. megabytes of pasted raw
                                                        # data) rather than to constrain
                                                        # legitimate documents. The actual
                                                        # ceiling for pipeline output is
                                                        # Llm.MAX_TOKENS_LONG_FORM, not this.

        MAX_TEXT_BYTES: int = 350_000                  # UTF-8-ENCODED BYTE budget, enforced
                                                        # ALONGSIDE (not instead of) the char-
                                                        # based MAX_TEXT_LENGTH above, via
                                                        # `len(text.encode("utf-8"))` in
                                                        # validate_extracted_text_length. Exists
                                                        # because MAX_TEXT_LENGTH alone doesn't
                                                        # bound Firestore's 1,048,576-byte
                                                        # (1 MiB) per-document hard limit:
                                                        # Firestore/gRPC measures document size
                                                        # in UTF-8-encoded bytes, but
                                                        # `len(text)` counts codepoints, so
                                                        # non-ASCII text passes the char check
                                                        # while still being oversized in bytes
                                                        # -- 500,000 chars of CJK is ~1.5 MB in
                                                        # UTF-8 (3 bytes/char), emoji/
                                                        # supplementary-plane text ~2 MB (4
                                                        # bytes/char). Both previously produced
                                                        # an uncaught Firestore write failure
                                                        # (500) instead of a clean 400 (verified
                                                        # empirically; see .dev/trial-simplify/
                                                        # edge-case-review-backend-2026-09-05.md
                                                        # Finding 1).
                                                        #
                                                        # Sized against the FULL completed
                                                        # care_plan_outputs doc, not just
                                                        # input_text, per that same review:
                                                        #   1,048,576 B  hard Firestore doc limit
                                                        #   -   ~2,000 B  job metadata (uid,
                                                        #                 timestamps, status,
                                                        #                 filenames, flags, etc.
                                                        #                 -- all small scalars)
                                                        #   - ~150,000 B  output_data reserve:
                                                        #                 for TRIAL jobs (the
                                                        #                 only ones where
                                                        #                 input_text and
                                                        #                 output_data can appear
                                                        #                 in the doc together --
                                                        #                 see complete_job's
                                                        #                 clear_input_text
                                                        #                 param), output_data
                                                        #                 has already had
                                                        #                 care_plan.raw,
                                                        #                 input.text, and all
                                                        #                 non-"combined" grading
                                                        #                 entries stripped (see
                                                        #                 routes/worker.py's
                                                        #                 is_trial branch); what
                                                        #                 remains is the
                                                        #                 structured care_plan
                                                        #                 (medications/tests/
                                                        #                 procedures/warning_
                                                        #                 signs/terms/etc.,
                                                        #                 fixed-shape items each
                                                        #                 a few hundred bytes)
                                                        #                 plus 2 grading entries
                                                        #                 and metrics -- 150 KB
                                                        #                 is a generous multiple
                                                        #                 of even a dense real
                                                        #                 visit's structured
                                                        #                 output (consistent
                                                        #                 with this file's own
                                                        #                 note above that even a
                                                        #                 "very long chart" is
                                                        #                 well under 100K chars)
                                                        #   = ~896,576 B  bytes actually
                                                        #                 available for
                                                        #                 input_text alone
                                                        # 350,000 B leaves >2.5x that computed
                                                        # margin unused (~546 KB spare) as a
                                                        # deliberate additional safety buffer --
                                                        # e.g. if the input_text-clearing fix
                                                        # (complete_job/fail_job's
                                                        # clear_input_text) were ever skipped or
                                                        # raced, a 350,000-byte input_text
                                                        # co-existing with a full 150 KB
                                                        # output_data reserve would still fit
                                                        # comfortably under the 1 MiB ceiling.
                                                        # Also comfortably covers every
                                                        # legitimate document per this file's
                                                        # MAX_TEXT_LENGTH note (350,000 bytes is
                                                        # ~116,000 CJK characters or ~350,000
                                                        # ASCII characters -- either far exceeds
                                                        # "even a very long chart").

        MIN_MEANINGFUL_CONTENT_CHARS: int = 20         # Minimum stripped-text length (chars)
                                                        # for a single extracted file, or the
                                                        # final combined document, to count as
                                                        # "real content" rather than noise or
                                                        # separator scaffolding. Applied at
                                                        # services.care_plan_input.
                                                        # resolve_uploaded_files (per file) and
                                                        # again defensively in routes/worker.py
                                                        # (on the fully-resolved text, whichever
                                                        # source_kind produced it) before any
                                                        # pipeline/LLM step runs. Chosen well
                                                        # below any realistic clinical note --
                                                        # even a terse "Take Tylenol 500mg BID"
                                                        # is >20 chars -- but well above what a
                                                        # scanned/no-text-layer PDF, a blank
                                                        # docx/txt/html, or stray OCR noise on a
                                                        # truly blank image produces (0, or a
                                                        # handful of characters at most).
                                                        # Without this floor, such inputs were
                                                        # silently treated as valid, non-empty
                                                        # documents and the full 5-stage LLM
                                                        # pipeline would run on essentially
                                                        # nothing, very plausibly returning a
                                                        # fabricated "completed" care plan
                                                        # instead of failing with EMPTY_DOCUMENT
                                                        # (see edge-case review Finding 2).

    class Pipeline:
        PIPELINE_VERSION_V1_2: str = "v1-2"

        class PIPELINE_V1_2_STEPS(Enum):
            """Named steps of the v1_2 care-plan pipeline. Each member carries its
            1-based step number (`.number`) and its user-facing progress label
            (`.label`); replaces the old bare `dict[int, str]` so call sites
            reference named members instead of int literals."""
            READ_NOTE          = (1, "Reading your note")
            DETECT_TERMS       = (2, "Finding difficult and medical terms")
            SIMPLIFY_LANGUAGE  = (3, "Simplifying language")
            CLARIFY_AND_ACTION = (4, "Clarifying actions and numbers")
            STRUCTURE_DOCUMENT = (5, "Organizing your care plan")

            def __new__(cls, number: int, label: str):
                obj = object.__new__(cls)
                obj._value_ = number
                obj.number = number
                obj.label = label
                return obj

        # ── SSE stream result sentinel ───────────────────────────────────
        RESULT_SENTINEL: str = "__result__"

        class CARE_PLAN_VERSIONS(Enum):
            V1_2 = "1.2"

    class Batch:
        MAX_BATCH_RUNS: int = 50

    class Trial:
        MAX_FILE_COUNT: int = 5
        # Trial-only aggregate upload cap: 5 files / 10 MB combined / NO per-file
        # cap (an explicit product decision -- deliberately more permissive per
        # file, tighter in aggregate, than the main app's Constants.Uploads
        # limits, which are unchanged by this). Mirrors
        # frontend-trial/src/utils/validateFiles.ts's MAX_AGGREGATE_BYTES --
        # keep these two values in sync.
        MAX_AGGREGATE_FILE_BYTES: int = 10 * 1024 * 1024
        RATE_LIMIT_PER_IP_PER_HOUR: int = 5
        RATE_LIMIT_COLLECTION: str = "trial_rate_limits"
        RATE_LIMIT_COUNTER_TTL_HOURS: int = 2
        JOB_TTL_HOURS: int = 1
        # Number of trusted reverse-proxy hops between the public internet and
        # this container -- i.e. how many IPs are Google-appended to the RIGHT
        # end of X-Forwarded-For before the request reaches Flask. See the
        # topology note on utils.rate_limit.get_client_ip for why this is 1
        # today (direct Cloud Run, no external Load Balancer) and when it
        # would need to change. Overridable via TRIAL_TRUSTED_PROXY_HOPS so a
        # future topology change doesn't require a code change.
        TRUSTED_PROXY_HOPS: int = 1

    class Deadlines:
        SINGLE_JOB_INTERNAL_DEADLINE_S: int = 270
        BATCH_ITEM_INTERNAL_DEADLINE_S: int = 870
        JOB_TIMEOUT_SECONDS_SINGLE: int = 300
        JOB_TIMEOUT_SECONDS_BATCH: int = 900

    class Llm:
        MODEL_DEFAULT: str = "gemini-1.5-pro"
        MAX_TOKENS: int = 8192
        MAX_TOKENS_LONG_FORM: int = 65536
        TEMPERATURE_TEXT: float = 0.3
        TEMPERATURE_JSON: float = 0.2
        IMAGE_OCR_PROMPT: str = (
            "You are extracting clinical text from a photographed or scanned medical "
            "document image.\n\n"
            "Transcribe ALL visible text from the image exactly as written, preserving:\n"
            "- Section headers and structure, as plain text (no markdown, no HTML)\n"
            "- Medication names, dosages, frequencies, and instructions verbatim\n"
            "- Dates, numbers, units, and clinician/patient names exactly as they appear\n"
            "- Line breaks between distinct sections, list items, or table rows\n\n"
            "Do not summarize, interpret, correct, or add any text that is not visibly "
            "present in the image. Do not describe the image (for example, never write "
            "\"this is a photo of...\"). Output ONLY the transcribed text.\n\n"
            "If the image contains no legible text at all (blank, illegibly blurry, or a "
            "non-document photo), respond with exactly this token and nothing else:\n"
            "NO_TEXT_FOUND"
        )

    class Athena:
        BASE_URL: str = "https://api.preview.platform.athenahealth.com"
        PRACTICE_ID: str = "195900"
        OAUTH_SCOPE: str = "athena/service/Athenanet.MDP.*"
        TOKEN_TTL_S: int = 300
        TOKEN_REFRESH_BUFFER_S: int = 20
        HTTP_TIMEOUT_TOKEN_S: int = 30
        HTTP_TIMEOUT_GET_S: int = 60
        MAX_RETRIES: int = 3

        class AthenaSourceKind(StrEnum):
            ATHENA_ENCOUNTER    = "athena_encounter"
            ATHENA_CLINICAL_DOC = "athena_clinical_doc"
            GCS_BATCH_DATASET   = "gcs_batch_dataset"
            UPLOAD              = "upload"
            TEXT                = "text"
            DOC_ID              = "doc_id"
            BATCH_DATASET       = "batch_dataset"   # legacy

    class ClinicianDataset:
        """Config for the Clinician Dataset feature (NPI Registry + CMS mj5m-pzi6)."""

        # The exact 17-column output schema (order + spelling are load-bearing).
        COLUMNS: list[str] = [
            "NPI", "Type", "Name", "Speciality", "Address", "City", "State",
            "Zip", "Website", "Phone #", "Email", "Creds", "Why Pilot", "EHR",
            "Outreach status", "Contact date", "Notes",
        ]

        # Columns that never carry source data — always emitted as "".
        BLANK_COLUMNS: frozenset[str] = frozenset({
            "Website", "Email", "Why Pilot", "EHR", "Outreach status",
            "Contact date", "Notes",
        })

        # US states + DC + territories (reused by both datasets' dropdowns).
        US_STATE_CODES: frozenset[str] = frozenset({
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI",
            "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI",
            "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC",
            "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT",
            "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR", "VI", "GU", "AS",
            "MP",
        })

        class Npi:
            """NPPES NPI Registry official API (public, no auth)."""
            BASE_URL: str = "https://npiregistry.cms.hhs.gov/api/"
            VERSION: str = "2.1"
            HTTP_TIMEOUT_S: int = 30
            MAX_RETRIES: int = 3
            RETRY_BACKOFF_S: float = 1.0
            DEFAULT_LIMIT: int = 200
            MAX_LIMIT: int = 200
            DEFAULT_SKIP: int = 0
            MAX_SKIP: int = 1000

        class Cms:
            """CMS 'Doctors and Clinicians' datastore query API (public, no auth)."""
            # Trailing /0 (distribution index) is REQUIRED — dataset-id-only 404s.
            BASE_URL: str = "https://data.cms.gov/provider-data/api/1/datastore/query/mj5m-pzi6/0"
            HTTP_TIMEOUT_S: int = 60
            MAX_RETRIES: int = 3
            RETRY_BACKOFF_S: float = 1.0
            DEFAULT_LIMIT: int = 500
            MAX_LIMIT: int = 1500
            DEFAULT_OFFSET: int = 0

    class Storage:
        GCS_BUCKET_ENV_VAR: str = "GCP_BUCKET_NAME"
        GCS_PRESET_PREFIX: str = "preset-data"
        TEMP_BASE: str = "/tmp/juno-datasets"
        SIGNED_URL_TTL_MIN: int = 30
        GCP_LOCATION_DEFAULT: str = "us-central1"
        FIRESTORE_DATABASE_ID_DEFAULT: str = "(default)"

    class Grading:
        class GRADING_METHODS(Enum):
            SMOG           = _GradingMethodBase("SMOG", "SMOG (McLaughlin 1969) — counts polysyllabic words; designed for health materials")
            FLESCH_KINCAID = _GradingMethodBase("Flesch-Kincaid", "Flesch-Kincaid Reading Ease + Grade Level (1975) — sentence length × syllable load")
            DALE_CHALL     = _GradingMethodBase("Dale-Chall", "Dale-Chall (1948/1995) — difficult words outside the 3,000 familiar-word list")
            PEMAT          = _GradingMethodBase("PEMAT", "PEMAT (AHRQ 2013) — automated approximation of items 3,8,14,21-22 (understandability) and 27-33 (actionability)")
            SAM            = _GradingMethodBase("SAM", "SAM (Doak et al. 1996) — automated approximation of content, literacy demand, and layout/typography domains")
            CDC_CCI        = _GradingMethodBase("CDC CCI", "CDC Clear Communication Index — automated approximation of main message, behavioral recommendations, numbers, and call-to-action items")

    class Enums:
        class SOURCE(Enum):
            DOCUMENTS = "documents"
            RECORDING = "recording"
            NOTES     = "notes"

        class IMPORTANCE(Enum):
            HIGH = "high"
            LOW  = "low"

    class EnvVars:
        GCS_BUCKET: str = "GCP_BUCKET_NAME"
        GCP_PROJECT_ID: str = "GCP_PROJECT_ID"
        GCP_LOCATION: str = "GCP_LOCATION"
        VERTEX_AI_MODEL: str = "VERTEX_AI_MODEL"
        FIRESTORE_DATABASE_ID: str = "FIRESTORE_DATABASE_ID"
        DATASETS_BUCKET: str = "DATASETS_BUCKET_NAME"
        DATASETS_BUCKET_DEFAULT: str = "juno-preset-data"
        CARE_PLAN_DEFAULT_VERSION: str = "CARE_PLAN_DEFAULT_VERSION"
        CARE_PLAN_DEFAULT_VERSION_FALLBACK: str = "v1-2"
        ATHENA_CLIENT_ID: str = "ATHENA_HEALTH_TEST_CLIENT_ID"
        ATHENA_CLIENT_SECRET: str = "ATHENA_HEALTH_TEST_CLIENT_SECRET"
        K_SERVICE: str = "K_SERVICE"
        SERVICE_VERSION: str = "SERVICE_VERSION"
        WORKER_VERIFY_OIDC: str = "WORKER_VERIFY_OIDC"
        WORKER_SERVICE_ACCOUNT: str = "WORKER_SERVICE_ACCOUNT"
        CLOUD_TASKS_QUEUE: str = "CLOUD_TASKS_QUEUE"
        WORKER_URL: str = "WORKER_URL"
        PORT: str = "PORT"
        FLASK_ENV: str = "FLASK_ENV"
        JUNO_MODE: str = "JUNO_MODE"
        TRIAL_TRUSTED_PROXY_HOPS: str = "TRIAL_TRUSTED_PROXY_HOPS"

    class Observability:
        SERVICE_NAME_DEFAULT: str = "backend-processing"
        LOG_EXTRA_KEYS: list[str] = [
            "user_id", "function", "care_plan_version", "grading_version", "input_version",
            "operation", "metric", "metric_type", "duration_ms", "success", "outcome",
            "step_name", "status", "http_method", "http_path", "http_status",
            "http_status_code", "total_duration_ms", "saved_id", "input_chars",
            "error", "labels", "duration_ms_observed", "OpOutcome",
            "service", "environment",
        ]
        DIM_OUTCOME: str = "OpOutcome"
        DIM_STATUS_CODE: str = "StatusCode"
        DIM_CORRELATION_ID: str = "CorrelationId"
