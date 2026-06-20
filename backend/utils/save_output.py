"""Persistence helpers for Simplify output artifacts."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from firebase_admin import firestore
from google.cloud import storage as gcs


def upload_combined_pdf(pdf_bytes: bytes, user_id: str) -> str:
    """Upload combined input PDF bytes and return a gs:// URI."""
    bucket_name = os.environ.get("GCP_BUCKET_NAME", "")
    if not bucket_name:
        raise RuntimeError("GCP_BUCKET_NAME is not configured")

    project_id = os.environ.get("GCP_PROJECT_ID", "") or None
    object_id = str(uuid.uuid4())
    blob_name = f"simplify/{user_id}/inputs/{object_id}.pdf"

    client = gcs.Client(project=project_id)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(pdf_bytes, content_type="application/pdf")
    return f"gs://{bucket_name}/{blob_name}"


def save_simplify_output(
    *,
    user_id: str,
    name: str,
    source_filename: str,
    input_pdf_gcs: str | None,
    output_data: dict,
    dataset_group: str | None = None,
    batch_group_id: str | None = None,
) -> str:
    """Save a Simplify output document to Firestore and return its ID."""
    database_id = os.environ.get("FIRESTORE_DATABASE_ID", "(default)")
    output_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    db = firestore.client(database_id=database_id)
    payload = {
        "uid": user_id,
        "name": name,
        "source_filename": source_filename,
        "created_at": now,
        "updated_at": now,
        "input_pdf_gcs": input_pdf_gcs or "",
        "output_data": output_data,
    }
    if dataset_group is not None:
        payload["dataset_group"] = dataset_group
    if batch_group_id is not None:
        payload["batch_group_id"] = batch_group_id

    db.collection("simplify_outputs").document(output_id).set(payload)
    return output_id
