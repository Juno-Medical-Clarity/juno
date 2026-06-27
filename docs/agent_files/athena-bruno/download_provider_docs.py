#!/usr/bin/env python3
"""
download_provider_docs.py — Download Athena Health provider-authored clinical
content for Juno (medical AI assistant for providers).

Selected APIs focus on content a provider writes or signs:
  1.  Encounter Summary       — chart/encounters/{id}/summary
  2.  Assessment/Plan         — chart/encounter/{id}/assessment
  3.  Encounter Orders        — chart/encounter/{id}/orders
  4.  Problem List            — chart/{patientid}/problems
  5.  Medications             — chart/{patientid}/medications
  6.  Allergies               — chart/{patientid}/allergies
  7.  Vitals                  — chart/{patientid}/vitals
  8.  Medical History         — chart/{patientid}/medicalhistory
  9.  Social History          — chart/{patientid}/socialhistory
 10.  Family History          — chart/{patientid}/familyhistory
 11.  Surgical History        — chart/{patientid}/surgicalhistory
 12.  Lab Results             — chart/{patientid}/labresults
 13.  Prescriptions           — patients/{patientid}/documents/prescription
 14.  Clinical Documents      — patients/{patientid}/documents/clinicaldocument
 15.  Office Notes            — patients/{patientid}/documents/officenote
"""

import base64
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

BASE_URL = "https://api.preview.platform.athenahealth.com"
PRACTICE_ID = "195900"

SANDBOX_PATIENTS = [60178, 60179, 60180, 60181, 60182, 60183, 60184]

MAX_SAMPLES_PER_API = 5   # max JSON files to write per API
MAX_ENCOUNTERS_PER_PATIENT = 2  # encounters to pull per patient

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def get_access_token(client_id: str, client_secret: str) -> str:
    resp = requests.post(
        f"{BASE_URL}/oauth2/v1/token",
        auth=(client_id, client_secret),
        data={
            "grant_type": "client_credentials",
            "scope": "athena/service/Athenanet.MDP.*",
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    print(f"[auth] Token obtained (expires_in={resp.json().get('expires_in')}s)")
    return token


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def _api_get(session: requests.Session, path: str, params: dict | None = None) -> dict | None:
    url = f"{BASE_URL}{path}"
    while True:
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 60))
            print(f"  [rate-limit] 429 — sleeping {wait}s …")
            time.sleep(wait)
            continue
        if resp.status_code in (400, 403, 404):
            print(f"  [skip] HTTP {resp.status_code} for {path}: {resp.text[:200]}")
            return None
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return {"items": data}
        return data


# ---------------------------------------------------------------------------
# Save helper
# ---------------------------------------------------------------------------


def save_sample(folder: str, label: str, index: int, data: dict) -> None:
    out_dir = SCRIPT_DIR / folder
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = out_dir / f"sample_{label}_{index:02d}.json"
    fname.write_text(json.dumps(data, indent=2), encoding="utf-8")
    size = fname.stat().st_size
    print(f"  [saved] {folder}/sample_{label}_{index:02d}.json ({size:,} bytes)")


# ---------------------------------------------------------------------------
# Bootstrap: get patient department + encounter IDs
# ---------------------------------------------------------------------------


def get_patient_dept(session: requests.Session, patient_id: int) -> str | None:
    time.sleep(0.3)
    data = _api_get(session, f"/v1/{PRACTICE_ID}/patients/{patient_id}")
    if not data:
        return None
    pts = data.get("patients") or data.get("items") or []
    if pts:
        return str(pts[0].get("departmentid", "")) or None
    return str(data.get("departmentid", "")) or None


def get_encounters(session: requests.Session, patient_id: int, dept_id: str) -> list[dict]:
    time.sleep(0.3)
    data = _api_get(
        session,
        f"/v1/{PRACTICE_ID}/chart/{patient_id}/encounters",
        params={"departmentid": dept_id},
    )
    if not data:
        return []
    return data.get("encounters", [])


# ---------------------------------------------------------------------------
# 1. Encounter Summary
# ---------------------------------------------------------------------------


