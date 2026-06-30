"""utils/athena_client.py — Athena Health API client for Juno (SP3).

OAuth2 client-credentials flow with token caching, rate-limit-aware
batch fetching (batch_size=2, sleep 30s between batches), and HTML
stripping for encounter summaries.
"""
import html
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from errors import JunoError, ErrorCode
from utils.constants import Constants

logger = logging.getLogger(__name__)

BATCH_SIZE = 2
BATCH_SLEEP_S = 30


class AthenaAPIError(JunoError):
    """Raised when an Athena API call returns a non-200 status."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        if status_code == 401:
            code = ErrorCode.ATHENA_AUTH_FAILED
        elif status_code == 429:
            code = ErrorCode.ATHENA_RATE_LIMIT_ERROR
        elif status_code == 404:
            code = ErrorCode.ATHENA_PATIENT_NOT_FOUND
        else:
            code = ErrorCode.ATHENA_API_ERROR
        super().__init__(code, detail=f"status={status_code} body={body[:200]}")


class AthenaClient:
    """Singleton HTTP client for the Athena Health REST API.

    Caches the OAuth2 access token in memory for the process lifetime,
    refreshing when fewer than TOKEN_REFRESH_BUFFER_S seconds remain.
    """

    TOKEN_TTL_S: int = 300
    TOKEN_REFRESH_BUFFER_S: int = 20

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def get_token(self) -> str:
        """Return a valid Bearer token, refreshing if within 20s of expiry."""
        now = time.time()
        if self._token and now < self._token_expires_at - self.TOKEN_REFRESH_BUFFER_S:
            return self._token
        client_id = os.environ[Constants.ATHENA_CLIENT_ID_ENV_VAR]
        client_secret = os.environ[Constants.ATHENA_CLIENT_SECRET_ENV_VAR]
        resp = requests.post(
            f"{Constants.ATHENA_BASE_URL}/oauth2/v1/token",
            auth=(client_id, client_secret),
            data={
                "grant_type": "client_credentials",
                "scope": "athena/service/Athenanet.MDP.*",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise AthenaAPIError(resp.status_code, resp.text)
        self._token = resp.json()["access_token"]
        self._token_expires_at = now + self.TOKEN_TTL_S
        logger.info("athena_client: obtained new access token (expires in %ds)", self.TOKEN_TTL_S)
        return self._token

    def _get(self, path: str, retries: int = 3) -> dict:
        """GET with retry on 429; raises AthenaAPIError on other non-200."""
        for attempt in range(retries + 1):
            token = self.get_token()
            resp = requests.get(
                f"{Constants.ATHENA_BASE_URL}{path}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=60,
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                if attempt == retries:
                    raise AthenaAPIError(429, f"Rate limit exceeded after {retries} retries")
                logger.warning(
                    "athena_client: rate limited on %s (attempt %d/%d), sleeping %ds",
                    path, attempt + 1, retries, wait,
                )
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                raise AthenaAPIError(resp.status_code, resp.text)
            return resp.json()
        raise AthenaAPIError(429, "Rate limit: max retries exhausted")

    def fetch_encounter_summary(self, practice_id: str, encounter_id: str) -> str:
        """Fetch encounter summary HTML and return as stripped plain text."""
        path = f"/v1/{practice_id}/chart/encounters/{encounter_id}/summary"
        data = self._get(path)
        raw_html_str = data.get("summaryhtml", "")
        return self._strip_html(raw_html_str)

    def fetch_clinical_doc(self, practice_id: str, patient_id: str, document_id: str) -> str:
        """Fetch SOAP-note clinical document and return documentdata string."""
        path = f"/v1/{practice_id}/patients/{patient_id}/documents/clinicaldocument/{document_id}"
        data = self._get(path)
        return data.get("documentdata", "")

    @staticmethod
    def _strip_html(raw_html_str: str) -> str:
        """Strip HTML tags, unescape entities, collapse excess blank lines."""
        unescaped = html.unescape(raw_html_str)
        text = re.sub(r"<[^>]+>", "", unescaped)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def fetch_items_with_rate_limit(
        self, items: list[dict]
    ) -> list[tuple[dict, str]]:
        """Fetch Athena items in batches of BATCH_SIZE with BATCH_SLEEP_S between batches.

        Each item dict must contain: source_kind, practice_id, and either
        encounter_id (for athena_encounter) or patient_id + document_id
        (for athena_clinical_doc).

        Returns list of (item, text) pairs in arbitrary order.
        Sleeps BATCH_SLEEP_S seconds between batches but NOT after the last batch.
        """
        results: list[tuple[dict, str]] = []

        for i in range(0, len(items), BATCH_SIZE):
            batch = items[i : i + BATCH_SIZE]

            def _fetch_one(item: dict) -> str:
                if item["source_kind"] == "athena_encounter":
                    return self.fetch_encounter_summary(
                        item["practice_id"], item["encounter_id"]
                    )
                return self.fetch_clinical_doc(
                    item["practice_id"], item["patient_id"], item["document_id"]
                )

            with ThreadPoolExecutor(max_workers=BATCH_SIZE) as pool:
                futures = {pool.submit(_fetch_one, item): item for item in batch}
                for future in as_completed(futures):
                    results.append((futures[future], future.result()))

            is_last_batch = (i + BATCH_SIZE) >= len(items)
            if not is_last_batch:
                logger.info(
                    "athena_client: batch %d/%d done; sleeping %ds before next batch",
                    i // BATCH_SIZE + 1,
                    (len(items) + BATCH_SIZE - 1) // BATCH_SIZE,
                    BATCH_SLEEP_S,
                )
                time.sleep(BATCH_SLEEP_S)

        return results


# Module-level singleton — shared across all requests in the same worker process.
athena_client = AthenaClient()
