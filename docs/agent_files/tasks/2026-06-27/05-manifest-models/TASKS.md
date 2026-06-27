# Tasks: SP5 — Athena Manifest Models

**Sub-project:** SP5
**Branch:** `athena_health_part1`
**PRD source:** `docs/agent_files/tasks/2026-06-27/05-manifest-models/PRD.md`
**Fresh authoring** — no prior TASKS.md existed.
**Must run AFTER:** SP3 Tasks 1, 2, and 6

---

### Task 1 — Create `backend/models/athena_manifest.py`

**No dependencies within SP5. Must be completed before Tasks 2 and 5.**

- **Files:** `/root/projects/juno/backend/models/athena_manifest.py` *(new file)*

- **Changes:** Create the file from scratch. Do not import from `backend/models/athena.py` (that file covers live Athena API responses; this file covers static manifest config). The file defines four Pydantic v2 `BaseModel` classes and one Union type alias.

  ```python
  # backend/models/athena_manifest.py
  from __future__ import annotations

  from typing import Literal, Optional

  from pydantic import BaseModel, ConfigDict


  class AthenaEncounterManifestEntry(BaseModel):
      model_config = ConfigDict(extra="ignore")

      id: str
      label: str
      practice_id: str
      patient_id: str
      encounter_id: str
      api_path: str
      is_preview: bool
      preview_content: Optional[str] = None


  class AthenaEncounterManifest(BaseModel):
      model_config = ConfigDict(extra="ignore")

      source_kind: Literal["athena_encounter"]
      label: str
      tab_id: str
      preview_entry_id: str
      entries: list[AthenaEncounterManifestEntry]


  class AthenaClinicalDocManifestEntry(BaseModel):
      model_config = ConfigDict(extra="ignore")

      id: str
      label: str
      practice_id: str
      patient_id: str
      document_id: str
      api_path: str
      is_preview: bool
      preview_content: Optional[str] = None


  class AthenaClinicalDocManifest(BaseModel):
      model_config = ConfigDict(extra="ignore")

      source_kind: Literal["athena_clinical_doc"]
      label: str
      tab_id: str
      preview_entry_id: str
      entries: list[AthenaClinicalDocManifestEntry]


  AthenaManifest = AthenaEncounterManifest | AthenaClinicalDocManifest
  ```

  Design notes:
  - `ConfigDict(extra="ignore")` on all four models — future manifest fields are silently tolerated rather than raising `ValidationError`.
  - `source_kind` is typed as `Literal[...]` on each manifest-level model. Pydantic rejects a manifest with the wrong kind at validation time, before entries are inspected.
  - `encounter_id` is exclusive to `AthenaEncounterManifestEntry`; `document_id` is exclusive to `AthenaClinicalDocManifestEntry`. The two entry types are intentionally distinct — do not merge them.
  - All ID fields (`practice_id`, `patient_id`, `encounter_id`, `document_id`) are `str`. The manifest JSON stores them as strings and the API paths embed them as strings.
  - `preview_content: Optional[str] = None` handles entries where the field is `null` in JSON.
  - `AthenaManifest = AthenaEncounterManifest | AthenaClinicalDocManifest` is a plain Union type alias (not a discriminated union class). No `Annotated` or `Field(discriminator=...)` is needed here.

- **Acceptance criteria:**
  ```bash
  cd /root/projects/juno/backend
  python -c "
  from models.athena_manifest import (
      AthenaEncounterManifestEntry,
      AthenaEncounterManifest,
      AthenaClinicalDocManifestEntry,
      AthenaClinicalDocManifest,
      AthenaManifest,
  )

  # Valid encounter manifest round-trips correctly
  m = AthenaEncounterManifest.model_validate({
      'source_kind': 'athena_encounter',
      'label': 'Test',
      'tab_id': 'enc',
      'preview_entry_id': 'e1',
      'entries': [{
          'id': 'e1', 'label': 'E1', 'practice_id': '1',
          'patient_id': '2', 'encounter_id': '3',
          'api_path': '/v1/1/chart/encounters/3/summary',
          'is_preview': True, 'preview_content': None,
      }],
  })
  assert m.source_kind == 'athena_encounter'
  assert m.entries[0].encounter_id == '3'

  # Valid clinical doc manifest round-trips correctly
  d = AthenaClinicalDocManifest.model_validate({
      'source_kind': 'athena_clinical_doc',
      'label': 'Docs',
      'tab_id': 'doc',
      'preview_entry_id': 'd1',
      'entries': [{
          'id': 'd1', 'label': 'D1', 'practice_id': '1',
          'patient_id': '2', 'document_id': '99',
          'api_path': '/v1/1/patients/2/documents/99',
          'is_preview': True, 'preview_content': 'text',
      }],
  })
  assert d.entries[0].document_id == '99'
  print('OK')
  "
  ```
  Must print `OK` with no errors.

