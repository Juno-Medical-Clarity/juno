# Tasks: Utils Consolidation & Dead-Code Cleanup

Read `PRD.md` in this folder first. All paths are relative to `backend/` unless noted. Every grep
claim below was verified against the `fixing-cors` working tree.

Recommended landing order: **Task 1 → 2 → 8 → 3 → 4 → 5 → 6 → 7 → 9 → 10**. Tasks 1, 4, 5, 6, 7 are
the dead-code deletions and can be done independently; the consolidations (2, 3) and the
`upload_combined_pdf` relocation (8) have import-site dependencies. **Task 8 must land before Task 3**,
since Task 3 deletes `utils/save_output.py` and Task 8 must first lift `upload_combined_pdf` out of it.

---

### Task 1 — Merge PDF modules into `utils/pdf.py`

**Create** `utils/pdf.py` by concatenating, **verbatim**:
- all of `utils/pdf_extract.py` (`extract_text_from_pdf`, `import io/logging/PyPDF2`, module logger)
- all of `utils/pdf_merge.py` (`merge_pdfs`, `_txt_to_pdf`, `_append_pdf`, `from pypdf import ...`,
  `import textwrap`)

Keep a single module-level `logger = logging.getLogger(__name__)`. Do not unify the two PDF libraries
(`PyPDF2` vs `pypdf`) — they are used by different functions; leave both.

**Delete** `utils/pdf_extract.py` and `utils/pdf_merge.py`.

**Update import sites:**
- `routes/simplify.py:30` → `from utils.pdf import extract_text_from_pdf`
- `routes/simplify_v1_1.py:30` → `from utils.pdf import extract_text_from_pdf`
- `routes/simplify_v1_2.py:31-32` → `from utils.pdf import merge_pdfs, extract_text_from_pdf`
  (keep `from ... import` form so the route binds `merge_pdfs` locally — required for the existing test
  patch target `routes.simplify_v1_2.merge_pdfs` to keep working)
- `tests/test_pdf_merge.py:24,37` → `from utils.pdf import merge_pdfs`; line 39
  `assertLogs("utils.pdf_merge", ...)` → `assertLogs("utils.pdf", ...)`

**Do NOT change** the `@patch("routes.simplify_v1_2.merge_pdfs", ...)` targets in
`tests/test_simplify_v1_2_persistence.py:122,181,266` — they patch the name as bound in the route, which
is unchanged.

**Acceptance:**
- `python -c "from utils.pdf import extract_text_from_pdf, merge_pdfs"` succeeds.
- `python -c "import utils.pdf_extract"` and `import utils.pdf_merge` both raise `ModuleNotFoundError`.
- `pytest tests/test_pdf_merge.py tests/test_simplify_v1_2_persistence.py` passes.

---

### Task 2 — Create `utils/firebase.py` (Firebase init + Firestore client + auth + ownership + persistence)

**Create** `utils/firebase.py` with these symbols (see PRD §4.3 for full signatures):

1. `initialize_firebase()` — move **verbatim** from `config.py:11-32` (the whole function, plus its
   `import json, os, firebase_admin`, `from firebase_admin import credentials, firestore`,
   `from dotenv import load_dotenv` + the `load_dotenv()` call if not already done elsewhere).
2. `firestore_client()` — new; body identical to the `_db()` helpers currently in
   `routes/saved_outputs.py:34-36` and `routes/grading.py:17-19`:
   ```python
   def firestore_client():
       db_id = os.environ.get("FIRESTORE_DATABASE_ID", "(default)")
       return firestore.client(database_id=db_id)
   ```
3. `verify_firebase_token(f)` — move **verbatim** from `utils/auth.py` (keep `from firebase_admin
   import auth`, `from functools import wraps`, `from flask import g, request, jsonify`).
4. `get_owned_doc_or_403(db, collection, doc_id, user_id)` — generalize the identical
   `_get_doc_or_403` from `saved_outputs.py:39-48` / `grading.py:22-30`, taking `collection` as a
   parameter (both callers use `"simplify_outputs"`).
5. `save_simplify_output(...)` and `_without_raw(...)` — move **verbatim** from
   `utils/save_output.py:31-68` (keep `from firebase_admin import firestore`; keep `import copy, os,
   uuid`, `from datetime import datetime, timezone`).

