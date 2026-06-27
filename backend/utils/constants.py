from enum import Enum


class _grading_method_base():
    def __init__(self, value: str, description: str):
        self.value = value
        self.description = description


class Constants:
    # ── Summary schema versions (pre-existing) ───────────────────────────
    SUMMARY_SCHEMA_VERSION_1_2 = "1.2"
    SUMMARY_SCHEMA_VERSION_1_3 = "1.3"
    SUMMARY_SCHEMA_VERSION_1_4 = "1.4"

    # ── File upload limits ────────────────────────────────────────────────
    ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "txt", "docx", "html", "htm"})
    MAX_FILE_BYTES: int = 10 * 1024 * 1024       # 10 MB per file
    MAX_FILE_COUNT: int = 10
    MAX_AGGREGATE_FILE_BYTES: int = 25 * 1024 * 1024  # 25 MB combined

    # ── GCS / Cloud config ────────────────────────────────────────────────
    GCS_BUCKET_ENV_VAR: str = "GCP_BUCKET_NAME"

    # ── Dataset GCS config ─────────────────────────────────────────────────────
    DATASETS_BUCKET_NAME_ENV_VAR: str = "DATASETS_BUCKET_NAME"
    DATASETS_BUCKET_NAME_DEFAULT: str = "juno-preset-data"
    DATASETS_BUCKET_ENV_VAR: str = "DATASETS_BUCKET_NAME"

    # ── Pipeline registry ─────────────────────────────────────────────────
    PIPELINE_VERSION_V1_2: str = "v1-2"
    ALLOWED_VERSIONS: frozenset[str] = frozenset({"v1-2"})

    # ── Batch ─────────────────────────────────────────────────────────────
    MAX_BATCH_RUNS: int = 50

    # ── Default pipeline version ──────────────────────────────────────────
    CARE_PLAN_DEFAULT_VERSION_ENV_VAR: str = "CARE_PLAN_DEFAULT_VERSION"
    CARE_PLAN_DEFAULT_VERSION_FALLBACK: str = "v1-2"

    # ── SSE sentinel ──────────────────────────────────────────────────────
    RESULT_SENTINEL: str = "__result__"

    # ── Pipeline step labels ──────────────────────────────────────────────
    STEPS: dict[int, str] = {
        1: "Reading your note",
        2: "Finding difficult and medical terms",
        3: "Simplifying language",
        4: "Clarifying actions and numbers",
        5: "Organizing your care plan",
    }

    class CARE_PLAN_VERSIONS(Enum):
        V1_2 = "1.2"

    class GRADING_METHODS(Enum):
        SMOG           = _grading_method_base("SMOG", "SMOG (McLaughlin 1969) — counts polysyllabic words; designed for health materials")
        FLESCH_KINCAID = _grading_method_base("Flesch-Kincaid", "Flesch-Kincaid Reading Ease + Grade Level (1975) — sentence length × syllable load")
        DALE_CHALL     = _grading_method_base("Dale-Chall", "Dale-Chall (1948/1995) — difficult words outside the 3,000 familiar-word list")
        PEMAT          = _grading_method_base("PEMAT", "PEMAT (AHRQ 2013) — automated approximation of items 3,8,14,21-22 (understandability) and 27-33 (actionability)")
        SAM            = _grading_method_base("SAM", "SAM (Doak et al. 1996) — automated approximation of content, literacy demand, and layout/typography domains")
        CDC_CCI        = _grading_method_base("CDC CCI", "CDC Clear Communication Index — automated approximation of main message, behavioral recommendations, numbers, and call-to-action items")

    class SOURCE(Enum):
        DOCUMENTS = "documents"
        RECORDING = "recording"
        NOTES     = "notes"

    class IMPORTANCE(Enum):
        HIGH = "high"
        LOW  = "low"

    # Survey performed per PRD-3: remaining Literal types in v1_2.py, grading.py,
    # and input.py are single-use discriminator sentinels and do not qualify for
    # promotion to enums (criteria: 2+ values AND used in 2+ fields or across files).