"""services/external_api/athena_client.py — Athena Health REST client (OAuth2, retry, typed parse, metrics)."""
import html
import logging
import os
import re
import time

import requests

from utils.constants import Constants
from utils.markers.markers import Markers
from utils.markers.marker import Scope
from models.external_api.athena_models import (
    AthenaTokenResponse,
    AthenaEncounterSummaryResponse,
    AthenaClinicalDocumentContentResponse,
)
from models.external_api.athena_errors import AthenaAPIError
from errors import ErrorCode

logger = logging.getLogger(__name__)


class AthenaClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def get_token(self) -> str:
        """Return a valid Bearer token, refreshing if within TOKEN_REFRESH_BUFFER_S of expiry."""
        now = time.time()
        if (
            self._token
            and now < self._token_expires_at - Constants.Athena.TOKEN_REFRESH_BUFFER_S
        ):
            return self._token

        def _fetch(scope: Scope) -> str:
            client_id = os.environ[Constants.EnvVars.ATHENA_CLIENT_ID]
            client_secret = os.environ[Constants.EnvVars.ATHENA_CLIENT_SECRET]
            resp = requests.post(
                f"{Constants.Athena.BASE_URL}/oauth2/v1/token",
                auth=(client_id, client_secret),
                data={
                    "grant_type": "client_credentials",
                    "scope": Constants.Athena.OAUTH_SCOPE,
                },
                timeout=Constants.Athena.HTTP_TIMEOUT_TOKEN_S,
            )
            scope.add(Constants.Observability.DIM_STATUS_CODE, resp.status_code)
            if resp.status_code != 200:
                raise AthenaAPIError(
                    resp.status_code, resp.text, code=ErrorCode.ATHENA_AUTH_FAILED
                )
            token_response = AthenaTokenResponse.model_validate(resp.json())
            self._token = token_response.access_token
            self._token_expires_at = now + Constants.Athena.TOKEN_TTL_S
            logger.info(
                "athena_client: obtained new access token (expires in %ds)",
                Constants.Athena.TOKEN_TTL_S,
            )
            return self._token

        return Markers.Athena.GetToken.execute(_fetch)

    def _get(
        self,
        path: str,
        retries: int | None = None,
        scope: Scope | None = None,
    ) -> dict:
        """GET with retry on 429; raises AthenaAPIError on other non-200."""
        if retries is None:
            retries = Constants.Athena.MAX_RETRIES
        for attempt in range(retries + 1):
            token = self.get_token()
            resp = requests.get(
                f"{Constants.Athena.BASE_URL}{path}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=Constants.Athena.HTTP_TIMEOUT_GET_S,
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 60))
                if attempt == retries:
                    if scope:
                        scope.add(Constants.Observability.DIM_STATUS_CODE, 429)
                        scope.add("retries", attempt)
                    raise AthenaAPIError(
                        429,
                        f"Rate limit exceeded after {retries} retries",
                        code=ErrorCode.ATHENA_RATE_LIMIT_ERROR,
                    )
                logger.warning(
                    "athena_client: rate limited on %s (attempt %d/%d), sleeping %ds",
                    path, attempt + 1, retries, wait,
                )
                time.sleep(wait)
                continue
            if scope:
                scope.add(Constants.Observability.DIM_STATUS_CODE, resp.status_code)
                scope.add("retries", attempt)
            if resp.status_code != 200:
                raise AthenaAPIError(resp.status_code, resp.text)
            return resp.json()
        raise AthenaAPIError(
            429,
            "Rate limit: max retries exhausted",
            code=ErrorCode.ATHENA_RATE_LIMIT_ERROR,
        )

    def fetch_encounter_summary(self, practice_id: str, encounter_id: str) -> str:
        """Fetch encounter summary HTML and return as stripped plain text."""
        def _do(scope: Scope) -> str:
            path = f"/v1/{practice_id}/chart/encounters/{encounter_id}/summary"
            scope.add("source_kind", Constants.Athena.AthenaSourceKind.ATHENA_ENCOUNTER.value)
            data = self._get(path, scope=scope)
            summary = AthenaEncounterSummaryResponse.model_validate(data)
            return self._strip_html(summary.summaryhtml)
        return Markers.Athena.FetchEncounterSummary.execute(_do)

    def fetch_clinical_doc(self, practice_id: str, patient_id: str, document_id: str) -> str:
        """Fetch SOAP-note clinical document and return documentdata string."""
        def _do(scope: Scope) -> str:
            path = f"/v1/{practice_id}/patients/{patient_id}/documents/clinicaldocument/{document_id}"
            scope.add("source_kind", Constants.Athena.AthenaSourceKind.ATHENA_CLINICAL_DOC.value)
            data = self._get(path, scope=scope)
            doc = AthenaClinicalDocumentContentResponse.model_validate(data)
            return doc.documentdata or ""
        return Markers.Athena.FetchClinicalDoc.execute(_do)

    @staticmethod
    def _strip_html(raw_html_str: str) -> str:
        """Strip HTML tags, unescape entities, collapse excess blank lines."""
        unescaped = html.unescape(raw_html_str)
        text = re.sub(r"<[^>]+>", "", unescaped)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


athena_client = AthenaClient()