---

### Task 2 — Update `_load_athena_sources()` in `backend/routes/datasets.py`

**Depends on Task 1 completing first. Also requires SP3 Task 6 to have already added `_load_athena_sources()` to this file — do not implement this task before SP3 Task 6 is done.**

- **Files:** `/root/projects/juno/backend/routes/datasets.py`

- **Changes:** After SP3 Task 6, the file contains the following raw-`json.load()` implementation of `_load_athena_sources()`:

  **Current state (post-SP3 Task 6):**
  ```python
  import json
  from pathlib import Path

  from flask import Blueprint, jsonify

  from routes.care_plan import _extract_text_from_bytes
  from utils.firebase import verify_firebase_token
  from utils.preset_data import list_datasets, read_dataset_file, GCSFetchRequired

  datasets_bp = Blueprint("datasets", __name__)

  # Resolved relative to this file: backend/routes/../data/ = backend/data/
  DATA_DIR = Path(__file__).resolve().parent.parent / "data"

  _ATHENA_MANIFEST_NAMES = [
      "athena-encounters-manifest.json",
      "athena-clinicaldocs-manifest.json",
  ]


  def _load_athena_sources() -> list[dict]:
      """Load Athena source manifests from backend/data/. Missing files are silently skipped."""
      sources = []
      for name in _ATHENA_MANIFEST_NAMES:
          path = DATA_DIR / name
          if path.is_file():
              with path.open("r", encoding="utf-8") as f:
                  sources.append(json.load(f))
      return sources
  ```

  Apply the following changes:

  1. **Add imports** after the existing `import json` / `from pathlib import Path` block — add `import logging` and `from pydantic import ValidationError` and `from models.athena_manifest import AthenaEncounterManifest, AthenaClinicalDocManifest`.

  2. **Add a module-level logger** immediately after the import block (before `datasets_bp`):
     ```python
     logger = logging.getLogger(__name__)
     ```

  3. **Add `_SOURCE_KIND_MODEL_MAP`** after `_ATHENA_MANIFEST_NAMES`:
     ```python
     _SOURCE_KIND_MODEL_MAP = {
         "athena_encounter": AthenaEncounterManifest,
         "athena_clinical_doc": AthenaClinicalDocManifest,
     }
     ```

  4. **Replace the body of `_load_athena_sources()`** with the validated implementation. The function signature and docstring change too:

  **Old `_load_athena_sources` body:**
  ```python
  def _load_athena_sources() -> list[dict]:
      """Load Athena source manifests from backend/data/. Missing files are silently skipped."""
      sources = []
      for name in _ATHENA_MANIFEST_NAMES:
          path = DATA_DIR / name
          if path.is_file():
              with path.open("r", encoding="utf-8") as f:
                  sources.append(json.load(f))
      return sources
  ```

  **New `_load_athena_sources` body:**
  ```python
  def _load_athena_sources() -> list[dict]:
      """Load and validate Athena source manifests from backend/data/.

      Missing files are silently skipped. Files with an unknown source_kind or a
      Pydantic validation error are logged as warnings and skipped — no exception
      propagates to the caller.
      """
      sources = []
      for name in _ATHENA_MANIFEST_NAMES:
          path = DATA_DIR / name
          if not path.is_file():
              continue
          with path.open("r", encoding="utf-8") as f:
              raw = json.load(f)
          source_kind = raw.get("source_kind")
          model_cls = _SOURCE_KIND_MODEL_MAP.get(source_kind)
          if model_cls is None:
              logger.warning(
                  "Skipping manifest %s: unknown source_kind %r", name, source_kind
              )
              continue
          try:
              manifest = model_cls.model_validate(raw)
          except ValidationError as exc:
              logger.warning("Skipping manifest %s: validation error — %s", name, exc)
              continue
          sources.append(manifest.model_dump())
      return sources
  ```

  The full updated file (for reference — all other routes are unchanged):
  ```python
  import json
  import logging
  from pathlib import Path

  from flask import Blueprint, jsonify
  from pydantic import ValidationError

  from models.athena_manifest import AthenaEncounterManifest, AthenaClinicalDocManifest
  from routes.care_plan import _extract_text_from_bytes
  from utils.firebase import verify_firebase_token
  from utils.preset_data import list_datasets, read_dataset_file, GCSFetchRequired

  datasets_bp = Blueprint("datasets", __name__)
  logger = logging.getLogger(__name__)

  # Resolved relative to this file: backend/routes/../data/ = backend/data/
  DATA_DIR = Path(__file__).resolve().parent.parent / "data"

  _ATHENA_MANIFEST_NAMES = [
      "athena-encounters-manifest.json",
      "athena-clinicaldocs-manifest.json",
  ]

  _SOURCE_KIND_MODEL_MAP = {
      "athena_encounter": AthenaEncounterManifest,
      "athena_clinical_doc": AthenaClinicalDocManifest,
  }


  def _load_athena_sources() -> list[dict]:
      """Load and validate Athena source manifests from backend/data/.

      Missing files are silently skipped. Files with an unknown source_kind or a
      Pydantic validation error are logged as warnings and skipped — no exception
      propagates to the caller.
      """
      sources = []
      for name in _ATHENA_MANIFEST_NAMES:
          path = DATA_DIR / name
          if not path.is_file():
              continue
          with path.open("r", encoding="utf-8") as f:
              raw = json.load(f)
          source_kind = raw.get("source_kind")
          model_cls = _SOURCE_KIND_MODEL_MAP.get(source_kind)
          if model_cls is None:
              logger.warning(
                  "Skipping manifest %s: unknown source_kind %r", name, source_kind
              )
              continue
          try:
              manifest = model_cls.model_validate(raw)
          except ValidationError as exc:
              logger.warning("Skipping manifest %s: validation error — %s", name, exc)
              continue
          sources.append(manifest.model_dump())
      return sources


  @datasets_bp.route("/care_plan/datasets", methods=["GET"])
  @verify_firebase_token
  def list_datasets_route(user_id: str):
      _ = user_id
      return jsonify({
          "datasets": list_datasets(),
          "athena_sources": _load_athena_sources(),
      })


  @datasets_bp.route(
      "/care_plan/datasets/<group>/<input_id>/<string:filename>",
      methods=["GET"],
  )
  @verify_firebase_token
  def get_dataset_file_route(user_id: str, group: str, input_id: str, filename: str):
      _ = user_id

      try:
          file_bytes = read_dataset_file(group, input_id, filename)
          content = _extract_text_from_bytes(file_bytes, filename)
      except GCSFetchRequired:
          return jsonify({"error": "On-demand GCS fetch not yet implemented (SP2)"}), 503
      except FileNotFoundError:
          return jsonify({"error": "Not found"}), 404

      return jsonify({"filename": filename, "content": content})
  ```

