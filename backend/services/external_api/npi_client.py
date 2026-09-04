"""services/external_api/npi_client.py — NPPES NPI Registry official API client.

Wraps the public, no-auth NPI Registry endpoint
(``GET https://npiregistry.cms.hhs.gov/api/?version=2.1``) with timeouts and a
retry/backoff on 429/5xx (mirroring athena_client.py), and maps each result to
the shared 17-column clinician schema.

``map_npi_result`` is a pure, importable function so it is unit-testable without
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


def _format_zip(postal_code: str | None) -> str:
    """Format a 9-digit postal code as ``#####-####``; leave others untouched."""
    zip_str = (postal_code or "").strip()
    if len(zip_str) == 9 and zip_str.isdigit():
        return f"{zip_str[:5]}-{zip_str[5:]}"
    return zip_str


def _join_nonblank(parts: list[str | None], sep: str = " ") -> str:
    return sep.join(p.strip() for p in parts if p and p.strip())


def map_npi_result(result: dict) -> dict:
    """Map one official-API (snake_case) NPI result to the 17-column schema.

    - Picks the taxonomy with ``primary == True`` (falls back to the first).
    - Picks the address with ``address_purpose == "LOCATION"`` (falls back to
      the first address).
    - ``NPI-1`` -> ``Individual``, ``NPI-2`` -> ``Organization``.
    """
    row = _empty_row()

    basic = result.get("basic") or {}
    taxonomies = result.get("taxonomies") or []
    addresses = result.get("addresses") or []

    # Primary taxonomy: primary==True, else first.
    primary_tax = next(
        (t for t in taxonomies if t.get("primary")),
        taxonomies[0] if taxonomies else {},
    )

    # Location address: address_purpose=="LOCATION", else first.
    location = next(
        (a for a in addresses if a.get("address_purpose") == "LOCATION"),
        addresses[0] if addresses else {},
    )

    enum_type = result.get("enumeration_type") or ""
    is_org = enum_type == "NPI-2"

    if is_org:
        name = (basic.get("organization_name") or "").strip()
    else:
        name = _join_nonblank([
            basic.get("first_name"),
            basic.get("middle_name"),
            basic.get("last_name"),
        ])

    address = _join_nonblank([
        location.get("address_1"),
        location.get("address_2"),
    ])

    row["NPI"] = str(result.get("number") or "")
    row["Type"] = "Organization" if is_org else ("Individual" if enum_type == "NPI-1" else "")
    row["Name"] = name
    row["Speciality"] = (primary_tax.get("desc") or "").strip()
    row["Address"] = address
    row["City"] = (location.get("city") or "").strip()
    row["State"] = (location.get("state") or "").strip()
    row["Zip"] = _format_zip(location.get("postal_code"))
    row["Phone #"] = (location.get("telephone_number") or "").strip()
    row["Creds"] = (basic.get("credential") or "").strip()
    return row


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class NpiClient:
    """Thin HTTP client for the official NPI Registry API."""

    def search(self, params: dict) -> dict:
        """GET the NPI Registry with the given query params (version added here).

        Returns the raw parsed envelope ``{"result_count": int, "results": [...]}``.
        Retries on 429/5xx with backoff, mirroring athena_client.py.
        """
        cfg = Constants.ClinicianDataset.Npi
        query = {"version": cfg.VERSION, **params}

        last_exc: Exception | None = None
        for attempt in range(cfg.MAX_RETRIES + 1):
            try:
                resp = requests.get(
                    cfg.BASE_URL,
                    params=query,
                    timeout=cfg.HTTP_TIMEOUT_S,
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt == cfg.MAX_RETRIES:
                    raise
                wait = cfg.RETRY_BACKOFF_S * (2 ** attempt)
                logger.warning("npi_client: request error (attempt %d/%d): %s; retrying in %.1fs",
                               attempt + 1, cfg.MAX_RETRIES, exc, wait)
                time.sleep(wait)
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == cfg.MAX_RETRIES:
                    resp.raise_for_status()
                wait = int(resp.headers.get("Retry-After", 0)) or cfg.RETRY_BACKOFF_S * (2 ** attempt)
                logger.warning("npi_client: status %d (attempt %d/%d); sleeping %.1fs",
                               resp.status_code, attempt + 1, cfg.MAX_RETRIES, wait)
                time.sleep(wait)
                continue

            resp.raise_for_status()
            return resp.json()

        # Unreachable under valid configs (MAX_RETRIES >= 0).
        if last_exc:
            raise last_exc
        raise RuntimeError("npi_client: retries exhausted")


npi_client = NpiClient()
