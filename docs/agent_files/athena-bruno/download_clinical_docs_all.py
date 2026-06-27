#!/usr/bin/env python3
"""
download_clinical_docs_all.py — Download Athena clinical documents (text + images).

For each document: downloads text content + all image pages into individual folders.
Structure:
    ClinicalDocumentContentAll/{patientId}_{clinicaldocumentId}/document.txt
    ClinicalDocumentContentAll/{patientId}_{clinicaldocumentId}/images/page_1.png
    ClinicalDocumentContentAll/{patientId}_{clinicaldocumentId}/images/page_2.png
    ...

Supports --max-docs (default 100) and resumes from manifest.json automatically.
Appends to manifest.json after each successful download so progress is preserved
if interrupted.
"""

import argparse
import base64
import json
import os
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
OUTPUT_DIR = SCRIPT_DIR / "ClinicalDocumentContentAll"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"

SANDBOX_PATIENTS = [60178, 60179, 60180, 60181, 60182, 60183, 60184]

# Credentials (fallback to hardcoded sandbox creds if env not set)
_CLIENT_ID = os.getenv("ATHENA_HEALTH_CLIENT_ID") or "0oa130qx2jmWVBcQr298"
_CLIENT_SECRET = os.getenv("ATHENA_HEALTH_CLIENT_SECRET") or (
    "inxzGyC8Rag44orjVsPoB4WbkLrPGedqaGhIMdIZ96oLKr3ws-VBXZdypY"
)

DELAY_BETWEEN_DOCS = 30  # seconds — do NOT reduce


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------


def load_manifest() -> tuple[list[dict], set[int]]:
    """Load existing manifest. Returns (documents_list, set_of_downloaded_doc_ids)."""
    if not MANIFEST_PATH.exists():
        return [], set()
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        docs = data.get("documents", [])
        downloaded_ids = {int(d["doc_id"]) for d in docs if d.get("doc_id")}
        return docs, downloaded_ids
    except Exception as e:
        print(f"[warn] Could not read manifest: {e} — starting fresh")
        return [], set()


def append_to_manifest(existing_docs: list[dict], new_summary: dict) -> None:
    """Append one summary to the manifest file in place."""
    existing_docs.append(new_summary)
    MANIFEST_PATH.write_text(
        json.dumps(
            {"run_date": time.strftime("%Y-%m-%dT%H:%M:%S"), "documents": existing_docs},
            indent=2,
        ),
        encoding="utf-8",
    )


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
# HTTP helpers
# ---------------------------------------------------------------------------


def _api_get(session: requests.Session, path: str, params: dict | None = None) -> dict | None:
    """GET a JSON endpoint. Handles 429 rate limits. Returns None on 4xx."""
    url = f"{BASE_URL}{path}" if path.startswith("/") else path
    while True:
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 60))
            print(f"  [rate-limit] 429 — sleeping {wait}s ...")
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


def _api_get_binary(session: requests.Session, path: str, params: dict | None = None) -> bytes | None:
    """GET a binary endpoint (image). Returns raw bytes. Handles 429 rate limits."""
    url = f"{BASE_URL}{path}" if path.startswith("/") else path
    while True:
        resp = session.get(url, params=params, timeout=60)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 60))
            print(f"  [rate-limit] 429 — sleeping {wait}s ...")
            time.sleep(wait)
            continue
        if resp.status_code in (400, 403, 404):
            print(f"  [skip] HTTP {resp.status_code} for {path}: {resp.text[:200]}")
            return None
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        # If the API returns JSON with base64, decode it
        if "json" in content_type:
            try:
                data = resp.json()
                # Look for common base64 fields
                for key in ("imagedata", "data", "content", "documentdata"):
                    if isinstance(data, dict) and data.get(key):
                        return base64.b64decode(data[key])
                # If it's a list, try the first element
                if isinstance(data, list) and data:
                    item = data[0]
                    for key in ("imagedata", "data", "content", "documentdata"):
                        if isinstance(item, dict) and item.get(key):
                            return base64.b64decode(item[key])
            except Exception as e:
                print(f"  [warn] Could not decode JSON image response: {e}")
            return None

        return resp.content


