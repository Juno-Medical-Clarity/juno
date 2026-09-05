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
        RATE_LIMIT_PER_IP_PER_HOUR: int = 5
        RATE_LIMIT_COLLECTION: str = "trial_rate_limits"
        RATE_LIMIT_COUNTER_TTL_HOURS: int = 2
        JOB_TTL_HOURS: int = 1

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
