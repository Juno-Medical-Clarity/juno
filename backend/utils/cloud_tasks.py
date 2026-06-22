"""Cloud Tasks enqueue helper for juno-worker dispatch."""
import json

from google.cloud import tasks_v2
from google.protobuf import duration_pb2


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