- **Acceptance criteria:**
  ```bash
  cd /root/projects/juno/backend
  python -c "
  import sys; sys.path.insert(0, '.')
  from routes.datasets import _load_athena_sources, _SOURCE_KIND_MODEL_MAP
  from models.athena_manifest import AthenaEncounterManifest, AthenaClinicalDocManifest

  # _SOURCE_KIND_MODEL_MAP is wired correctly
  assert _SOURCE_KIND_MODEL_MAP['athena_encounter'] is AthenaEncounterManifest
  assert _SOURCE_KIND_MODEL_MAP['athena_clinical_doc'] is AthenaClinicalDocManifest

  # With real manifest files present (after SP3 Tasks 1+2), sources load and validate
  sources = _load_athena_sources()
  assert len(sources) == 2
  assert any(s['source_kind'] == 'athena_encounter' for s in sources)
  assert any(s['source_kind'] == 'athena_clinical_doc' for s in sources)
  print('OK')
  "
  ```
  Must print `OK`. Run after SP3 Tasks 1 and 2 have created the manifest files on disk.

  Also verify that a bad manifest is skipped, not raised:
  ```bash
  cd /root/projects/juno/backend
  python -c "
  import sys; sys.path.insert(0, '.')
  import json, pathlib, tempfile, unittest.mock as mock

  # Temporarily patch _ATHENA_MANIFEST_NAMES to point at a bad file
  import routes.datasets as ds
  bad = {'source_kind': 'bad_kind', 'entries': []}
  with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
      json.dump(bad, f)
      bad_path = pathlib.Path(f.name)

  orig_dir = ds.DATA_DIR
  orig_names = ds._ATHENA_MANIFEST_NAMES
  ds.DATA_DIR = bad_path.parent
  ds._ATHENA_MANIFEST_NAMES = [bad_path.name]
  try:
      result = ds._load_athena_sources()
      assert result == [], f'Expected [], got {result}'
  finally:
      ds.DATA_DIR = orig_dir
      ds._ATHENA_MANIFEST_NAMES = orig_names
      bad_path.unlink()
  print('OK — bad manifest skipped without exception')
  "
  ```

