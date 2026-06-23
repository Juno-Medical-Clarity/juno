"""Cloud Tasks enqueue helper for juno-worker dispatch."""
import json
import os

from google.cloud import tasks_v2
from google.protobuf import duration_pb2


class MissingJobConfigError(RuntimeError):
    """Raised when a required Cloud Tasks env var is unset/empty.

    The message names the missing variable so server-side logs are diagnosable
    instead of surfacing an opaque KeyError.
    """


def require_env(name: str) -> str:
    """Return the value of a required env var, or raise a clear error.

    Unlike ``os.environ[name]`` (which raises a bare ``KeyError`` that gives no
    indication of which variable is missing), this names the offending variable
    and treats empty strings as missing too.
    """
    value = os.environ.get(name)
    if not value:
        raise MissingJobConfigError(
            f"Required environment variable '{name}' is not set. "
            "Async job dispatch requires CLOUD_TASKS_QUEUE, WORKER_URL, and "
            "WORKER_SERVICE_ACCOUNT to be configured on this service."
        )
    return value


def enqueue_job(
    job_id: str,
    *,
    queue_name: str,
    worker_url: str,
    service_account: str,
    deadline_seconds: int,
    batch_run_id: str | None = None,
) -> None:
    client = tasks_v2.CloudTasksClient()
    url = f"{worker_url.rstrip('/')}/internal/jobs/execute/{job_id}"
    payload = json.dumps({"job_id": job_id, "batch_run_id": batch_run_id}).encode()

    task = {
        "http_request": {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": url,
            "headers": {"Content-Type": "application/json"},
            "body": payload,
            "oidc_token": {
                "service_account_email": service_account,
                "audience": url,
            },
        },
        "dispatch_deadline": duration_pb2.Duration(seconds=deadline_seconds),
    }
    client.create_task(request={"parent": queue_name, "task": task})
