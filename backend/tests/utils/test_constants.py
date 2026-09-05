from utils.constants import Constants


def test_schema_namespace():
    assert Constants.Schema.INPUT_VERSION == "1.0"
    assert Constants.Schema.GRADING_VERSION == "1.0"
    assert Constants.Schema.SUMMARY_SCHEMA_VERSION_1_2 == "1.2"


def test_uploads_namespace():
    assert Constants.Uploads.MAX_FILE_BYTES == 10 * 1024 * 1024
    assert Constants.Uploads.MAX_AGGREGATE_FILE_BYTES == 25 * 1024 * 1024
    assert "pdf" in Constants.Uploads.ALLOWED_EXTENSIONS
    assert Constants.Uploads.UPLOAD_PREFIX == "care_plan-uploads"
    # Generous by design (no practical limit on real clinical documents) --
    # see the constant's own comment for the reasoning. Must stay comfortably
    # below what fits in the model's input context.
    assert Constants.Uploads.MAX_TEXT_LENGTH == 500_000


def test_deadlines_namespace():
    assert Constants.Deadlines.SINGLE_JOB_INTERNAL_DEADLINE_S == 270
    assert Constants.Deadlines.BATCH_ITEM_INTERNAL_DEADLINE_S == 870
    assert Constants.Deadlines.JOB_TIMEOUT_SECONDS_SINGLE == 300
    assert Constants.Deadlines.JOB_TIMEOUT_SECONDS_BATCH == 900


def test_llm_namespace():
    assert Constants.Llm.MODEL_DEFAULT == "gemini-1.5-pro"
    assert Constants.Llm.TEMPERATURE_TEXT == 0.3
    assert Constants.Llm.TEMPERATURE_JSON == 0.2
    assert Constants.Llm.MAX_TOKENS == 8192
    assert Constants.Llm.MAX_TOKENS_LONG_FORM == 65536


def test_athena_namespace():
    assert Constants.Athena.TOKEN_TTL_S == 300
    assert Constants.Athena.TOKEN_REFRESH_BUFFER_S == 20
    assert Constants.Athena.HTTP_TIMEOUT_TOKEN_S == 30
    assert Constants.Athena.HTTP_TIMEOUT_GET_S == 60
    assert Constants.Athena.MAX_RETRIES == 3
    assert "Athenanet" in Constants.Athena.OAUTH_SCOPE


def test_athena_source_kind_enum():
    sk = Constants.Athena.AthenaSourceKind
    assert sk.ATHENA_ENCOUNTER == "athena_encounter"
    assert sk.ATHENA_CLINICAL_DOC == "athena_clinical_doc"


def test_storage_namespace():
    assert Constants.Storage.GCS_PRESET_PREFIX == "preset-data"
    assert Constants.Storage.TEMP_BASE == "/tmp/juno-datasets"
    assert Constants.Storage.SIGNED_URL_TTL_MIN == 30


def test_observability_namespace():
    assert Constants.Observability.SERVICE_NAME_DEFAULT == "backend-processing"
    assert "user_id" in Constants.Observability.LOG_EXTRA_KEYS
    assert Constants.Observability.DIM_OUTCOME == "OpOutcome"


def test_env_vars_namespace_deduplicated():
    assert Constants.EnvVars.DATASETS_BUCKET == "DATASETS_BUCKET_NAME"


def test_pipeline_v1_2_steps_enum():
    steps = Constants.Pipeline.PIPELINE_V1_2_STEPS
    assert steps.DETECT_TERMS.number == 2
    assert steps.DETECT_TERMS.label == "Finding difficult and medical terms"
    assert steps.READ_NOTE.number == 1
    assert steps.SIMPLIFY_LANGUAGE.number == 3
    assert steps.CLARIFY_AND_ACTION.number == 4
    assert steps.STRUCTURE_DOCUMENT.number == 5