def download_encounter_summaries(session: requests.Session, encounter_map: list[dict]) -> int:
    """encounter_map: list of {patient_id, encounter_id}"""
    folder = "EncounterSummaries"
    saved = 0
    print(f"\n[API] Encounter Summary → {folder}/")
    for item in encounter_map:
        if saved >= MAX_SAMPLES_PER_API:
            break
        pid, eid = item["patient_id"], item["encounter_id"]
        time.sleep(0.3)
        data = _api_get(session, f"/v1/{PRACTICE_ID}/chart/encounters/{eid}/summary")
        if data:
            save_sample(folder, f"p{pid}_e{eid}", saved, data)
            saved += 1
    print(f"  → {saved} sample(s) saved")
    return saved


# ---------------------------------------------------------------------------
# 2. Assessment / Plan
# ---------------------------------------------------------------------------


def download_assessments(session: requests.Session, encounter_map: list[dict]) -> int:
    folder = "Assessment"
    saved = 0
    print(f"\n[API] Assessment/Plan → {folder}/")
    for item in encounter_map:
        if saved >= MAX_SAMPLES_PER_API:
            break
        pid, eid = item["patient_id"], item["encounter_id"]
        time.sleep(0.3)
        data = _api_get(session, f"/v1/{PRACTICE_ID}/chart/encounter/{eid}/assessment")
        if data:
            save_sample(folder, f"p{pid}_e{eid}", saved, data)
            saved += 1
    print(f"  → {saved} sample(s) saved")
    return saved


# ---------------------------------------------------------------------------
# 3. Encounter Orders
# ---------------------------------------------------------------------------


def download_encounter_orders(session: requests.Session, encounter_map: list[dict]) -> int:
    folder = "EncounterOrders"
    saved = 0
    print(f"\n[API] Encounter Orders → {folder}/")
    for item in encounter_map:
        if saved >= MAX_SAMPLES_PER_API:
            break
        pid, eid = item["patient_id"], item["encounter_id"]
        time.sleep(0.3)
        data = _api_get(session, f"/v1/{PRACTICE_ID}/chart/encounter/{eid}/orders")
        if data:
            save_sample(folder, f"p{pid}_e{eid}", saved, data)
            saved += 1
    print(f"  → {saved} sample(s) saved")
    return saved


# ---------------------------------------------------------------------------
# 4. Problem List
# ---------------------------------------------------------------------------


def download_problems(session: requests.Session, patient_dept_map: list[dict]) -> int:
    folder = "ProblemList"
    saved = 0
    print(f"\n[API] Problem List → {folder}/")
    for item in patient_dept_map:
        if saved >= MAX_SAMPLES_PER_API:
            break
        pid, dept = item["patient_id"], item["dept_id"]
        time.sleep(0.3)
        data = _api_get(
            session,
            f"/v1/{PRACTICE_ID}/chart/{pid}/problems",
            params={"departmentid": dept},
        )
        if data:
            save_sample(folder, f"p{pid}", saved, data)
            saved += 1
    print(f"  → {saved} sample(s) saved")
    return saved


# ---------------------------------------------------------------------------
# 5. Medications
# ---------------------------------------------------------------------------


def download_medications(session: requests.Session, patient_dept_map: list[dict]) -> int:
    folder = "Medications"
    saved = 0
    print(f"\n[API] Medications → {folder}/")
    for item in patient_dept_map:
        if saved >= MAX_SAMPLES_PER_API:
            break
        pid, dept = item["patient_id"], item["dept_id"]
        time.sleep(0.3)
        data = _api_get(
            session,
            f"/v1/{PRACTICE_ID}/chart/{pid}/medications",
            params={"departmentid": dept},
        )
        if data:
            save_sample(folder, f"p{pid}", saved, data)
            saved += 1
    print(f"  → {saved} sample(s) saved")
    return saved


# ---------------------------------------------------------------------------
# 6. Allergies
# ---------------------------------------------------------------------------


def download_allergies(session: requests.Session, patient_dept_map: list[dict]) -> int:
    folder = "Allergies"
    saved = 0
    print(f"\n[API] Allergies → {folder}/")
    for item in patient_dept_map:
        if saved >= MAX_SAMPLES_PER_API:
            break
        pid, dept = item["patient_id"], item["dept_id"]
        time.sleep(0.3)
        data = _api_get(
            session,
            f"/v1/{PRACTICE_ID}/chart/{pid}/allergies",
            params={"departmentid": dept},
        )
        if data:
            save_sample(folder, f"p{pid}", saved, data)
            saved += 1
    print(f"  → {saved} sample(s) saved")
    return saved


