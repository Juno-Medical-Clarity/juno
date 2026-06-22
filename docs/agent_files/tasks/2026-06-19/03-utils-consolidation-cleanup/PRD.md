# PRD: Utils Consolidation & Dead-Code Cleanup

Sub-project 3 (SP3) of the Juno backend refactor. **Phase 1.** Depends on **SP1** (Pydantic
models — the persisted output shape that `save_output.py` writes). Coordinates import paths with
**SP2** (route consolidation + `simplify` → `care_plan` rename). Coordinates with **SP4** for the
logging doc (SP4 owns `docs/logging.md`; SP3 only deletes the stale `utils/LOGGING.md`).

All claims of "dead code" in this PRD are backed by `grep` evidence captured against the working tree
on the `fixing-cors` branch (see §4 per-module evidence blocks and §9).

## 1. Problem

`backend/utils/` has accreted into a grab-bag of overlapping and orphaned modules:

- **Two PDF modules.** `utils/pdf_extract.py` (extract text from a PDF, via `PyPDF2`) and
  `utils/pdf_merge.py` (merge PDF/TXT bytes into one PDF, via `pypdf` + `reportlab`) are separate
  single-function files that are always used together by the simplify routes.
- **Firebase/Firestore logic is scattered across six files.** Initialization lives in `config.py`;
  the Firestore client factory is re-implemented (`_db()`) in `routes/saved_outputs.py` and
  `routes/grading.py`; persistence helpers live in `utils/save_output.py`; token verification lives
  in `utils/auth.py`. Each route re-derives the database id and re-creates the client. There is no
  single home for "talk to Firebase."
- **Dead LLM code.** `utils/vertex_ai.py` (`VertexAIService`) is imported nowhere, references a
  `summarySchema/` directory that does not exist, and its public methods (`generate_questions`,
  `process_transcript_to_soap`) are called nowhere.
- **Duplicated live LLM code.** The real LLM client logic is duplicated inline across three pipeline
  files (`simplify/v1/pipeline.py`, `simplify/v1_1/pipeline.py`, `simplify/v1_2/pipeline.py`), and
  `utils/gemini_client.py` (`GeminiAPIClient`) is the only "library" piece — but it is imported
  *lazily inside* the v1_2 pipeline's `__init__`, not by v1 or v1_1.
- **Two more orphaned modules.** `utils/ocr.py` (Cloud Vision OCR) and `utils/storage.py`
  (`StorageService`) are each imported nowhere outside their own definition.
- **Stale doc.** `utils/LOGGING.md` duplicates content that now lives in `docs/logging.md` (SP4's
  home).

Result: editing "how Juno saves an output" or "how Juno calls the LLM" means touching 3–6 files, and
several modules are pure dead weight that confuses readers and inflates the dependency surface.

## 2. Goals

1. **One PDF module.** Merge `pdf_extract.py` + `pdf_merge.py` → `utils/pdf.py`, preserving both used
   functions verbatim; update the 4 import sites + 3 test patch targets.
2. **One Firebase module.** Create `utils/firebase.py` as the single home for: Firebase Admin init,
   the Firestore client factory, Firestore persistence helpers (the `save_output.py` functions), the
   ownership-check helper currently duplicated in two routes, and the auth-token decorator. Update
   every import site. Keep GCS object I/O *out* of this module (see §4 — GCS vs Firestore split).
3. **One LLM module.** Delete dead `utils/vertex_ai.py`; extract the live inline Vertex client logic +
   `utils/gemini_client.py` into a single `utils/llm.py` with one client class that picks Gemini API
   (primary, if `GEMINI_API_KEY` set) or Vertex `GenerativeModel` (fallback) — mirroring v1_2's
   current behavior. Pipelines call the shared client instead of inlining.
4. **OCR decision.** `utils/ocr.py` is unused (grep-verified). Delete it.
5. **Remove `utils/LOGGING.md`.** `docs/logging.md` is the home (owned by SP4).
6. **Tests for all utils.** Add/extend unit tests so every consolidated util module has coverage; keep
   the existing tests green by updating their import / patch targets.

## 3. Non-Goals

- **No external HTTP API change.** No route's URL, method, request body, or response shape changes.
  (Confirmed in §5.)
- **No frontend change.** (Confirmed in §6.)
- **Not restructuring observability.** `utils/juno_logger.py` and `utils/juno_metrics.py` are SP4's;
  SP3 does not touch them beyond deleting `utils/LOGGING.md`.
