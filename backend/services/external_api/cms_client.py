"""services/external_api/cms_client.py — CMS 'Doctors and Clinicians' client.

Wraps the public, no-auth CMS datastore query API
(``GET https://data.cms.gov/provider-data/api/1/datastore/query/mj5m-pzi6/0``)
with timeouts and a retry/backoff on 429/5xx (mirroring athena_client.py), and
maps each row to the shared 17-column clinician schema.

``map_cms_row`` is a pure, importable function so it is unit-testable without
any network access.
"""
from __future__ import annotations

import logging
import time

import requests

from utils.constants import Constants

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure helpers (network-free)
# ---------------------------------------------------------------------------

def _empty_row() -> dict:
    """Ordered dict with every one of the 17 columns initialised to ''."""
    return {col: "" for col in Constants.ClinicianDataset.COLUMNS}


def _format_zip(zip_code: str | None) -> str:
    """Format a 9-digit zip as ``#####-####``; keep leading-zero zips as strings."""
    zip_str = (zip_code or "").strip()
    if len(zip_str) == 9 and zip_str.isdigit():
        return f"{zip_str[:5]}-{zip_str[5:]}"
    return zip_str


def _join_nonblank(parts: list[str | None], sep: str = " ") -> str:
    return sep.join(p.strip() for p in parts if p and p.strip())


def map_cms_row(row: dict) -> dict:
    """Map one CMS mj5m-pzi6 row to the 17-column schema.

    - ``Type`` is always ``"Individual"`` (this dataset is individual clinicians).
    - ``Name`` = first + middle + last, then ``, {suff}`` when suff is present.
    - ``adr_ln_2`` is appended only when non-empty AND ``ln_2_sprs != "Y"``.
    - All source values are strings; missing data becomes ``""``.
    """
    out = _empty_row()

    name = _join_nonblank([
        row.get("provider_first_name"),
        row.get("provider_middle_name"),
        row.get("provider_last_name"),
    ])
    suff = (row.get("suff") or "").strip()
    if name and suff:
        name = f"{name}, {suff}"
    elif suff:
        name = suff

    adr_ln_1 = (row.get("adr_ln_1") or "").strip()
    adr_ln_2 = (row.get("adr_ln_2") or "").strip()
    ln_2_sprs = (row.get("ln_2_sprs") or "").strip()
    if adr_ln_2 and ln_2_sprs != "Y":
        address = _join_nonblank([adr_ln_1, adr_ln_2])
    else:
        address = adr_ln_1

    out["NPI"] = str(row.get("npi") or "")
    out["Type"] = "Individual"
    out["Name"] = name
    out["Speciality"] = (row.get("pri_spec") or "").strip()
    out["Address"] = address
    out["City"] = (row.get("citytown") or "").strip()
    out["State"] = (row.get("state") or "").strip()
    out["Zip"] = _format_zip(row.get("zip_code"))
    out["Phone #"] = (row.get("telephone_number") or "").strip()
    out["Creds"] = (row.get("cred") or "").strip()
    return out


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class CmsClient:
    """Thin HTTP client for the CMS mj5m-pzi6 datastore query API."""

    @staticmethod
    def build_conditions(filters: list[tuple[str, str, str]]) -> dict:
        """Flatten ``[(property, value, operator), ...]`` into ``conditions[N][...]`` params."""
        params: dict[str, str] = {}
        for idx, (prop, value, operator) in enumerate(filters):
            params[f"conditions[{idx}][property]"] = prop
            params[f"conditions[{idx}][value]"] = value
            params[f"conditions[{idx}][operator]"] = operator
        return params

    def search(self, params: dict) -> dict:
        """GET the CMS datastore query endpoint with the given params.

        Returns the raw parsed response ``{"count": int, "results": [...], ...}``.
        Retries on 429/5xx with backoff, mirroring athena_client.py.
        """
        cfg = Constants.ClinicianDataset.Cms

        last_exc: Exception | None = None
        for attempt in range(cfg.MAX_RETRIES + 1):
            try:
                resp = requests.get(
                    cfg.BASE_URL,
                    params=params,
                    timeout=cfg.HTTP_TIMEOUT_S,
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt == cfg.MAX_RETRIES:
                    raise
                wait = cfg.RETRY_BACKOFF_S * (2 ** attempt)
                logger.warning("cms_client: request error (attempt %d/%d): %s; retrying in %.1fs",
                               attempt + 1, cfg.MAX_RETRIES, exc, wait)
                time.sleep(wait)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == cfg.MAX_RETRIES:
                    resp.raise_for_status()
                wait = int(resp.headers.get("Retry-After", 0)) or cfg.RETRY_BACKOFF_S * (2 ** attempt)
                logger.warning("cms_client: status %d (attempt %d/%d); sleeping %.1fs",
                               resp.status_code, attempt + 1, cfg.MAX_RETRIES, wait)
                time.sleep(wait)
                continue

            resp.raise_for_status()
            return resp.json()

        # Unreachable under valid configs (MAX_RETRIES >= 0).
        if last_exc:
            raise last_exc
        raise RuntimeError("cms_client: retries exhausted")


cms_client = CmsClient()