# ---------------------------------------------------------------------------
# 7. Vitals
# ---------------------------------------------------------------------------


def download_vitals(session: requests.Session, patient_dept_map: list[dict]) -> int:
    folder = "Vitals"
    saved = 0
    print(f"\n[API] Vitals → {folder}/")
    for item in patient_dept_map:
        if saved >= MAX_SAMPLES_PER_API:
            break
        pid, dept = item["patient_id"], item["dept_id"]
        time.sleep(0.3)
        data = _api_get(
            session,
            f"/v1/{PRACTICE_ID}/chart/{pid}/vitals",
            params={"departmentid": dept},
        )
        if data:
            save_sample(folder, f"p{pid}", saved, data)
            saved += 1
    print(f"  → {saved} sample(s) saved")
    return saved


# ---------------------------------------------------------------------------
# 8. Medical History
# ---------------------------------------------------------------------------


def download_medical_history(session: requests.Session, patient_dept_map: list[dict]) -> int:
    folder = "MedicalHistory"
    saved = 0
    print(f"\n[API] Medical History → {folder}/")
    for item in patient_dept_map:
        if saved >= MAX_SAMPLES_PER_API:
            break
        pid, dept = item["patient_id"], item["dept_id"]
        time.sleep(0.3)
        data = _api_get(
            session,
            f"/v1/{PRACTICE_ID}/chart/{pid}/medicalhistory",
            params={"departmentid": dept},
        )
        if data:
            save_sample(folder, f"p{pid}", saved, data)
            saved += 1
    print(f"  → {saved} sample(s) saved")
    return saved


# ---------------------------------------------------------------------------
# 9. Social History
# ---------------------------------------------------------------------------


def download_social_history(session: requests.Session, patient_dept_map: list[dict]) -> int:
    folder = "SocialHistory"
    saved = 0
    print(f"\n[API] Social History → {folder}/")
    for item in patient_dept_map:
        if saved >= MAX_SAMPLES_PER_API:
            break
        pid, dept = item["patient_id"], item["dept_id"]
        time.sleep(0.3)
        data = _api_get(
            session,
            f"/v1/{PRACTICE_ID}/chart/{pid}/socialhistory",
            params={"departmentid": dept},
        )
        if data:
            save_sample(folder, f"p{pid}", saved, data)
            saved += 1
    print(f"  → {saved} sample(s) saved")
    return saved


# ---------------------------------------------------------------------------
# 10. Family History
# ---------------------------------------------------------------------------


def download_family_history(session: requests.Session, patient_dept_map: list[dict]) -> int:
    folder = "FamilyHistory"
    saved = 0
    print(f"\n[API] Family History → {folder}/")
    for item in patient_dept_map:
        if saved >= MAX_SAMPLES_PER_API:
            break
        pid, dept = item["patient_id"], item["dept_id"]
        time.sleep(0.3)
        data = _api_get(
            session,
            f"/v1/{PRACTICE_ID}/chart/{pid}/familyhistory",
            params={"departmentid": dept},
        )
        if data:
            save_sample(folder, f"p{pid}", saved, data)
            saved += 1
    print(f"  → {saved} sample(s) saved")
    return saved


# ---------------------------------------------------------------------------
# 11. Surgical History
# ---------------------------------------------------------------------------


def download_surgical_history(session: requests.Session, patient_dept_map: list[dict]) -> int:
    folder = "SurgicalHistory"
    saved = 0
    print(f"\n[API] Surgical History → {folder}/")
    for item in patient_dept_map:
        if saved >= MAX_SAMPLES_PER_API:
            break
        pid, dept = item["patient_id"], item["dept_id"]
        time.sleep(0.3)
        data = _api_get(
            session,
            f"/v1/{PRACTICE_ID}/chart/{pid}/surgicalhistory",
            params={"departmentid": dept},
        )
        if data:
            save_sample(folder, f"p{pid}", saved, data)
            saved += 1
    print(f"  → {saved} sample(s) saved")
    return saved


# ---------------------------------------------------------------------------
# 12. Lab Results
# ---------------------------------------------------------------------------