- **Not the `simplify` → `care_plan` rename.** That is SP2. SP3 publishes the new util import paths so
  SP2 (and the pipelines) can adopt them; SP3 does not rename `simplify/` itself.
- **Not changing pipeline prompts, scoring, term detection, or output JSON shape.** Pure relocation of
  LLM *client* plumbing; prompt strings and generation params are copied unchanged.
- **Not converting models to Pydantic.** That is SP1. SP3 must not alter the persisted document shape
  written by `save_simplify_output` (see §4 assumption).

## 4. Architecture Decisions

### 4.1 Old path → new path (master table)

| Old location | Symbol(s) | New location |
|---|---|---|
| `utils/pdf_extract.py` | `extract_text_from_pdf` | `utils/pdf.py` |
| `utils/pdf_merge.py` | `merge_pdfs` (+ private `_txt_to_pdf`, `_append_pdf`) | `utils/pdf.py` |
| `config.py` | `initialize_firebase` | `utils/firebase.py` (NO re-export; `app.py` + test repointed — see 4.3) |
| `utils/save_output.py` | `save_simplify_output`, `_without_raw` | `utils/firebase.py` (Firestore) |
| `utils/save_output.py` | `upload_combined_pdf` | `routes/simplify_v1_2.py` (its sole caller — no `utils/gcs.py`; see 4.3) |
| `utils/auth.py` | `verify_firebase_token` | `utils/firebase.py` |
| `routes/saved_outputs.py` | `_db`, `_get_doc_or_403` | `utils/firebase.py` (`firestore_client`, `get_owned_doc_or_403`) |
| `routes/grading.py` | `_db`, `_get_doc_or_403` (duplicate) | use `utils/firebase.py` (delete the duplicates) |
| `utils/vertex_ai.py` | `VertexAIService`, `MaxTokensError` | **DELETED** (dead) |
| `utils/gemini_client.py` | `GeminiAPIClient` | `utils/llm.py` |
| `simplify/v1_2/pipeline.py` (inline Vertex client + Gemini switch in `__init__` / `_generate_text`) | — | `utils/llm.py` (`LLMClient`) |
| `simplify/v1/pipeline.py`, `simplify/v1_1/pipeline.py` (inline Vertex client) | — | `utils/llm.py` (`LLMClient`) |
| `utils/ocr.py` | `ocr_image`, `ocr_pdf`, `ocr_pdf_gcs` | **DELETED** (dead — owner confirmed) |
| `utils/storage.py` | `StorageService` | **DELETED** (dead — owner confirmed, see 4.6) |
| `utils/LOGGING.md` | — | **DELETED** (home is `docs/logging.md`, SP4) |

> **Naming choice: `utils/llm.py`, not `utils/gemini.py`.** The module holds *both* the Gemini API
> client and the Vertex fallback, and is the seam where future providers would plug in. A
> provider-neutral name (`llm.py`) is more honest than `gemini.py`. See 4.4 for the owner's question.

### 4.2 `utils/pdf.py` — the merged PDF module

Straight concatenation of the two files. Both source files already use the standard logging module and
have no name collisions. The merged module exposes exactly:

```python
def extract_text_from_pdf(pdf_content: bytes) -> str: ...   # from pdf_extract.py (PyPDF2)
def merge_pdfs(file_list: list[tuple[bytes, str]]) -> bytes: ...  # from pdf_merge.py (pypdf+reportlab)
# private helpers _txt_to_pdf, _append_pdf carried over unchanged
```

Keep both imports (`import PyPDF2` for extract; `from pypdf import PdfReader, PdfWriter` for merge) —
they are different libraries used by different functions; do **not** try to unify them in this SP (out
of scope, behavior-risk).

**Import sites to update (4 source + 3 test-patch targets):**

| File | Current | New |
|---|---|---|
| `routes/simplify.py:30` | `from utils.pdf_extract import extract_text_from_pdf` | `from utils.pdf import extract_text_from_pdf` |
| `routes/simplify_v1_1.py:30` | `from utils.pdf_extract import extract_text_from_pdf` | `from utils.pdf import extract_text_from_pdf` |
| `routes/simplify_v1_2.py:31-32` | `from utils.pdf_merge import merge_pdfs` / `from utils.pdf_extract import extract_text_from_pdf` | `from utils.pdf import merge_pdfs, extract_text_from_pdf` |
| `tests/test_pdf_merge.py:24,37,39` | `from utils.pdf_merge import merge_pdfs`; `assertLogs("utils.pdf_merge", ...)` | `from utils.pdf import merge_pdfs`; `assertLogs("utils.pdf", ...)` |