Do **not** move `upload_combined_pdf` here — it moves into `routes/simplify_v1_2.py` (its sole caller)
in Task 8. No `utils/gcs.py` is created (owner directive).

**Acceptance:** `python -c "from utils.firebase import initialize_firebase, firestore_client,
verify_firebase_token, get_owned_doc_or_403, save_simplify_output"` succeeds.

---

### Task 3 — Repoint all Firebase/Firestore import sites; delete `utils/auth.py`

**`config.py`** — remove the `initialize_firebase` definition outright. **Do NOT add a re-export**
(owner directive: no one-line wrapper/re-export modules; breaking now is fine, nothing is in
production — PRD §4.3, §9). Leave the config constants (`GCP_PROJECT_ID`, `VERTEX_AI_MODEL`,
`SIMPLIFY_DEFAULT_VERSION`, etc.) in place. Repoint the two consumers directly:
- `app.py:11` → `from utils.firebase import initialize_firebase` (was `from config import ...`).
- `tests/test_container_startup.py:16,44` → `patch("utils.firebase.initialize_firebase", ...)`
  (was `patch("config.initialize_firebase", ...)`).

**`routes/saved_outputs.py`:**
- line 21: `from utils.auth import verify_firebase_token` →
  `from utils.firebase import verify_firebase_token, firestore_client, get_owned_doc_or_403`
- delete local `_db()` (34-36) and `_get_doc_or_403()` (39-48)
- replace `db = _db()` calls with `db = firestore_client()`
- replace `_get_doc_or_403(db, doc_id, user_id)` calls with
  `get_owned_doc_or_403(db, "simplify_outputs", doc_id, user_id)`

**`routes/grading.py`:** same swap as above (line 9 import; delete `_db` 17-19 and `_get_doc_or_403`
22-30; update call sites at lines 49-50).

**Simple import-line swaps (no other change):**
- `routes/simplify.py:28` → `from utils.firebase import verify_firebase_token`
- `routes/datasets.py:4` → `from utils.firebase import verify_firebase_token`
- `routes/batch.py:15` → `from utils.firebase import verify_firebase_token`
- `routes/batch.py:17` → `from utils.firebase import save_simplify_output`
- `routes/simplify_v1_2.py:33` → `from utils.firebase import save_simplify_output`
  (`upload_combined_pdf` is no longer imported — it is *defined locally* in this route module per
  Task 8)

**Delete** `utils/save_output.py` and `utils/auth.py` (their contents now live in `utils/firebase.py`;
`upload_combined_pdf` is moved into `routes/simplify_v1_2.py` per Task 8). Do this only after Tasks
2 + 8 land. No re-export shims (owner directive — PRD §4.8, §9).

**Update test patch targets:**
- `tests/test_save_output.py` — Firestore cases (`save_simplify_output`) repoint patches from
  `utils.save_output.*` → `utils.firebase.*`; the `upload_combined_pdf` case repoints to
  `routes.simplify_v1_2.*` (its new home — see Task 8).
- `tests/test_simplify_v1_2_persistence.py` patch targets `routes.simplify_v1_2.save_simplify_output`
  / `routes.simplify_v1_2.upload_combined_pdf` stay **unchanged** (`save_simplify_output` is bound
  locally via `from utils.firebase import ...`; `upload_combined_pdf` is now *defined* in
  `routes.simplify_v1_2`).

**Acceptance:**
- `python -c "import utils.auth"` and `import utils.save_output` raise `ModuleNotFoundError`.
- `python -c "from config import initialize_firebase"` raises `ImportError` (re-export removed);
  `from utils.firebase import initialize_firebase` works.
- `pytest tests/test_saved_outputs_route.py tests/test_save_output.py tests/test_container_startup.py
  tests/test_batch_route.py tests/test_simplify_v1_2_persistence.py tests/test_simplify_auth.py` passes.

---

### Task 4 — Delete dead `utils/vertex_ai.py`

Grep evidence: `VertexAIService` / `generate_questions` / `process_transcript_to_soap` imported and
called nowhere; references a nonexistent `summarySchema/` dir (PRD §4.5).

**Delete** `utils/vertex_ai.py`.

**Acceptance:** `python -c "import utils.vertex_ai"` raises `ModuleNotFoundError`; full test suite still
green (nothing imported it).

---

### Task 5 — Delete dead `utils/ocr.py`