def download_lab_results(session: requests.Session, patient_dept_map: list[dict]) -> int:
    folder = "LabResults"
    saved = 0
    print(f"\n[API] Lab Results → {folder}/")
    for item in patient_dept_map:
        if saved >= MAX_SAMPLES_PER_API:
            break
        pid, dept = item["patient_id"], item["dept_id"]
        time.sleep(0.3)
        data = _api_get(
            session,
            f"/v1/{PRACTICE_ID}/chart/{pid}/labresults",
            params={"departmentid": dept},
        )
        if data:
            save_sample(folder, f"p{pid}", saved, data)
            saved += 1
    print(f"  → {saved} sample(s) saved")
    return saved


# ---------------------------------------------------------------------------
# 13. Prescriptions
# ---------------------------------------------------------------------------


def download_prescriptions(session: requests.Session, patient_dept_map: list[dict]) -> int:
    folder = "Prescriptions"
    saved = 0
    print(f"\n[API] Prescriptions → {folder}/")
    for item in patient_dept_map:
        if saved >= MAX_SAMPLES_PER_API:
            break
        pid, dept = item["patient_id"], item["dept_id"]
        time.sleep(0.3)
        data = _api_get(
            session,
            f"/v1/{PRACTICE_ID}/patients/{pid}/documents/prescription",
            params={"departmentid": dept},
        )
        if data:
            save_sample(folder, f"p{pid}", saved, data)
            saved += 1
    print(f"  → {saved} sample(s) saved")
    return saved


# ---------------------------------------------------------------------------
# 14. Clinical Documents
# ---------------------------------------------------------------------------


def download_clinical_documents(session: requests.Session, patient_dept_map: list[dict]) -> int:
    folder = "ClinicalDocuments"
    saved = 0
    print(f"\n[API] Clinical Documents → {folder}/")
    for item in patient_dept_map:
        if saved >= MAX_SAMPLES_PER_API:
            break
        pid, dept = item["patient_id"], item["dept_id"]
        time.sleep(0.3)
        data = _api_get(
            session,
            f"/v1/{PRACTICE_ID}/patients/{pid}/documents/clinicaldocument",
            params={"departmentid": dept},
        )
        if data:
            save_sample(folder, f"p{pid}", saved, data)
            saved += 1
    print(f"  → {saved} sample(s) saved")
    return saved


# ---------------------------------------------------------------------------
# 15. Office Notes
# ---------------------------------------------------------------------------


def download_office_notes(session: requests.Session, patient_dept_map: list[dict]) -> int:
    folder = "OfficeNotes"
    saved = 0
    print(f"\n[API] Office Notes → {folder}/")
    for item in patient_dept_map:
        if saved >= MAX_SAMPLES_PER_API:
            break
        pid, dept = item["patient_id"], item["dept_id"]
        time.sleep(0.3)
        data = _api_get(
            session,
            f"/v1/{PRACTICE_ID}/patients/{pid}/documents/officenote",
            params={"departmentid": dept},
        )
        if data:
            save_sample(folder, f"p{pid}", saved, data)
            saved += 1
    print(f"  → {saved} sample(s) saved")
    return saved


# ---------------------------------------------------------------------------
# 16. Clinical Document Content
# ---------------------------------------------------------------------------