Note: `tests/test_simplify_v1_2_persistence.py` patches `routes.simplify_v1_2.merge_pdfs` (the name as
bound *in the route module*). Because the route still does `from utils.pdf import merge_pdfs`, the
patch target `routes.simplify_v1_2.merge_pdfs` is **unchanged** — only the route's import line moves.
This is why the route must use `from utils.pdf import merge_pdfs` (binding the name locally), not
`import utils.pdf`.

**Evidence (grep):**
```
routes/simplify.py:30:        from utils.pdf_extract import extract_text_from_pdf
routes/simplify_v1_1.py:30:     from utils.pdf_extract import extract_text_from_pdf
routes/simplify_v1_2.py:31-32:  from utils.pdf_merge import merge_pdfs / from utils.pdf_extract import extract_text_from_pdf
tests/test_pdf_merge.py:24,37:  from utils.pdf_merge import merge_pdfs
tests/test_simplify_v1_2_persistence.py:122,181,266: @patch("routes.simplify_v1_2.merge_pdfs", ...)
```
No other references exist.

### 4.3 `utils/firebase.py` — the consolidated Firebase/Firestore module

**Proposed public API:**

```python
# utils/firebase.py
def initialize_firebase() -> "firestore.Client":
    """Init Firebase Admin (idempotent) and return a Firestore client for the configured DB.
       Moved verbatim from config.py."""

def firestore_client() -> "firestore.Client":
    """Return a Firestore client for FIRESTORE_DATABASE_ID (default '(default)').
       Replaces the duplicated _db() helpers in saved_outputs.py and grading.py."""

def verify_firebase_token(f):
    """Auth decorator. Moved verbatim from utils/auth.py (still uses firebase_admin.auth)."""

def get_owned_doc_or_403(db, collection: str, doc_id: str, user_id: str):
    """Fetch a doc, 404 if missing, 403 if uid != user_id. Returns (doc, None) or (None, error).
       Generalizes the identical _get_doc_or_403 duplicated in saved_outputs.py and grading.py
       (both hard-code collection 'simplify_outputs' — pass it explicitly so it's reusable)."""

def save_simplify_output(*, user_id, name, source_filename, input_pdf_gcs, output_data,
                         dataset_group=None, batch_group_id=None) -> str:
    """Persist a simplify output document to Firestore. Moved verbatim from save_output.py."""
```

**GCS vs Firestore split (RESOLVED by owner — no `utils/gcs.py`).** `utils/save_output.py` currently
mixes two concerns: `save_simplify_output` (Firestore write) and `upload_combined_pdf` (GCS upload).
`firebase.py` owns **Firestore-only** logic.

- **Decision (owner-directed clean-up):** `save_simplify_output` and `_without_raw` move into
  `utils/firebase.py`. **`upload_combined_pdf` is relocated into `routes/simplify_v1_2.py`** — its sole
  caller — rather than into a new `utils/gcs.py`. The owner directed `utils/gcs.py: DELETE`, i.e. do
  not create a standalone one-function GCS utility module. Inlining `upload_combined_pdf` at its only
  call site removes the last reason for `utils/save_output.py` to exist (which is then deleted).
