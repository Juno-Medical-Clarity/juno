class Constants:
    # ── Summary schema versions (pre-existing) ───────────────────────────
    SUMMARY_SCHEMA_VERSION_1_2 = "1.2"
    SUMMARY_SCHEMA_VERSION_1_3 = "1.3"
    SUMMARY_SCHEMA_VERSION_1_4 = "1.4"

    # ── File upload limits ────────────────────────────────────────────────
    ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "txt", "docx"})
    MAX_FILE_BYTES: int = 10 * 1024 * 1024       # 10 MB per file
    MAX_FILE_COUNT: int = 10
    MAX_AGGREGATE_FILE_BYTES: int = 25 * 1024 * 1024  # 25 MB combined

    # ── GCS / Cloud config ────────────────────────────────────────────────
    GCS_BUCKET_ENV_VAR: str = "GCP_BUCKET_NAME"

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
