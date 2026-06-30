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
        ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "txt", "docx", "html", "htm"})
        MAX_FILE_BYTES: int = 10 * 1024 * 1024
        MAX_FILE_COUNT: int = 10
        MAX_AGGREGATE_FILE_BYTES: int = 25 * 1024 * 1024
        UPLOAD_PREFIX: str = "care_plan-uploads"

    class Pipeline:
        PIPELINE_VERSION_V1_2: str = "v1-2"
        STEPS: dict[int, str] = {
            1: "Reading your note",
            2: "Finding difficult and medical terms",
            3: "Simplifying language",
            4: "Clarifying actions and numbers",
            5: "Organizing your care plan",
        }
        RESULT_SENTINEL: str = "__result__"

        class CARE_PLAN_VERSIONS(Enum):
            V1_2 = "1.2"

    class Batch:
        MAX_BATCH_RUNS: int = 50

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

    class Athena:
        BASE_URL: str = "https://api.preview.platform.athenahealth.com"
        PRACTICE_ID: str = "195900"
        OAUTH_SCOPE: str = "athena/service/Athenanet.MDP.*"
        BATCH_SIZE: int = 2
        BATCH_SLEEP_S: int = 30
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


# ---------------------------------------------------------------------------
# Backward-compat flat shims — kept for callsites not yet migrated.
# TODO(SP03+): remove each shim once its consumer migrates to Constants.<Namespace>.<NAME>.
# ---------------------------------------------------------------------------
Constants.RESULT_SENTINEL               = Constants.Pipeline.RESULT_SENTINEL
Constants.MAX_BATCH_RUNS               = Constants.Batch.MAX_BATCH_RUNS
Constants.ALLOWED_EXTENSIONS           = Constants.Uploads.ALLOWED_EXTENSIONS
Constants.MAX_FILE_BYTES               = Constants.Uploads.MAX_FILE_BYTES
Constants.MAX_FILE_COUNT               = Constants.Uploads.MAX_FILE_COUNT
Constants.MAX_AGGREGATE_FILE_BYTES     = Constants.Uploads.MAX_AGGREGATE_FILE_BYTES
Constants.PIPELINE_VERSION_V1_2        = Constants.Pipeline.PIPELINE_VERSION_V1_2
Constants.STEPS                        = Constants.Pipeline.STEPS
Constants.CARE_PLAN_VERSIONS           = Constants.Pipeline.CARE_PLAN_VERSIONS
Constants.GRADING_METHODS              = Constants.Grading.GRADING_METHODS
Constants.SOURCE                       = Constants.Enums.SOURCE
Constants.IMPORTANCE                   = Constants.Enums.IMPORTANCE
Constants.ATHENA_BASE_URL              = Constants.Athena.BASE_URL
Constants.ATHENA_PRACTICE_ID           = Constants.Athena.PRACTICE_ID
Constants.GCS_BUCKET_ENV_VAR           = Constants.Storage.GCS_BUCKET_ENV_VAR
Constants.DATASETS_BUCKET_NAME_ENV_VAR = Constants.EnvVars.DATASETS_BUCKET
Constants.DATASETS_BUCKET_ENV_VAR      = Constants.EnvVars.DATASETS_BUCKET
Constants.DATASETS_BUCKET_NAME_DEFAULT = Constants.EnvVars.DATASETS_BUCKET_DEFAULT
Constants.CARE_PLAN_DEFAULT_VERSION_ENV_VAR     = Constants.EnvVars.CARE_PLAN_DEFAULT_VERSION
Constants.CARE_PLAN_DEFAULT_VERSION_FALLBACK    = Constants.EnvVars.CARE_PLAN_DEFAULT_VERSION_FALLBACK
Constants.ATHENA_CLIENT_ID_ENV_VAR     = Constants.EnvVars.ATHENA_CLIENT_ID
Constants.ATHENA_CLIENT_SECRET_ENV_VAR = Constants.EnvVars.ATHENA_CLIENT_SECRET