Grep evidence: zero importers outside the file itself (PRD §4.6).

**Delete** `utils/ocr.py`.

**Acceptance:** `python -c "import utils.ocr"` raises `ModuleNotFoundError`; full suite green.

---

### Task 6 — Delete dead `utils/storage.py` (`StorageService`)

Grep evidence: `StorageService` imported nowhere (PRD §4.6). **Owner confirmed deletion** (PRD §8.1,
§9). No further sign-off needed.

**Delete** `utils/storage.py`.

**Acceptance:** `python -c "import utils.storage"` raises `ModuleNotFoundError`; full suite green.

---

### Task 7 — Remove `utils/LOGGING.md`

`docs/logging.md` is the home (SP4 owns its content). **Delete** `utils/LOGGING.md`. Do **not** touch
`docs/logging.md`, `utils/juno_logger.py`, or `utils/juno_metrics.py`.

**Acceptance:** `utils/LOGGING.md` no longer exists; `docs/logging.md` unchanged.

---

### Task 8 — Relocate `upload_combined_pdf` into `routes/simplify_v1_2.py` (no `utils/gcs.py`)

**[CHANGED per owner — `utils/gcs.py` is DELETED / not created; PRD §4.3, §9 OQ-2.]** Do **not** create
a standalone GCS utility module. `upload_combined_pdf` has exactly one caller, so move it into that
caller.

**Move** `upload_combined_pdf` **verbatim** from `utils/save_output.py:14-28` into
`routes/simplify_v1_2.py` (define it as a module-level function in the route file; keep the imports it
needs — `import os, uuid`, `from google.cloud import storage as gcs` — adding them to the route module
if not already present). After this move + Task 3's Firestore swap, `utils/save_output.py` has no
remaining symbols and is deleted in Task 3.

**Update** `routes/simplify_v1_2.py:33`: drop `upload_combined_pdf` from the (former)
`from utils.save_output import ...` line — it is now a local definition, not an import. The patch target
`routes.simplify_v1_2.upload_combined_pdf` in `tests/test_simplify_v1_2_persistence.py` stays
**unchanged** (the name now resolves to the local definition on the same module path).

**Update** `tests/test_save_output.py` `upload_combined_pdf` case: patches
`utils.save_output.gcs.Client` / `utils.save_output.uuid.uuid4` / `utils.save_output.os.environ` →
`routes.simplify_v1_2.gcs.Client` / `routes.simplify_v1_2.uuid.uuid4` / `routes.simplify_v1_2.os.environ`
(new home).

**Acceptance:** `python -c "import utils.gcs"` raises `ModuleNotFoundError` (never created);
`from routes.simplify_v1_2 import upload_combined_pdf` succeeds;
`pytest tests/test_save_output.py tests/test_simplify_v1_2_persistence.py` passes; combined-PDF blob
path test still asserts `simplify/{user}/inputs/{uuid}.pdf`.

---

### Task 9 — Create `utils/llm.py`; consolidate LLM client; delete `gemini_client.py`

**Create** `utils/llm.py` with `LLMClient` (PRD §4.4). Lift logic, behavior-identical:
- `__init__(model_name=None)`: default `model_name` to `os.environ.get("VERTEX_AI_MODEL",
  "gemini-1.5-pro")`. If `GEMINI_API_KEY` is set → Gemini API path (port `GeminiAPIClient.__init__`
  from `utils/gemini_client.py`: `genai.configure`, `genai.GenerativeModel`). Else → Vertex path (port
  v1_2 `__init__` lines 73-88: `vertexai.init`, `GenerativeModel`, the BLOCK_NONE safety dict).
- `generate_text(prompt, temperature=0.3, max_tokens=8192)`: branch on backend. Gemini path = port
  `GeminiAPIClient.generate_content` (NO safety, NO max-tokens check — preserve this asymmetry).
  Vertex path = port v1_2 `_generate_text` lines 102-122 (safety settings, MAX_TOKENS warn, return
  `response.text.strip()`).
- `generate_json(prompt, temperature=0.2, max_tokens=8192)`: port v1_2 `_generate_json` (124-135) +
  the module-level `_strip_json_fences` (54-57) into `utils/llm.py`.