---

### Task 3 — Append manifest interfaces to `frontend/src/types/athena.ts`

**No dependency on Tasks 1 or 2. Can run in parallel with the backend tasks.**

- **Files:** `/root/projects/juno/frontend/src/types/athena.ts` *(existing file — append only; do not alter existing content)*

- **Changes:** The file currently ends after the `AthenaPushDocumentResponse` interface on the last line. Append the following block after the last existing export. Do not remove or modify any existing interface or comment.

  ```typescript
  // ── Manifest models (static config files, not live API responses) ──────────

  export interface AthenaEncounterManifestEntry {
    id: string;
    label: string;
    practice_id: string;
    patient_id: string;
    encounter_id: string;
    api_path: string;
    is_preview: boolean;
    preview_content: string | null;
  }

  export interface AthenaEncounterManifest {
    source_kind: "athena_encounter";
    label: string;
    tab_id: string;
    preview_entry_id: string;
    entries: AthenaEncounterManifestEntry[];
  }

  export interface AthenaClinicalDocManifestEntry {
    id: string;
    label: string;
    practice_id: string;
    patient_id: string;
    document_id: string;
    api_path: string;
    is_preview: boolean;
    preview_content: string | null;
  }

  export interface AthenaClinicalDocManifest {
    source_kind: "athena_clinical_doc";
    label: string;
    tab_id: string;
    preview_entry_id: string;
    entries: AthenaClinicalDocManifestEntry[];
  }

  export type AthenaManifest = AthenaEncounterManifest | AthenaClinicalDocManifest;
  ```

  Notes:
  - `encounter_id` is only on `AthenaEncounterManifestEntry`; `document_id` is only on `AthenaClinicalDocManifestEntry`. These are not shared fields.
  - `preview_content` is `string | null` (not `string | undefined`) to match the Pydantic `Optional[str] = None` which serializes as `null` in JSON.
  - `source_kind` on each manifest interface is a string literal type (`"athena_encounter"`, `"athena_clinical_doc"`), enabling TypeScript discriminated union narrowing on `AthenaManifest`.

- **Acceptance criteria:**
  ```bash
  cd /root/projects/juno/frontend
  npx tsc --noEmit 2>&1 | head -20
  ```
  Must produce no TypeScript errors related to `athena.ts`. Also verify by grep:
  ```bash
  grep -n "AthenaEncounterManifest\|AthenaClinicalDocManifest\|AthenaManifest" \
    /root/projects/juno/frontend/src/types/athena.ts
  ```
  Must show all five new declarations (two entry types, two manifest types, one union alias). The existing interfaces (`AthenaTokenResponse`, `AthenaClinicalDocumentMeta`, etc.) must still be present and unchanged.

---

### Task 4 — Remove inline interfaces from frontend components; import from `athena.ts`

**Depends on Task 3 completing first. Also requires SP3 to have created `PresetDataCard.tsx` and `AthenaPresetPanel.tsx` — do not implement this task before SP3 Tasks (whichever add those components) are done.**

- **Files:**
  - `/root/projects/juno/frontend/src/components/PresetDataCard.tsx`
  - `/root/projects/juno/frontend/src/components/AthenaPresetPanel.tsx`

- **Changes for `PresetDataCard.tsx`:**

  Locate the inline `AthenaSource` and `AthenaEntry` interface declarations (added by SP3). Remove both interface blocks entirely. Add the following import at the top of the file (with the other type imports):

  ```typescript
  import type { AthenaManifest, AthenaEncounterManifestEntry, AthenaClinicalDocManifestEntry } from "@/types/athena";
  ```

  Update all usages in the component body:
  - `AthenaSource` → `AthenaManifest`
  - `AthenaEntry` → `AthenaEncounterManifestEntry | AthenaClinicalDocManifestEntry`

  If `AthenaEntry` is used as a union of entry types in the component, replace it with the explicit union. If it is used as a standalone type annotation on a variable that only ever holds one kind of entry, replace with the specific type (`AthenaEncounterManifestEntry` or `AthenaClinicalDocManifestEntry`) as appropriate to the context — do not broaden unnecessarily.

  The runtime behaviour and rendered output are unchanged. Only the type source changes.