# ---------------------------------------------------------------------------
# Patient / document helpers
# ---------------------------------------------------------------------------


def get_patient_dept(session: requests.Session, patient_id: int) -> str | None:
    """Return the departmentid for a patient, or None if not found."""
    time.sleep(0.3)
    data = _api_get(session, f"/v1/{PRACTICE_ID}/patients/{patient_id}")
    if not data:
        return None
    pts = data.get("patients") or data.get("items") or []
    if pts:
        return str(pts[0].get("departmentid", "")) or None
    return str(data.get("departmentid", "")) or None


def list_clinical_documents(
    session: requests.Session, patient_id: int, dept_id: str
) -> list[dict]:
    """
    Return ALL clinical document metadata dicts for a patient by paging through
    the endpoint with limit=200 until no more results are returned.
    """
    all_docs: list[dict] = []
    offset = 0
    limit = 200

    while True:
        time.sleep(0.3)
        data = _api_get(
            session,
            f"/v1/{PRACTICE_ID}/patients/{patient_id}/documents/clinicaldocument",
            params={"departmentid": dept_id, "limit": limit, "offset": offset},
        )
        if not data:
            break
        page_docs = data.get("clinicaldocuments") or data.get("items") or []
        if not page_docs:
            break
        all_docs.extend(page_docs)
        print(f"  [list] offset={offset} → got {len(page_docs)} docs (total so far: {len(all_docs)})")

        # If fewer than limit were returned, we've reached the end
        if len(page_docs) < limit:
            break
        offset += limit

    return all_docs


def fetch_document_content(
    session: requests.Session, patient_id: int, doc_id: int
) -> dict | None:
    """Fetch full document JSON from the content endpoint. Returns the unwrapped item dict."""
    time.sleep(0.5)
    data = _api_get(
        session,
        f"/v1/{PRACTICE_ID}/patients/{patient_id}/documents/clinicaldocument/{doc_id}",
    )
    if not data:
        return None
    items = data.get("items") or []
    if items:
        return items[0]
    # Some responses return the doc directly (not in a list)
    if data.get("clinicaldocumentid"):
        return data
    return None


# ---------------------------------------------------------------------------
# Image fetching
# ---------------------------------------------------------------------------


def _ext_from_content_type(content_type: str) -> str:
    """Map a MIME content type to a file extension."""
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/tiff": ".tif",
        "image/gif": ".gif",
        "application/pdf": ".pdf",
    }
    for mime, ext in mapping.items():
        if mime in content_type.lower():
            return ext
    return ".bin"


def fetch_document_images(
    session: requests.Session,
    patient_id: int,
    doc_id: int,
    doc_response: dict,
) -> list[tuple[str, bytes]]:
    """
    Download all image pages for a document.

    Returns a list of (filename, bytes) tuples ordered by pageordering.
    Filenames look like: page_1.png, page_2.png, ...

    The document response `pages` array contains entries like:
        {
          "contenttype": "image/png",
          "href": "https://.../.../pages/54951",
          "pageid": "54951",
          "pageordering": 1
        }

    We hit the href directly (it's a full URL) or fall back to constructing
    the path pattern: /v1/{practiceId}/patients/{patientId}/documents/
                       clinicaldocument/{docId}/pages/{pageId}
    """
    pages = doc_response.get("pages", [])
    if not pages:
        return []

    # Sort by pageordering
    pages_sorted = sorted(pages, key=lambda p: int(p.get("pageordering", 0)))

    results: list[tuple[str, bytes]] = []
    for page in pages_sorted:
        page_id = page.get("pageid", "")
        page_num = int(page.get("pageordering", len(results) + 1))
        content_type = page.get("contenttype", "image/png")
        ext = _ext_from_content_type(content_type)

        href = page.get("href", "")
        if href:
            # href may be a full URL; _api_get_binary accepts full URLs
            url_path = href
        else:
            url_path = (
                f"/v1/{PRACTICE_ID}/patients/{patient_id}"
                f"/documents/clinicaldocument/{doc_id}/pages/{page_id}"
            )

        print(f"    [image] Fetching page {page_num} (pageId={page_id}) ...")
        time.sleep(0.5)
        img_bytes = _api_get_binary(session, url_path)

        if img_bytes:
            filename = f"page_{page_num}{ext}"
            results.append((filename, img_bytes))
            print(f"    [image] Got {len(img_bytes):,} bytes → {filename}")
        else:
            print(f"    [image] No data for page {page_num} (pageId={page_id})")

    return results


