"""routes/clinician_dataset.py — Clinician Dataset search endpoints.

Two POST endpoints that proxy public, no-auth external registries and return
rows already mapped to the shared 17-column clinician schema:

  POST /clinician_dataset/npi/search  — NPPES NPI Registry official API
  POST /clinician_dataset/cms/search  — CMS 'Doctors and Clinicians' (mj5m-pzi6)

Row-mapping logic lives in services/external_api/{npi,cms}_client.py as pure,
importable functions.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests
from flask import Blueprint, jsonify, request
from pydantic import BaseModel, ConfigDict, ValidationError

from errors import make_error_response, ErrorCode
from utils.constants import Constants
from utils.firebase import verify_firebase_token
from services.external_api.npi_client import npi_client, map_npi_result
from services.external_api.cms_client import cms_client, map_cms_row

logger = logging.getLogger(__name__)
clinician_dataset_bp = Blueprint("clinician_dataset", __name__)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class NpiSearchRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    number: Optional[str] = None
    enumerationType: Optional[str] = None  # "NPI-1" | "NPI-2" | None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    organizationName: Optional[str] = None
    taxonomyDescription: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postalCode: Optional[str] = None
    limit: int = Constants.ClinicianDataset.Npi.DEFAULT_LIMIT
    skip: int = Constants.ClinicianDataset.Npi.DEFAULT_SKIP


class CmsSearchRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    state: Optional[str] = None
    citytown: Optional[str] = None
    pri_spec: Optional[str] = None
    provider_last_name: Optional[str] = None
    provider_first_name: Optional[str] = None
    facility_name: Optional[str] = None
    zip_code: Optional[str] = None
    limit: int = Constants.ClinicianDataset.Cms.DEFAULT_LIMIT
    offset: int = Constants.ClinicianDataset.Cms.DEFAULT_OFFSET


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validation_error(exc: ValidationError):
    first_err = exc.errors()[0]
    loc = first_err.get("loc", ("unknown",))
    return make_error_response(
        ErrorCode.INPUT_VALIDATION_ERROR,
        request.path,
        {"field": str(loc[0]) if loc else "unknown", "reason": first_err["msg"]},
    ).to_dict(), 400


def _field_error(field: str, reason: str):
    return make_error_response(
        ErrorCode.INPUT_VALIDATION_ERROR,
        request.path,
        {"field": field, "reason": reason},
    ).to_dict(), 400


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def _nonblank(value: Optional[str]) -> str:
    return (value or "").strip()


# ---------------------------------------------------------------------------
# Endpoint 1 — NPI Registry
# ---------------------------------------------------------------------------

@clinician_dataset_bp.route("/clinician_dataset/npi/search", methods=["POST"])
@verify_firebase_token
def npi_search(user_id: str):
    """Search the NPPES NPI Registry and return rows in the 17-column schema.

    Response: {"rows": [...], "count": <result_count>}
    """
    _ = user_id
    try:
        req = NpiSearchRequest(**(request.get_json(silent=True) or {}))
    except ValidationError as exc:
        return _validation_error(exc)

    enum_type = _nonblank(req.enumerationType)
    if enum_type and enum_type not in ("NPI-1", "NPI-2"):
        return _field_error("enumerationType", "must be 'NPI-1', 'NPI-2', or null")

    # Map camelCase request fields → official-API snake_case params.
    field_to_param = {
        "number": req.number,
        "enumeration_type": req.enumerationType,
        "first_name": req.firstName,
        "last_name": req.lastName,
        "organization_name": req.organizationName,
        "taxonomy_description": req.taxonomyDescription,
        "city": req.city,
        "state": req.state,
        "postal_code": req.postalCode,
    }
    params = {k: _nonblank(v) for k, v in field_to_param.items() if _nonblank(v)}

    # Official API rejects a query using ONLY `state`; require another criterion.
    narrowing_fields = (
        "number", "first_name", "last_name", "organization_name",
        "taxonomy_description", "city", "postal_code",
    )
    if "state" in params and not any(f in params for f in narrowing_fields):
        return _field_error(
            "state",
            "State alone is not accepted by the NPI Registry — add another filter "
            "(name, city, postal code, or taxonomy).",
        )

    cfg = Constants.ClinicianDataset.Npi
    params["limit"] = _clamp(req.limit, 0, cfg.MAX_LIMIT)
    params["skip"] = _clamp(req.skip, 0, cfg.MAX_SKIP)

    try:
        data = npi_client.search(params)
    except requests.RequestException:
        logger.exception("npi_search: upstream NPI Registry request failed")
        return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 502

    results = data.get("results") or []
    rows = [map_npi_result(r) for r in results]
    count = int(data.get("result_count") or 0)
    return jsonify({"rows": rows, "count": count})


# ---------------------------------------------------------------------------
# Endpoint 2 — CMS Doctors & Clinicians (mj5m-pzi6)
# ---------------------------------------------------------------------------

@clinician_dataset_bp.route("/clinician_dataset/cms/search", methods=["POST"])
@verify_firebase_token
def cms_search(user_id: str):
    """Search the CMS mj5m-pzi6 dataset and return rows in the 17-column schema.

    Response: {"rows": [...], "count": <total matching rows>}
    """
    _ = user_id
    try:
        req = CmsSearchRequest(**(request.get_json(silent=True) or {}))
    except ValidationError as exc:
        return _validation_error(exc)

    # (property, value, operator) tuples. `=` for state; `like` (substring) for
    # the free-text fields, matching the verified spec behaviour.
    filters: list[tuple[str, str, str]] = []
    state = _nonblank(req.state)
    if state:
        filters.append(("state", state, "="))
    like_fields = {
        "citytown": req.citytown,
        "pri_spec": req.pri_spec,
        "provider_last_name": req.provider_last_name,
        "provider_first_name": req.provider_first_name,
        "facility_name": req.facility_name,
        "zip_code": req.zip_code,
    }
    for prop, raw in like_fields.items():
        value = _nonblank(raw)
        if value:
            filters.append((prop, f"%{value}%", "like"))

    cfg = Constants.ClinicianDataset.Cms
    params: dict = {
        "limit": _clamp(req.limit, 0, cfg.MAX_LIMIT),
        "offset": max(0, req.offset),
    }
    params.update(cms_client.build_conditions(filters))

    try:
        data = cms_client.search(params)
    except requests.RequestException:
        logger.exception("cms_search: upstream CMS request failed")
        return make_error_response(ErrorCode.INTERNAL_ERROR, request.path).to_dict(), 502

    results = data.get("results") or []
    rows = [map_cms_row(r) for r in results]
    count = int(data.get("count") or 0)
    return jsonify({"rows": rows, "count": count})