- **Changes for `AthenaPresetPanel.tsx`:**

  Apply the same pattern: remove any inline `AthenaEntry` or `AthenaSource` interface declarations. Add the import:

  ```typescript
  import type { AthenaManifest, AthenaEncounterManifestEntry, AthenaClinicalDocManifestEntry } from "@/types/athena";
  ```

  Update all type annotations accordingly.

- **Acceptance criteria:**
  ```bash
  cd /root/projects/juno/frontend
  npx tsc --noEmit 2>&1 | head -30
  ```
  Must produce zero TypeScript errors. Also verify no inline interface declarations remain:
  ```bash
  grep -n "interface AthenaSource\|interface AthenaEntry" \
    /root/projects/juno/frontend/src/components/PresetDataCard.tsx \
    /root/projects/juno/frontend/src/components/AthenaPresetPanel.tsx
  ```
  Must return no matches. And verify the import is present in both files:
  ```bash
  grep -n "from \"@/types/athena\"" \
    /root/projects/juno/frontend/src/components/PresetDataCard.tsx \
    /root/projects/juno/frontend/src/components/AthenaPresetPanel.tsx
  ```
  Must show a match in each file.

---

### Task 5 — Add `backend/tests/models/test_athena_manifest.py`

**Depends on Tasks 1 and 2 completing first. Also requires SP3 Tasks 1 and 2 to have created the manifest JSON files on disk at `backend/data/athena-encounters-manifest.json` and `backend/data/athena-clinicaldocs-manifest.json`.**

- **Files:** `/root/projects/juno/backend/tests/models/test_athena_manifest.py` *(new file)*