# ---------------------------------------------------------------------------
# Full document download (text + images)
# ---------------------------------------------------------------------------


def download_document(
    session: requests.Session, patient_id: int, doc: dict
) -> dict:
    """
    Orchestrate download of one clinical document: text + images.

    Saves into: OUTPUT_DIR/{patient_id}_{doc_id}/
        document.txt       — plain text or placeholder
        images/page_N.ext  — one file per image page

    Returns a summary dict.
    """
    doc_id = doc.get("clinicaldocumentid")
    doc_desc = doc.get("documentdescription", "clinical document")
    doc_source = doc.get("documentsource", "")

    print(f"\n  [doc] Patient={patient_id}  docId={doc_id}  source={doc_source}  desc={doc_desc!r}")

    folder_name = f"{patient_id}_{doc_id}"
    doc_dir = OUTPUT_DIR / folder_name
    doc_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "patient_id": patient_id,
        "doc_id": doc_id,
        "doc_desc": doc_desc,
        "folder": str(doc_dir),
        "text_saved": False,
        "images_saved": 0,
        "pdf_saved": False,
        "errors": [],
    }

    # --- Fetch document content ---
    doc_response = fetch_document_content(session, patient_id, doc_id)
    if not doc_response:
        msg = f"No content response for doc {doc_id}"
        print(f"  [warn] {msg}")
        summary["errors"].append(msg)
        # Save placeholder so folder is non-empty
        txt_path = doc_dir / "document.txt"
        txt_path.write_text(
            f"[NO CONTENT] Patient {patient_id}, Document {doc_id}\n"
            f"Description: {doc_desc}\n",
            encoding="utf-8",
        )
        return summary

    # --- Save text content ---
    doc_data: str = doc_response.get("documentdata", "")
    if doc_data:
        txt_path = doc_dir / "document.txt"
        txt_path.write_text(doc_data, encoding="utf-8")
        size = txt_path.stat().st_size
        print(f"  [text] Saved document.txt ({size:,} bytes)")
        summary["text_saved"] = True
    else:
        # Save a metadata placeholder so we can see what we got
        meta_path = doc_dir / "document.txt"
        # Exclude full pages blob from placeholder to keep it readable
        meta_copy = {k: v for k, v in doc_response.items() if k != "pages"}
        placeholder = (
            f"[NO TEXT CONTENT] Patient {patient_id}, Document {doc_id}\n"
            f"Description: {doc_desc}\n\n"
            f"Metadata:\n{json.dumps(meta_copy, indent=2)}\n"
        )
        meta_path.write_text(placeholder, encoding="utf-8")
        print(f"  [text] No documentdata — saved placeholder document.txt")

    # --- Fetch and save images ---
    pages = doc_response.get("pages", [])
    if pages:
        img_dir = doc_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        print(f"  [images] {len(pages)} page(s) to download ...")

        image_results = fetch_document_images(session, patient_id, doc_id, doc_response)
        for filename, img_bytes in image_results:
            img_path = img_dir / filename
            img_path.write_bytes(img_bytes)
            summary["images_saved"] += 1

        print(f"  [images] Saved {summary['images_saved']} of {len(pages)} page(s)")
    else:
        print(f"  [images] No image pages in this document")

    # --- Fetch and save original PDF ---
    orig_doc = doc_response.get("originaldocument")
    if orig_doc:
        orig_href = orig_doc.get("href", "")
        if orig_href:
            time.sleep(0.5)
            pdf_bytes = _api_get_binary(session, orig_href)
            if pdf_bytes:
                pdf_path = doc_dir / "original.pdf"
                pdf_path.write_bytes(pdf_bytes)
                print(f"  [pdf] Saved original.pdf ({len(pdf_bytes):,} bytes)")
                summary["pdf_saved"] = True

    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Download Athena clinical documents")
    parser.add_argument(
        "--max-docs",
        type=int,
        default=100,
        help="Total number of unique documents to have downloaded after this run (default: 100)",
    )
    args = parser.parse_args()
    max_docs_total = args.max_docs

    # Load existing manifest to know what's already done
    existing_docs, already_downloaded_ids = load_manifest()
    already_done = len(already_downloaded_ids)
    remaining_needed = max(0, max_docs_total - already_done)

    print(f"\n[config] Output directory: {OUTPUT_DIR}")
    print(f"[config] Max docs total target: {max_docs_total}")
    print(f"[config] Already downloaded   : {already_done} (IDs: {sorted(already_downloaded_ids)[:10]}{'...' if len(already_downloaded_ids) > 10 else ''})")
    print(f"[config] Remaining to download: {remaining_needed}")
    print(f"[config] Delay between docs   : {DELAY_BETWEEN_DOCS}s")

    if remaining_needed == 0:
        print(f"\n[main] Already at or above target ({already_done}/{max_docs_total}). Nothing to do.")
        return

    token = get_access_token(_CLIENT_ID, _CLIENT_SECRET)
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # docs_done tracks NEW downloads in this run
    new_downloads = 0
    first_doc = True

    for patient_id in SANDBOX_PATIENTS:
        if new_downloads >= remaining_needed:
            print(f"\n[main] Reached target. Done.")
            break

        print(f"\n[patient] {patient_id}: looking up department ...")
        dept_id = get_patient_dept(session, patient_id)
        if not dept_id:
            # Fallback: try department 1 (known to work for patient 60178)
            print(f"  [fallback] Could not resolve dept for {patient_id}, trying dept=1")
            dept_id = "1"

        print(f"[patient] {patient_id}: dept={dept_id}. Listing ALL clinical documents ...")
        all_docs = list_clinical_documents(session, patient_id, dept_id)
        if not all_docs:
            print(f"[patient] {patient_id}: no clinical documents found, skipping")
            continue

        # Filter out already-downloaded docs
        new_docs = [
            d for d in all_docs
            if int(d.get("clinicaldocumentid", -1)) not in already_downloaded_ids
        ]
        print(
            f"[patient] {patient_id}: {len(all_docs)} total docs, "
            f"{len(new_docs)} new (not yet downloaded)"
        )

        for doc in new_docs:
            if new_downloads >= remaining_needed:
                break

            doc_id = int(doc.get("clinicaldocumentid", -1))
            overall_count = already_done + new_downloads + 1
            print(
                f"\n[{overall_count}/{max_docs_total}] Downloading doc {doc_id} "
                f"for patient {patient_id} ..."
            )

            # Delay between documents (skip before the very first one)
            if not first_doc:
                print(f"  [delay] Sleeping {DELAY_BETWEEN_DOCS}s before next document ...")
                time.sleep(DELAY_BETWEEN_DOCS)
            first_doc = False

            summary = download_document(session, patient_id, doc)

            # Mark as downloaded and append to manifest immediately
            already_downloaded_ids.add(doc_id)
            append_to_manifest(existing_docs, summary)
            new_downloads += 1
            total_so_far = already_done + new_downloads
            print(f"  [progress] {total_so_far}/{max_docs_total} total documents downloaded")

    # --- Final report ---
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  New downloads this run      : {new_downloads}")
    print(f"  Total documents in manifest : {already_done + new_downloads}")
    print(f"  Target                      : {max_docs_total}")
    print(f"  Output root                 : {OUTPUT_DIR}")
    print(f"  Manifest                    : {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
