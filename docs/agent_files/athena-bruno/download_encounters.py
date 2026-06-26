#!/usr/bin/env python3
"""
download_encounters.py — Download Athena Health encounter summaries to HTML files.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load credentials from .env in the same directory as this script
SCRIPT_DIR = Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

BASE_URL = "https://api.preview.platform.athenahealth.com"
PRACTICE_ID = "195900"

# Known sandbox test patients — departmentid 1
SANDBOX_PATIENTS = [60178, 60179, 60180, 60181, 60182, 60183, 60184]
# Additional patient known to have closed encounters
EXTRA_PATIENTS = [8188]  # departmentid 150

# Departments to scan for booked appointments with encounter IDs
SCAN_DEPTS = [1, 150, 82, 102, 21, 142]

# Batch rate-limiting: pause after every BATCH_SIZE *new* downloads
BATCH_SIZE = 2
BATCH_DELAY_SECONDS = 30


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_access_token(client_id: str, client_secret: str) -> str:
    """Obtain a Bearer token via client_credentials flow."""
    url = f"{BASE_URL}/oauth2/v1/token"
    resp = requests.post(
        url,
        auth=(client_id, client_secret),
        data={
            "grant_type": "client_credentials",
            "scope": "athena/service/Athenanet.MDP.*",
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    print(f"[auth] Obtained access token (expires_in={resp.json().get('expires_in')}s)")
    return token


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _api_get(session: requests.Session, path: str, params: dict | None = None,
             retries: int = 3) -> dict | list | None:
    """GET wrapper with rate-limit/timeout handling and graceful 4xx errors."""
    import requests as _requests
    url = f"{BASE_URL}{path}"
    attempt = 0
    while True:
        try:
            resp = session.get(url, params=params, timeout=60)
        except (_requests.exceptions.ReadTimeout, _requests.exceptions.ConnectionError) as exc:
            attempt += 1
            if attempt > retries:
                print(f"  [error] Timeout/connection error after {retries} retries: {exc}")
                return None
            wait = 10 * attempt
            print(f"  [retry] Network error ({exc.__class__.__name__}), waiting {wait}s (attempt {attempt}/{retries}) …")
            time.sleep(wait)
            continue
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 60))
            print(f"  [rate-limit] 429 — sleeping {wait}s …")
            time.sleep(wait)
            continue
        if resp.status_code in (400, 404):
            msg = ""
            try:
                msg = resp.json().get("error", resp.text[:80])
            except Exception:
                msg = resp.text[:80]
            print(f"  [skip] HTTP {resp.status_code}: {msg}")
            return None
        resp.raise_for_status()
        return resp.json()


def get_patient_dept(session: requests.Session, patient_id: int | str) -> str | None:
    """Return the departmentid string for a patient, or None on failure."""
    data = _api_get(session, f"/v1/{PRACTICE_ID}/patients/{patient_id}")
    if not data:
        return None
    if isinstance(data, list):
        return str(data[0].get("departmentid", "")) if data else None
    return str(data.get("departmentid", "")) or None


def get_booked_encounters(session: requests.Session, dept_id: int | str) -> list[tuple[int, int]]:
    """Return (patient_id, encounter_id) pairs from booked appointments in a dept."""
    data = _api_get(
        session,
        f"/v1/{PRACTICE_ID}/appointments/booked",
        params={"startdate": "01/01/2019", "enddate": "06/30/2026",
                "limit": 100, "departmentid": dept_id},
    )
    if not data:
        return []
    pairs = []
    for appt in data.get("appointments", []):
        pid = appt.get("patientid")
        enc = appt.get("encounterid")
        if pid and enc:
            pairs.append((int(pid), int(enc)))
    return pairs


def get_patient_encounters(session: requests.Session, patient_id: int | str, dept_id: int | str) -> list[dict]:
    """List encounters for a patient in a given department."""
    data = _api_get(
        session,
        f"/v1/{PRACTICE_ID}/chart/{patient_id}/encounters",
        params={"departmentid": dept_id},
    )
    if not data:
        return []
    return data.get("encounters", [])


def get_encounter_summary(session: requests.Session, encounter_id: int | str) -> dict | None:
    """Fetch the HTML summary for an encounter.
    Correct path: /v1/{practiceId}/chart/encounters/{encounterId}/summary  (plural)
    """
    return _api_get(session, f"/v1/{PRACTICE_ID}/chart/encounters/{encounter_id}/summary")


# ---------------------------------------------------------------------------
# HTML extraction
# ---------------------------------------------------------------------------

def extract_html(summary_data: dict, patient_id, encounter_id) -> str:
    """Pull HTML out of the summary JSON, falling back to pretty-printed JSON."""
    if summary_data is None:
        return "<p>No data returned.</p>"

    # Try common keys that might hold HTML (case-insensitive)
    html_keys = ("summaryhtml", "html", "summary", "encountersummary", "summaryhtml", "content", "body")
    for key in html_keys:
        for k, v in summary_data.items():
            if k.lower() == key and isinstance(v, str) and v.strip():
                print(f"  [html] Found HTML content under key '{k}' ({len(v):,} chars)")
                return v

    # If there's any string value that looks like HTML, use it
    for k, v in summary_data.items():
        if isinstance(v, str) and "<" in v and ">" in v:
            print(f"  [html] Using HTML-like string from key '{k}'")
            return v

    # Fallback: pretty-print JSON
    print(f"  [html] No HTML key found — wrapping JSON in <pre>")
    return f"<pre>{json.dumps(summary_data, indent=2)}</pre>"


def build_html_page(patient_id, encounter_id, body_content: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Encounter {encounter_id} - Patient {patient_id}</title>
  <link rel="stylesheet" href="athena-encounter.css">
</head>
<body>
{body_content}
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Core download
# ---------------------------------------------------------------------------

def download_encounter(session: requests.Session, patient_id, encounter_id, out_dir: Path) -> bool:
    """Download one encounter summary and write it as HTML. Returns True on success."""
    fname = out_dir / f"patient_{patient_id}_encounter_{encounter_id}.html"
    if fname.exists():
        size = fname.stat().st_size
        print(f"  [skip] {fname.name} already exists ({size:,} bytes)")
        return True

    print(f"  [fetch] Encounter {encounter_id} for patient {patient_id} …")
    time.sleep(0.5)

    summary = get_encounter_summary(session, encounter_id)
    if summary is None:
        return False

    body = extract_html(summary, patient_id, encounter_id)
    html = build_html_page(patient_id, encounter_id, body)

    fname.write_text(html, encoding="utf-8")
    size = fname.stat().st_size
    print(f"  [saved] {fname.name} ({size:,} bytes)")
    return True


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_encounter_pairs(session: requests.Session, dept_id=None) -> list[tuple[int, int]]:
    """Build a list of (patient_id, encounter_id) to attempt, deduped."""
    pairs: list[tuple[int, int]] = []
    seen_enc_ids: set[int] = set()

    def add(pid, enc):
        if enc not in seen_enc_ids:
            seen_enc_ids.add(enc)
            pairs.append((int(pid), int(enc)))

    # 1. Scan booked appointments in target depts to find direct encounter IDs
    scan_depts = [dept_id] if dept_id else SCAN_DEPTS
    for did in scan_depts:
        print(f"[discover] Booked appointments in dept {did} …")
        time.sleep(0.5)
        for pid, enc in get_booked_encounters(session, did):
            add(pid, enc)
        print(f"  Running total: {len(pairs)} encounter pairs")

    # 2. For known patients (with known departments), list their encounters
    known = [(8188, 150)]  # patient, dept
    for pid, dept in known:
        if dept_id and str(dept) != str(dept_id):
            continue
        print(f"[discover] Encounters for patient {pid} (dept {dept}) …")
        time.sleep(0.5)
        encs = get_patient_encounters(session, pid, dept)
        for e in encs:
            enc_id = e.get("encounterid")
            if enc_id:
                add(pid, enc_id)
        print(f"  Running total: {len(pairs)} encounter pairs")

    return pairs


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download Athena Health encounter summaries as HTML files."
    )
    parser.add_argument("folder", help="Output directory for HTML files")
    parser.add_argument("--count", type=int, default=10, help="Max encounters to download (default: 10)")
    parser.add_argument("--patient-id", type=int, help="Target a specific patient")
    parser.add_argument("--department-id", type=int, help="Filter by department ID")
    parser.add_argument("--encounter-id", type=int, help="Download a single specific encounter")
    args = parser.parse_args()

    out_dir = Path(args.folder)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[output] Writing to: {out_dir.resolve()}")

    client_id = os.getenv("ATHENA_HEALTH_CLIENT_ID")
    client_secret = os.getenv("ATHENA_HEALTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit("ERROR: ATHENA_HEALTH_CLIENT_ID and ATHENA_HEALTH_CLIENT_SECRET must be set in .env")

    token = get_access_token(client_id, client_secret)
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    downloaded = 0

    # --- Single encounter mode ---
    if args.encounter_id:
        patient_id = args.patient_id or "unknown"
        ok = download_encounter(session, patient_id, args.encounter_id, out_dir)
        if ok:
            downloaded += 1
        _finish(out_dir, downloaded)
        return

    # --- Single patient + encounter list mode ---
    if args.patient_id:
        # Resolve dept for this patient
        print(f"[patient {args.patient_id}] Looking up department …")
        time.sleep(0.5)
        dept = args.department_id or get_patient_dept(session, args.patient_id)
        if not dept:
            sys.exit(f"ERROR: Could not determine department for patient {args.patient_id}")
        print(f"  Department: {dept}")
        time.sleep(0.5)
        encs = get_patient_encounters(session, args.patient_id, dept)
        print(f"  Found {len(encs)} encounter(s)")
        for enc in encs:
            if downloaded >= args.count:
                break
            enc_id = enc.get("encounterid")
            if enc_id:
                ok = download_encounter(session, args.patient_id, enc_id, out_dir)
                if ok:
                    downloaded += 1
                    if downloaded % BATCH_SIZE == 0:
                        print(f"  [batch] Downloaded {downloaded} so far — sleeping {BATCH_DELAY_SECONDS}s …")
                        time.sleep(BATCH_DELAY_SECONDS)
        _finish(out_dir, downloaded)
        return

    # --- Discovery mode ---
    pairs = discover_encounter_pairs(session, dept_id=args.department_id)
    print(f"\n[run] Found {len(pairs)} candidate encounter(s) — targeting {args.count}\n")

    for patient_id, encounter_id in pairs:
        if downloaded >= args.count:
            break
        ok = download_encounter(session, patient_id, encounter_id, out_dir)
        if ok:
            downloaded += 1
            if downloaded % BATCH_SIZE == 0:
                print(f"  [batch] Downloaded {downloaded} so far — sleeping {BATCH_DELAY_SECONDS}s …")
                time.sleep(BATCH_DELAY_SECONDS)

    _finish(out_dir, downloaded)


def _finish(out_dir: Path, downloaded: int):
    files = sorted(out_dir.glob("*.html"))
    print(f"\n[done] Downloaded {downloaded} new encounter(s)")
    print(f"[files] {len(files)} HTML file(s) in {out_dir.resolve()}:")
    for f in files:
        size = f.stat().st_size
        print(f"  {f.name}  ({size:,} bytes)")


if __name__ == "__main__":
    main()