- **Changes:** Create the file with the following six tests:

  ```python
  # backend/tests/models/test_athena_manifest.py
  """Unit and integration tests for backend/models/athena_manifest.py."""
  from __future__ import annotations

  import json
  import pathlib
  import tempfile
  from unittest import mock

  import pytest
  from pydantic import ValidationError

  from models.athena_manifest import (
      AthenaClinicalDocManifest,
      AthenaEncounterManifest,
      AthenaEncounterManifestEntry,
  )

  # Resolve paths relative to this file's location so tests work regardless of cwd.
  _BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
  _DATA_DIR = _BACKEND_DIR / "data"


  # ---------------------------------------------------------------------------
  # test_encounters_manifest_parses
  # ---------------------------------------------------------------------------

  def test_encounters_manifest_parses():
      """The encounters manifest JSON on disk parses through AthenaEncounterManifest."""
      manifest_path = _DATA_DIR / "athena-encounters-manifest.json"
      assert manifest_path.is_file(), (
          f"Manifest file not found: {manifest_path}. "
          "Run SP3 Tasks 1 and 2 before this test."
      )
      with manifest_path.open("r", encoding="utf-8") as f:
          raw = json.load(f)

      manifest = AthenaEncounterManifest.model_validate(raw)

      assert manifest.source_kind == "athena_encounter"
      assert len(manifest.entries) >= 1
      first = manifest.entries[0]
      assert first.encounter_id  # non-empty string
      assert first.practice_id   # non-empty string


  # ---------------------------------------------------------------------------
  # test_clinical_docs_manifest_parses
  # ---------------------------------------------------------------------------

  def test_clinical_docs_manifest_parses():
      """The clinical docs manifest JSON on disk parses through AthenaClinicalDocManifest."""
      manifest_path = _DATA_DIR / "athena-clinicaldocs-manifest.json"
      assert manifest_path.is_file(), (
          f"Manifest file not found: {manifest_path}. "
          "Run SP3 Tasks 1 and 2 before this test."
      )
      with manifest_path.open("r", encoding="utf-8") as f:
          raw = json.load(f)

      manifest = AthenaClinicalDocManifest.model_validate(raw)

      assert manifest.source_kind == "athena_clinical_doc"
      assert len(manifest.entries) >= 1
      first = manifest.entries[0]
      assert first.document_id  # non-empty string
      assert first.patient_id   # non-empty string


  # ---------------------------------------------------------------------------
  # test_invalid_source_kind_raises
  # ---------------------------------------------------------------------------

  def test_invalid_source_kind_raises():
      """AthenaEncounterManifest rejects a dict with the wrong source_kind."""
      data = {
          "source_kind": "athena_unknown",
          "label": "Test",
          "tab_id": "x",
          "preview_entry_id": "e1",
          "entries": [],
      }
      with pytest.raises(ValidationError):
          AthenaEncounterManifest.model_validate(data)


  # ---------------------------------------------------------------------------
  # test_encounter_entry_missing_encounter_id_raises
  # ---------------------------------------------------------------------------

  def test_encounter_entry_missing_encounter_id_raises():
      """AthenaEncounterManifestEntry requires encounter_id; omitting it raises ValidationError."""
      data = {
          "id": "e1",
          "label": "Entry 1",
          "practice_id": "195900",
          "patient_id": "60183",
          # encounter_id intentionally omitted
          "api_path": "/v1/195900/chart/encounters/62021/summary",
          "is_preview": False,
      }
      with pytest.raises(ValidationError):
          AthenaEncounterManifestEntry.model_validate(data)


  # ---------------------------------------------------------------------------
  # test_extra_fields_are_ignored
  # ---------------------------------------------------------------------------

  def test_extra_fields_are_ignored():
      """Extra keys in a manifest dict are silently dropped (ConfigDict extra='ignore')."""
      data = {
          "source_kind": "athena_encounter",
          "label": "Test",
          "tab_id": "enc",
          "preview_entry_id": "e1",
          "entries": [{
              "id": "e1",
              "label": "Entry 1",
              "practice_id": "195900",
              "patient_id": "60183",
              "encounter_id": "62021",
              "api_path": "/v1/195900/chart/encounters/62021/summary",
              "is_preview": True,
              "preview_content": None,
          }],
          "metadata": {"version": 1},  # extra field — should be ignored
      }
      manifest = AthenaEncounterManifest.model_validate(data)
      dumped = manifest.model_dump()
      assert "metadata" not in dumped, "Extra field 'metadata' must be absent from model_dump()"
      assert manifest.label == "Test"


  # ---------------------------------------------------------------------------
  # test_load_athena_sources_skips_invalid_manifest  (integration)
  # ---------------------------------------------------------------------------

  def test_load_athena_sources_skips_invalid_manifest(caplog):
      """_load_athena_sources() skips a manifest with an unknown source_kind and logs a warning."""
      import routes.datasets as ds

      bad_manifest = {"source_kind": "bad_kind", "entries": []}

      with tempfile.NamedTemporaryFile(
          mode="w", suffix=".json", dir=str(_DATA_DIR), delete=False
      ) as tmp:
          json.dump(bad_manifest, tmp)
          tmp_path = pathlib.Path(tmp.name)

      orig_data_dir = ds.DATA_DIR
      orig_names = ds._ATHENA_MANIFEST_NAMES
      ds.DATA_DIR = tmp_path.parent
      ds._ATHENA_MANIFEST_NAMES = [tmp_path.name]

      try:
          import logging
          with caplog.at_level(logging.WARNING, logger="routes.datasets"):
              result = ds._load_athena_sources()
      finally:
          ds.DATA_DIR = orig_data_dir
          ds._ATHENA_MANIFEST_NAMES = orig_names
          tmp_path.unlink()

      assert result == [], f"Expected empty list, got: {result}"
      assert any("bad_kind" in record.message for record in caplog.records), (
          "Expected a warning mentioning 'bad_kind' in caplog"
      )
  ```

- **Acceptance criteria:**
  ```bash
  cd /root/projects/juno/backend
  python -m pytest tests/models/test_athena_manifest.py -v 2>&1
  ```
  All six tests must pass:
  - `test_encounters_manifest_parses` — PASSED
  - `test_clinical_docs_manifest_parses` — PASSED
  - `test_invalid_source_kind_raises` — PASSED
  - `test_encounter_entry_missing_encounter_id_raises` — PASSED
  - `test_extra_fields_are_ignored` — PASSED
  - `test_load_athena_sources_skips_invalid_manifest` — PASSED

  Zero failures, zero errors. If `test_encounters_manifest_parses` or `test_clinical_docs_manifest_parses` fails with "Manifest file not found", the SP3 manifest files have not been created yet — complete SP3 Tasks 1 and 2 first.