**Update pipelines:**
- `simplify/v1_2/pipeline.py`: remove inline `vertexai` imports (26-33) and lazy
  `from utils.gemini_client import GeminiAPIClient` (69); replace `__init__` backend-selection block
  (63-88) with `self._llm = LLMClient()`; replace `_generate_text` (90-122) and `_generate_json`
  (124-135) bodies with delegation to `self._llm`. Remove now-unused `_strip_json_fences` from the
  pipeline.
- `simplify/v1/pipeline.py` and `simplify/v1_1/pipeline.py`: replace inline Vertex `__init__` +
  `_generate_text` with `self._llm = LLMClient()` and delegation. **No `force_vertex` flag** (OQ-3
  resolved). These pipelines are slated for removal in SP2 — if they are already gone when SP3 lands,
  skip them entirely; do not add special handling for their Vertex-only behavior.

**[RESOLVED OQ-3 — PRD §4.4, §9]:** Keep Gemini (one LLM path is good); do not worry about v1/v1_1
behavior (they're being removed). `LLMClient` mirrors v1_2 verbatim — no `force_vertex` flag is added.

**Delete** `utils/gemini_client.py`.

**Acceptance:**
- `python -c "from utils.llm import LLMClient"` succeeds.
- `python -c "import utils.gemini_client"` raises `ModuleNotFoundError`.
- `pytest tests/test_simplify_pipeline_executors.py` passes (patch `utils.llm.LLMClient`).
- No `import vertexai` or `from vertexai...` remains in the three pipeline files (grep clean).

---

### Task 10 — Tests for consolidated utils

Implement PRD §7 in full:
- `tests/test_pdf.py` (rename/extend `test_pdf_merge.py`): keep merge cases + add
  `extract_text_from_pdf` cases (2-page fixture → joined text; empty/imageless PDF → `""`).
- `tests/test_firebase.py`: `initialize_firebase` idempotency + JSON-cred branch; `firestore_client`
  database-id; `get_owned_doc_or_403` 404/403/success; `save_simplify_output` strips `raw` + tz-aware
  datetimes + batch metadata (port from `test_save_output.py`).
- `upload_combined_pdf` blob path coverage (`simplify/{user}/inputs/{uuid}.pdf`): **no `tests/test_gcs.py`**
  (no `utils/gcs.py` exists). Keep this assertion in `tests/test_save_output.py`'s `upload_combined_pdf`
  case, retargeted to its new home `routes.simplify_v1_2.*` (per Task 8).
- `tests/test_llm.py`: Gemini-path selection (GEMINI_API_KEY set, `google.generativeai` mocked);
  Vertex-path selection (mocked `vertexai`/`GenerativeModel`, safety applied, MAX_TOKENS warns);
  `generate_json` fenced + raw parse, `ValueError` on bad JSON.
- `tests/test_dead_code_removed.py`: assert `import` of `utils.vertex_ai`, `utils.ocr`,
  `utils.storage`, `utils.pdf_extract`, `utils.pdf_merge`, `utils.gemini_client`, `utils.auth`,
  `utils.save_output` each raise `ModuleNotFoundError`.

**Acceptance:** `pytest` (full suite) green. SP6 wires broader CI; SP3 ships these unit tests.

---

## Summary of what requires you (not a dev agent)

**Nothing outstanding — all prior decisions are resolved by the owner (PRD §8, §9).** Recorded:

1. **Task 6:** delete `utils/storage.py` (`StorageService`) — **RESOLVED: yes, delete.**
2. **Task 5:** delete `utils/ocr.py` — **RESOLVED: yes, delete.**
3. **Task 9 / OQ-3:** v1/v1_1 Gemini fallback — **RESOLVED: no `force_vertex` flag; v1/v1_1 being
   removed anyway, don't worry about them. `LLMClient` mirrors v1_2 verbatim.**
4. **Task 8:** GCS module — **RESOLVED: no `utils/gcs.py`. `upload_combined_pdf` moves into
   `routes/simplify_v1_2.py` (sole caller). No route-GCS migration.**
5. **Module name:** **RESOLVED: `utils/llm.py`.**
6. **Landing order vs SP2:** **RESOLVED: SP3's import-swaps land before SP2's route consolidation.**
7. **Transitional re-exports:** **RESOLVED: none. No `config.initialize_firebase` re-export (`app.py`
   + container-startup test repoint directly to `utils.firebase`); `utils/auth.py` deleted outright.**