def _slugify(text: str, max_len: int = 40) -> str:
    """Convert text to a filename-safe slug."""
    text = re.sub(r"[^a-zA-Z0-9_\- ]", "", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text[:max_len] or "document"


def download_clinical_document_content(
    session: requests.Session,
    patient_id: int,
    clinical_document_id: int,
    document_description: str = "clinical_document",
) -> dict | None:
    """
    Fetch the actual text/content of a single clinical document.

    Endpoint:
        GET /v1/{practiceId}/patients/{patientId}/documents/clinicaldocument/{clinicaldocumentId}

    The response is a JSON array with one object.  The key fields are:
        documentdata  — plain-text SOAP note / letter (most documents)
        pages         — list of page objects for image-based (scanned) documents
        documentclass — e.g. "CLINICALDOCUMENT"

    Saves to ClinicalDocumentContent/:
        {clinicaldocumentId}_{slug}.txt   — plain-text documents
        {clinicaldocumentId}_{slug}.html  — HTML documents
        {clinicaldocumentId}_{slug}.pdf   — base64-encoded PDF documents
        {clinicaldocumentId}_{slug}_meta.json — page-based (image) documents
    """
    out_dir = SCRIPT_DIR / "ClinicalDocumentContent"
    out_dir.mkdir(parents=True, exist_ok=True)

    url = f"/v1/{PRACTICE_ID}/patients/{patient_id}/documents/clinicaldocument/{clinical_document_id}"
    data = _api_get(session, url)
    if not data:
        return None

    # _api_get wraps bare lists in {"items": [...]}, unwrap
    items = data.get("items") or []
    item = items[0] if items else None
    if not item:
        print(f"  [skip] No content for doc {clinical_document_id}")
        return None

    doc_data: str = item.get("documentdata", "")
    pages: list = item.get("pages", [])
    slug = _slugify(document_description)

    if doc_data:
        # Detect format
        stripped = doc_data.strip()
        if stripped.startswith("<"):
            ext = ".html"
            fname = out_dir / f"{clinical_document_id}_{slug}.html"
            fname.write_text(doc_data, encoding="utf-8")
        else:
            # Check for base64-encoded PDF (long, no natural language)
            sample = stripped[:200].replace("\n", "").replace("\r", "")
            if len(stripped) > 500 and re.match(r"^[A-Za-z0-9+/=]+$", sample):
                ext = ".pdf"
                fname = out_dir / f"{clinical_document_id}_{slug}.pdf"
                try:
                    raw = base64.b64decode(doc_data)
                    fname.write_bytes(raw)
                except Exception:
                    ext = ".txt"
                    fname = out_dir / f"{clinical_document_id}_{slug}.txt"
                    fname.write_text(doc_data, encoding="utf-8")
            else:
                ext = ".txt"
                fname = out_dir / f"{clinical_document_id}_{slug}.txt"
                fname.write_text(doc_data, encoding="utf-8")

        size = fname.stat().st_size
        print(f"  [saved] ClinicalDocumentContent/{fname.name} ({size:,} bytes)")
        return {
            "clinicaldocumentid": clinical_document_id,
            "patient_id": patient_id,
            "document_description": document_description,
            "file": str(fname),
            "format": ext,
            "size_bytes": size,
        }

    if pages:
        # Image-based / scanned document — save metadata so the IDs are recorded
        fname = out_dir / f"{clinical_document_id}_{slug}_meta.json"
        fname.write_text(json.dumps(item, indent=2), encoding="utf-8")
        size = fname.stat().st_size
        print(f"  [saved] ClinicalDocumentContent/{fname.name} ({size:,} bytes) [page-based]")
        return {
            "clinicaldocumentid": clinical_document_id,
            "patient_id": patient_id,
            "document_description": document_description,
            "file": str(fname),
            "format": ".json",
            "size_bytes": size,
            "note": f"page-based document ({len(pages)} page(s)), no documentdata text",
        }

    print(f"  [skip] Doc {clinical_document_id} has no documentdata and no pages")
    return None


def download_clinical_document_contents(
    session: requests.Session,
    clinical_docs_metadata_dir: str | None = None,
    max_docs: int = 10,
) -> int:
    """
    Download actual content for up to *max_docs* clinical documents.

    Reads (patientid, clinicaldocumentid) pairs from the ClinicalDocuments/
    metadata files already on disk, then fetches each document's full text
    via download_clinical_document_content().

    INTERFACE-sourced documents are prioritised because they typically contain
    rich narrative text (SOAP notes, letters) rather than scanned images.
    """
    folder = "ClinicalDocumentContent"
    print(f"\n[API] Clinical Document Content → {folder}/")

    meta_dir = Path(clinical_docs_metadata_dir) if clinical_docs_metadata_dir else SCRIPT_DIR / "ClinicalDocuments"
    if not meta_dir.exists():
        print(f"  [skip] Metadata dir not found: {meta_dir}")
        return 0

    candidates: list[dict] = []
    for meta_file in sorted(meta_dir.glob("*.json")):
        with open(meta_file, encoding="utf-8") as f:
            meta = json.load(f)
        docs = meta.get("clinicaldocuments") or meta.get("items") or []
        for d in docs:
            candidates.append({
                "patient_id": d.get("patientid") or d.get("patient_id"),
                "clinicaldocumentid": d.get("clinicaldocumentid"),
                "document_description": d.get("documentdescription", "clinical document"),
                "documentsource": d.get("documentsource", ""),
            })

    # INTERFACE docs first (richer narrative text), then others
    ordered = sorted(candidates, key=lambda c: 0 if c.get("documentsource") == "INTERFACE" else 1)

    saved = 0
    tried = 0
    for c in ordered:
        if saved >= max_docs:
            break
        pid = c.get("patient_id")
        doc_id = c.get("clinicaldocumentid")
        if not pid or not doc_id:
            continue
        tried += 1
        time.sleep(0.3)
        result = download_clinical_document_content(
            session, int(pid), int(doc_id), c.get("document_description", "clinical document")
        )
        if result:
            saved += 1
        if tried >= max_docs * 3:  # give up after trying 3× as many
            break

    print(f"  → {saved} document(s) saved to {folder}/")
    return saved


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    client_id = os.getenv("ATHENA_HEALTH_CLIENT_ID")
    client_secret = os.getenv("ATHENA_HEALTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit("ERROR: ATHENA_HEALTH_CLIENT_ID and ATHENA_HEALTH_CLIENT_SECRET must be set in .env")

    token = get_access_token(client_id, client_secret)
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    # ------------------------------------------------------------------
    # Phase 1: Resolve department IDs and encounter IDs for all patients
    # ------------------------------------------------------------------
    print("\n[phase 1] Resolving patient departments and encounters …")
    patient_dept_map: list[dict] = []   # [{patient_id, dept_id}]
    encounter_map: list[dict] = []       # [{patient_id, encounter_id}]

    for pid in SANDBOX_PATIENTS:
        print(f"\n  Patient {pid}: looking up department …")
        dept = get_patient_dept(session, pid)
        if not dept:
            print(f"  Patient {pid}: could not resolve dept, skipping")
            continue
        print(f"  Patient {pid}: dept={dept}")
        patient_dept_map.append({"patient_id": pid, "dept_id": dept})

        # Fetch encounters for this patient
        encounters = get_encounters(session, pid, dept)
        if not encounters:
            print(f"  Patient {pid}: no encounters found")
            continue
        print(f"  Patient {pid}: {len(encounters)} encounter(s) found")
        for enc in encounters[:MAX_ENCOUNTERS_PER_PATIENT]:
            eid = enc.get("encounterid")
            if eid:
                encounter_map.append({"patient_id": pid, "encounter_id": eid})
                print(f"    encounter {eid}")

    print(f"\n[phase 1] {len(patient_dept_map)} patients resolved, {len(encounter_map)} encounters")

    # ------------------------------------------------------------------
    # Phase 2: Download each API
    # ------------------------------------------------------------------
    print("\n[phase 2] Downloading provider-authored content …")

    results: dict[str, int] = {}

    results["EncounterSummaries"] = download_encounter_summaries(session, encounter_map)
    results["Assessment"] = download_assessments(session, encounter_map)
    results["EncounterOrders"] = download_encounter_orders(session, encounter_map)
    results["ProblemList"] = download_problems(session, patient_dept_map)
    results["Medications"] = download_medications(session, patient_dept_map)
    results["Allergies"] = download_allergies(session, patient_dept_map)
    results["Vitals"] = download_vitals(session, patient_dept_map)
    results["MedicalHistory"] = download_medical_history(session, patient_dept_map)
    results["SocialHistory"] = download_social_history(session, patient_dept_map)
    results["FamilyHistory"] = download_family_history(session, patient_dept_map)
    results["SurgicalHistory"] = download_surgical_history(session, patient_dept_map)
    results["LabResults"] = download_lab_results(session, patient_dept_map)
    results["Prescriptions"] = download_prescriptions(session, patient_dept_map)
    results["ClinicalDocuments"] = download_clinical_documents(session, patient_dept_map)
    results["OfficeNotes"] = download_office_notes(session, patient_dept_map)
    results["ClinicalDocumentContent"] = download_clinical_document_contents(session, max_docs=10)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    total = 0
    for folder, count in results.items():
        status = "OK" if count > 0 else "EMPTY"
        print(f"  [{status:5s}] {folder:<25} {count} file(s)")
        total += count
    print(f"\n  Total files saved: {total}")
    print(f"  Output directory: {SCRIPT_DIR.resolve()}/")


if __name__ == "__main__":
    main()
