"""Pure, stateless helpers for translating between JobDoc and Metrics shapes."""

_INPUT_TYPE_MAP = {
    "upload": "file",
    "batch_dataset": "text",       # legacy, pre-extracted text
    "gcs_batch_dataset": "text",   # new, downloads from GCS at worker time
    "doc_id": "doc_id",
    "text": "text",
    "athena_encounter": "text",    # new SP3 — live Athena encounter fetch
    "athena_clinical_doc": "text", # new SP3 — live Athena clinical doc fetch
}


def canonical_input_type(source_kind: str) -> str:
    return _INPUT_TYPE_MAP.get(source_kind, "text")


def is_batch_item(job) -> bool:  # job: models.job.JobDoc
    return job.batch_group_id is not None