- The dead `StorageService` in `utils/storage.py` is deleted (4.6). No GCS helper module is created.
- **Route-inline GCS migration is dropped** (was OQ-2's optional sub-question): with no `utils/gcs.py`
  target, the `_fetch_from_gcs` / signed-URL blocks simply stay where they are. SP2 can revisit GCS
  organization if it wants; SP3 does not.

**`config.py` after the move.** `config.py` still loads `.env` and exposes the config constants
(`GCP_PROJECT_ID`, `VERTEX_AI_MODEL`, etc.). Per the owner directive (no one-line wrapper/re-export
modules), `config.py` does **NOT** re-export `initialize_firebase`. Instead the two consumers are
repointed directly to `utils.firebase`:

- `app.py:11` → `from utils.firebase import initialize_firebase` (one-line edit; not a wrapper).
- `tests/test_container_startup.py:16,44` → `patch("utils.firebase.initialize_firebase", ...)`.

This deletes the `initialize_firebase` definition from `config.py` outright with no shim.

**Import sites to update:**

| File | Current | New |
|---|---|---|
| `app.py:11` | `from config import initialize_firebase` | `from utils.firebase import initialize_firebase` |
| `tests/test_container_startup.py:16,44` | `patch("config.initialize_firebase", ...)` | `patch("utils.firebase.initialize_firebase", ...)` |
| `routes/saved_outputs.py:21` | `from utils.auth import verify_firebase_token` | `from utils.firebase import verify_firebase_token, firestore_client, get_owned_doc_or_403` |
| `routes/saved_outputs.py:34-48` | local `_db()` / `_get_doc_or_403()` | **delete**, call `firestore_client()` / `get_owned_doc_or_403(db, "simplify_outputs", ...)` |
| `routes/grading.py:9` | `from utils.auth import verify_firebase_token` | `from utils.firebase import verify_firebase_token, firestore_client, get_owned_doc_or_403` |
| `routes/grading.py:17-30` | local `_db()` / `_get_doc_or_403()` | **delete**, use the shared helpers |
| `routes/simplify.py:28` | `from utils.auth import verify_firebase_token` | `from utils.firebase import verify_firebase_token` |
| `routes/datasets.py:4` | `from utils.auth import verify_firebase_token` | `from utils.firebase import verify_firebase_token` |
| `routes/batch.py:15` | `from utils.auth import verify_firebase_token` | `from utils.firebase import verify_firebase_token` |
| `routes/batch.py:17` | `from utils.save_output import save_simplify_output` | `from utils.firebase import save_simplify_output` |
| `routes/simplify_v1_2.py:33` | `from utils.save_output import save_simplify_output, upload_combined_pdf` | `from utils.firebase import save_simplify_output` (and define `upload_combined_pdf` locally in this module) |
| `tests/test_save_output.py:13-78` | patches `utils.save_output.*` | retarget Firestore cases to `utils.firebase.*`; retarget `upload_combined_pdf` case to `routes.simplify_v1_2.*` (its new home) |
| `tests/test_simplify_v1_2_persistence.py:64,120,121,...` | `patch("routes.simplify_v1_2.save_simplify_output")` / `...upload_combined_pdf` | **unchanged** patch targets — `save_simplify_output` is bound locally via `from utils.firebase import ...`, and `upload_combined_pdf` is now *defined* in `routes.simplify_v1_2`, so both names resolve on the same module path |

**Evidence (grep) — current Firebase/Firestore footprint:**
```
config.py:11               def initialize_firebase()            <- init + firestore.client
config.py:13               firebase_admin._apps / initialize_app
utils/auth.py:3            from firebase_admin import auth      <- verify_firebase_token
utils/save_output.py:10    from firebase_admin import firestore <- save_simplify_output
routes/saved_outputs.py:18 from firebase_admin import firestore; _db(); _get_doc_or_403()
routes/grading.py:7        from firebase_admin import firestore; _db(); _get_doc_or_403()  (duplicate)
app.py:11/39               from config import initialize_firebase; initialize_firebase()
verify_firebase_token used by: saved_outputs, simplify, datasets, batch, grading (5 routes)
```

### 4.4 `utils/llm.py` — the single LLM client (answers the owner's question)

**Owner asked: "Isn't vertex ai and gemini together? Shouldn't they be in same file?"**

**Answer: Yes — and after this SP they are.** "Vertex AI" and "Gemini" are not two different models;
they are two different *access paths to the same Gemini models*:
- **Gemini API** (`google.generativeai`, a.k.a. Google AI Studio) — keyed by `GEMINI_API_KEY`. Simple,
  no GCP project needed. This is `utils/gemini_client.py`'s `GeminiAPIClient`.
- **Vertex AI** (`vertexai` / `GenerativeModel`) — the same Gemini models served through a GCP project,
  used when no `GEMINI_API_KEY` is present. This is the code inlined in all three pipelines and in the
  dead `vertex_ai.py`.

They belong in one file. The v1_2 pipeline already proves the pattern: its `__init__` picks
`GeminiAPIClient` if `GEMINI_API_KEY` is set, otherwise builds a Vertex `GenerativeModel`, and
`_generate_text` branches on `self._use_gemini_api`. We lift exactly that decision into one class.

**Proposed API:**

```python
# utils/llm.py
class LLMClient:
    """Single LLM client. Gemini API primary (if GEMINI_API_KEY), Vertex AI GenerativeModel fallback.
       Mirrors the current V1_2Pipeline.__init__ + _generate_text behavior exactly."""

    def __init__(self, model_name: str | None = None):
        # model_name defaults to os.environ["VERTEX_AI_MODEL"] or "gemini-1.5-pro"
        # if GEMINI_API_KEY: configure google.generativeai, build GenerativeModel (Gemini API path)
        # else: vertexai.init(project, location); build vertexai GenerativeModel (Vertex path)
        ...

    def generate_text(self, prompt: str, temperature: float = 0.3, max_tokens: int = 8192) -> str:
        """Branch on backend; for Vertex apply the shared BLOCK_NONE safety settings and the
           MAX_TOKENS warning, exactly as today. Returns response text (.strip() on Vertex path)."""
        ...

    def generate_json(self, prompt: str, temperature: float = 0.2, max_tokens: int = 8192) -> dict | list:
        """generate_text + fence-stripping + json.loads, mirroring V1_2Pipeline._generate_json."""
        ...
```

Carry over the module-level `_strip_json_fences` helper from v1_2's pipeline into `utils/llm.py`.

**Behavior-preservation notes (must mirror current code, do not "improve"):**
- The Gemini API path (`GeminiAPIClient.generate_content`) does **not** apply safety settings or do the
  MAX_TOKENS check — only the Vertex path does. Preserve that asymmetry exactly.
- v1, v1_1, v1_2 all use the same safety dict (all four categories `BLOCK_NONE`) and the same
  `model_name` resolution (`VERTEX_AI_MODEL` env, default `gemini-1.5-pro`). One client covers all.
- **[RESOLVED OQ-3] No `force_vertex` flag; do not worry about v1/v1_1.** Today only v1_2 checks
  `GEMINI_API_KEY` (grep-confirmed: the only hit is `simplify/v1_2/pipeline.py:68`); v1 and v1_1 are
  Vertex-only. The owner directive: keep Gemini (one LLM path is good), and v1/v1_1 are being removed
  anyway (SP2), so their behavior is not a concern. `LLMClient` mirrors v1_2's behavior verbatim
  (Gemini API primary if `GEMINI_API_KEY`, Vertex fallback). It is **not** given a `force_vertex` flag.
  If v1/v1_1 still exist when this lands, adopting `LLMClient` in them is fine (they simply gain the
  Gemini path); no special handling is required.

**Pipeline call-site changes:**
- `simplify/v1_2/pipeline.py`: delete the inline `__init__` backend selection (lines ~63-88), the
  `_generate_text` body (lines ~90-122), and `_generate_json` (lines ~124-135) and the
  module-level `vertexai` / `vertexai.preview.generative_models` imports + `_strip_json_fences`.
  Replace with `self._llm = LLMClient()` and delegate `_generate_text` / `_generate_json` to it.
- `simplify/v1/pipeline.py` and `simplify/v1_1/pipeline.py`: same treatment (replace inline Vertex
  client with `LLMClient`). No `force_vertex` flag (OQ-3 resolved). These pipelines are slated for
  removal in SP2; if they are already gone when SP3 lands, skip them.
- Remove the lazy `from utils.gemini_client import GeminiAPIClient` inside v1_2 `__init__`
  (lines 69-70) — `LLMClient` now owns that.

**Import sites:**
| File | Current | New |
|---|---|---|
| `simplify/v1_2/pipeline.py:26-33,69-70` | inline `vertexai` import + lazy `gemini_client` import | `from utils.llm import LLMClient` |
| `simplify/v1/pipeline.py:19-21` | inline `vertexai` import | `from utils.llm import LLMClient` |
| `simplify/v1_1/pipeline.py:26-30` | inline `vertexai` import | `from utils.llm import LLMClient` |

**Evidence (grep):**
```
utils/gemini_client.py:17   class GeminiAPIClient
simplify/v1_2/pipeline.py:69 from utils.gemini_client import GeminiAPIClient   (only importer)
simplify/v1_2/pipeline.py:26 import vertexai ; :78 GenerativeModel(...)
simplify/v1/pipeline.py:19   import vertexai ; :149 GenerativeModel(...)
simplify/v1_1/pipeline.py:26 import vertexai ; :90  GenerativeModel(...)
```

### 4.5 `utils/vertex_ai.py` — DEAD, delete

`VertexAIService` is imported by no file. Its `_create_summary_prompt` reads from a `summarySchema/`
directory that **does not exist** in the repo (verified: `ls summarySchema` → not found), so the class
would crash if ever instantiated. Its public methods (`generate_questions`,
`process_transcript_to_soap`) are called nowhere.

**Evidence (grep across `backend/`, excluding `.venv`/`__pycache__`):**
```
$ grep -rn "vertex_ai\|VertexAIService\|generate_questions\|process_transcript_to_soap"
utils/vertex_ai.py:13:class VertexAIService:        <- only the definition itself
(no other matches anywhere)
$ ls backend/summarySchema   ->  No such file or directory
```
The `VERTEX_AI_MODEL=...` lines in `.github/workflows/*.yml` are an **environment-variable name**, not
a reference to this module — unrelated to the deletion.

→ **Delete `utils/vertex_ai.py`.** (Its `MaxTokensError` symbol is also unused elsewhere — grep
confirms no importer.)

### 4.6 `utils/ocr.py` — DEAD, delete; `utils/storage.py` — DEAD, delete (bonus)

**`utils/ocr.py`:** Functions `ocr_image`, `ocr_pdf`, `ocr_pdf_gcs`. No file in `backend/` (outside
`.venv`) imports `utils.ocr` or any of its functions.

**Evidence (grep):**
```
$ grep -rln "ocr" backend/ --include="*.py" | grep -v .venv
utils/ocr.py        <- only the file itself
$ grep -rn "utils.ocr\|from utils import ocr\|ocr_image\|ocr_pdf"  (non-venv)
(no matches outside utils/ocr.py)
```
→ **Delete `utils/ocr.py` entirely** (no partial keep needed — zero functions are used).

**`utils/storage.py` (`StorageService`) — bonus dead-code finding, not on the owner's original list:**
```
$ grep -rn "StorageService" backend/ --include="*.py" | grep -v .venv
utils/storage.py:5:class StorageService:    <- only the definition itself
```
No importer anywhere. The live GCS upload used by the simplify route is the standalone
`upload_combined_pdf` in `save_output.py`, **not** this class. → **Delete `utils/storage.py`.**
**[RESOLVED: owner confirmed deletion.]** Its live counterpart `upload_combined_pdf` is relocated into
`routes/simplify_v1_2.py` (its sole caller), not into any GCS utility module (owner directed
`utils/gcs.py: DELETE`; see 4.3).

### 4.7 `utils/LOGGING.md` — remove

Stale duplicate of `docs/logging.md` (which exists and is owned by SP4). SP3 deletes
`utils/LOGGING.md` only; SP3 does not edit `docs/logging.md`.

### 4.8 Import-path contract for SP2 (`simplify` → `care_plan` rename)

So SP2 and the pipeline call sites can update in lockstep, the canonical post-SP3 util import paths
are:

```python
from utils.pdf import extract_text_from_pdf, merge_pdfs
from utils.firebase import (initialize_firebase, firestore_client,
                            verify_firebase_token, get_owned_doc_or_403, save_simplify_output)
from utils.llm import LLMClient
# upload_combined_pdf is NOT a util — it lives in routes/simplify_v1_2.py (its sole caller).
# DELETED (do not import): utils.pdf_extract, utils.pdf_merge, utils.vertex_ai,
#   utils.gemini_client, utils.ocr, utils.storage, utils.save_output, utils.auth, utils.gcs (never created)
```

`utils/auth.py` and `utils/save_output.py` are **deleted outright**; SP2 must not reintroduce imports of
them. **[RESOLVED: no transitional re-exports — owner directive. `utils/auth.py` is deleted with no
shim; `config.initialize_firebase` re-export is NOT kept (app.py and the test repoint directly).]**

### 4.9 Files shared with SP2 — merge-conflict flags

These files are touched by **both** SP3 and SP2 (route consolidation). Coordinate landing order:

| File | SP3 change | SP2 change | Mitigation |
|---|---|---|---|
| `config.py` | move `initialize_firebase` → `utils.firebase` (no re-export; delete from config) | may touch config constants / version dispatch | SP3 lands its config edit first; SP2 rebases |
| `routes/saved_outputs.py` | swap imports, delete `_db`/`_get_doc_or_403` | route consolidation / rename | land SP3's import-only change first, or SP2 absorbs it |
| `routes/grading.py` | swap imports, delete `_db`/`_get_doc_or_403` | route consolidation | same |
| `routes/simplify_v1_2.py`, `simplify.py`, `simplify_v1_1.py`, `batch.py`, `datasets.py` | import-line swaps only | larger route edits / rename | SP3's are 1-line import swaps — easiest if SP3 lands first |
| `simplify/v1_2/pipeline.py` (+ v1, v1_1) | LLM client extraction | SP2 may move under `care_plan/` | agree on order; LLM extraction is internal to the file |

**Assumption coordinated with SP1:** `save_simplify_output` writes `output_data` (with `raw` stripped
via `_without_raw`) and top-level `uid/name/.../created_at`. SP3 moves this function **verbatim** —
the persisted document shape is unchanged. If SP1's Pydantic work changes what `output_data` contains,
that is an SP1 concern that flows through the *callers*, not through `firebase.py`. SP3 does not alter
the shape.

## 5. API Change Summary

**No external API change.** Confirmed: SP3 only relocates helper modules and deletes dead code. No
route URL, HTTP method, request field, or response field changes. (`POST /simplify`, `POST
/simplify/grade`, `GET/PATCH/DELETE /simplify/saved/*`, batch and dataset routes all behave
identically.)

## 6. Frontend Change Summary

**N/A.** Confirmed: no frontend file is touched and no response shape changes, so the frontend needs no
change.

## 7. Testing (per-util test plan)

Existing tests that must stay green after retargeting imports/patch paths:
`test_pdf_merge.py`, `test_save_output.py`, `test_simplify_v1_2_persistence.py`,
`test_saved_outputs_route.py`, `test_container_startup.py`, `test_batch_route.py`,
`test_simplify_auth.py`, `test_simplify_pipeline_executors.py`.

New / updated coverage:

- **`utils/pdf.py`** — keep both `test_pdf_merge.py` cases (retargeted to `utils.pdf`); **add**
  `test_pdf_extract` cases: `extract_text_from_pdf` returns concatenated page text for a 2-page PDF
  fixture, and returns `""` for an empty/imageless PDF.
- **`utils/firebase.py`** —
  - `initialize_firebase`: idempotent (no re-init when `firebase_admin._apps` set); picks the
    `FIREBASE_SERVICE_ACCOUNT_JSON` branch when that env is set (mock `credentials.Certificate`).
  - `firestore_client`: passes `database_id` from `FIRESTORE_DATABASE_ID` (default `(default)`).
  - `get_owned_doc_or_403`: 404 when doc missing, 403 when `uid` mismatches, `(doc, None)` on success
    (port the existing ownership-check assertions from `test_saved_outputs_route.py`).
  - `save_simplify_output`: re-point `test_save_output.py`'s Firestore assertions here (strips `raw`,
    uses tz-aware datetimes, accepts batch metadata).
