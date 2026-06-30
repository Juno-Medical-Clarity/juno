"""Shared GCS bucket construction helper."""
import os

from google.cloud import storage as gcs

_DEFAULT_BUCKET = os.environ.get("GCP_BUCKET_NAME", "")


def get_gcs_bucket(bucket_name: str | None = None):
    """Return a GCS Bucket for the given name (default: GCP_BUCKET_NAME env)."""
    name = bucket_name or _DEFAULT_BUCKET
    client = gcs.Client(project=os.environ.get("GCP_PROJECT_ID") or None)
    return client.bucket(name)