- **`upload_combined_pdf` (now in `routes/simplify_v1_2.py`)** — re-point `test_save_output.py`'s
  `upload_combined_pdf` case (expected `simplify/{user}/inputs/{uuid}.pdf` blob path) to
  `routes.simplify_v1_2.*` (no `utils/gcs.py` exists).
- **`utils/llm.py`** —
  - With `GEMINI_API_KEY` set (and `google.generativeai` mocked): `LLMClient()` selects the Gemini
    path; `generate_text` returns `response.text`.
  - Without `GEMINI_API_KEY` (mock `vertexai` + `GenerativeModel`): selects the Vertex path; applies
    safety settings; `generate_text` strips and returns text; MAX_TOKENS warns but returns partial.
  - `generate_json`: parses fenced ```json blocks and raw JSON; raises `ValueError` on bad JSON
    (mirror `V1_2Pipeline._generate_json`).
  - Pipeline integration: extend `test_simplify_pipeline_executors.py` so the three pipelines call
    `LLMClient.generate_text/json` (patch `utils.llm.LLMClient`) and still produce the expected output
    shape.
- **Deletion guard tests** — add a small `test_dead_code_removed.py`: assert `import utils.vertex_ai`,
  `utils.ocr`, `utils.storage`, `utils.pdf_extract`, `utils.pdf_merge` all raise `ModuleNotFoundError`
  (prevents accidental re-introduction). SP6 owns broader CI; this is a cheap local guard.

(SP6 owns the broader test reorg + CI wiring; SP3 delivers the module-level unit tests above.)

## 8. Manual Intervention Required From You

All prior open items have been resolved by the owner — no further human decision is required to
execute this SP. Recorded for the record:

1. **`utils/storage.py` (`StorageService`) deletion** — **[RESOLVED: delete. Owner confirmed.]**
2. **`utils/ocr.py` deletion** — **[RESOLVED: delete entirely. Owner confirmed.]**
3. **OQ-3 (v1/v1_1 Gemini fallback)** — **[RESOLVED: no `force_vertex` flag; v1/v1_1 are being removed
   anyway, so do not worry about them. `LLMClient` mirrors v1_2 verbatim.]**
4. **GCS module** — **[RESOLVED: `utils/gcs.py` is DELETED / not created. `upload_combined_pdf` is
   relocated into `routes/simplify_v1_2.py` (its sole caller). No route-inline-GCS migration.]**
5. **Module name** — **[RESOLVED: `utils/llm.py` (provider-neutral) is the single LLM module.]**
6. **Landing order with SP2** (§4.9) — **[RESOLVED: SP3's call. SP3's import-swaps land before SP2's
   route consolidation; SP2 rebases onto the new util paths.]**
7. **Transitional re-exports** — **[RESOLVED: none. No `config.initialize_firebase` re-export
   (`app.py` + the container-startup test repoint directly to `utils.firebase`); `utils/auth.py`
   deleted outright. Owner directive: no duplicate / one-line wrapper modules; breaking now is fine.]**

## 9. Open Questions & Decisions

- **OQ-1 — Is `utils/ocr.py` truly dead?** Resolved by grep: yes, zero importers (§4.6).
  **[RESOLVED: DELETE `utils/ocr.py`. Owner confirmed — yes, delete.]**
- **OQ-2 — GCS vs Firestore split in `firebase.py`.** Resolved: Firestore-only in `firebase.py`.
  **[RESOLVED: DELETE `utils/gcs.py` plan — owner confirmed `utils/gcs.py` is to be DELETED, not
  created. See decision note below.]** Owner directive: "utils/gcs.py: DELETE — yes." The previous
  plan created a *new* `utils/gcs.py` to home `upload_combined_pdf`; the owner has instead chosen to
  eliminate the GCS-helper module entirely. `upload_combined_pdf` is the only *live* GCS helper, used
  by exactly one route (`routes/simplify_v1_2.py`). The clean-up-first resolution: move
  `upload_combined_pdf` directly into `routes/simplify_v1_2.py` (its sole caller) so there is no
  standalone one-function utility module. The dead `StorageService` (`utils/storage.py`) is deleted
  outright. No `utils/gcs.py` is created. The optional route-inline-GCS-migration sub-question is
  therefore moot and dropped.
- **OQ-3 — v1/v1_1 gaining the Gemini-API path** (§4.4).
  **[RESOLVED: N/A — keep Gemini (one LLM path is good). v1 and v1_1 are being removed anyway (SP2),
  so do not add a `force_vertex` flag and do not worry about v1/v1_1 behavior. `LLMClient` mirrors
  v1_2's current behavior verbatim — Gemini API primary, Vertex fallback.]**
- **OQ-4 — Does any deploy/script import these modules?**
  **[RESOLVED: NO. Owner confirmed no deploy/script imports these modules. The only `.yml` hits are
  the `VERTEX_AI_MODEL` env-var name, unrelated to `vertex_ai.py`. Safe to delete.]**
- **OQ-5 — `MaxTokensError`.** Defined only in dead `vertex_ai.py`; nothing imports it.
  **[RESOLVED: proceed as proposed — drop `MaxTokensError` with the file.]**

### Owner-directed decisions (global + this SP)

- **[RESOLVED: `utils/storage.py` (`StorageService`) — DELETE. Owner confirmed yes.]**
- **[RESOLVED: `utils/ocr.py` — DELETE. Owner confirmed yes.]**
- **[RESOLVED: `utils/gcs.py` — DELETE / do-not-create. Owner confirmed yes. `upload_combined_pdf`
  is relocated into its sole caller `routes/simplify_v1_2.py`; no standalone GCS module.]**
- **[RESOLVED: `utils/llm.py` — module name confirmed (provider-neutral). It holds the single
  consolidated LLM client.]** (Owner directive listed "utils/llm.py: DELETE" referring to removing the
  *old scattered* LLM code paths; the consolidation target `utils/llm.py` is the surviving single LLM
  module per §4.4. Net effect: all duplicate/inline LLM client code is deleted; one `utils/llm.py`
  remains.)
- **[RESOLVED: No transitional re-exports. Owner directive — main goal is clean-up; no duplicate or
  one-line wrapper modules; breaking now is fine, nothing is in production.]** Consequences:
  `config.py` does **not** re-export `initialize_firebase`; instead `app.py` and
  `tests/test_container_startup.py` are repointed directly to `utils.firebase`. `utils/auth.py` is
  deleted outright (no re-export shim). See §4.3, §4.8, §8.
- **[RESOLVED: Landing order w.r.t. SP2 — SP3's call. Recommendation stands: land SP3's import-swaps
  before SP2's route consolidation/rename so SP2 rebases onto the new util paths (§4.9).]**
