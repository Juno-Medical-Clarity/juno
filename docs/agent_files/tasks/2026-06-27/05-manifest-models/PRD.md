# PRD: SP5 — Athena Manifest Models

**Sub-project:** SP5
**Branch context:** `athena_health_part1`
**Date:** 2026-06-27
**Status:** Planning — no implementation started
**Depends on:** SP3 Tasks 1+2 (manifest files on disk), SP3 Task 6 (datasets route `_load_athena_sources()`)

---

## 1. Problem

SP3 Task 6 introduces `_load_athena_sources()` in `backend/routes/datasets.py` which reads the two Athena manifest JSON files via raw `json.load()`:

```python
sources.append(json.load(f))  # raw dict, no validation
```

This approach has four concrete problems:

1. **No type safety.** The returned value is `list[dict]`, giving callers no signal about which keys exist or what their types are. Silent `KeyError` or `AttributeError` at render time is the failure mode.

2. **No validation on load.** If a manifest file is malformed (a field renamed, a value type changed, a required key removed), the error surfaces at the call site — potentially in the middle of a request — rather than at startup or at the point of reading the file.

3. **Silent schema drift.** As manifests evolve (new entries added, optional fields introduced), there is no contract enforcing that existing consumers still receive what they expect. A typo in a manifest key is invisible until it causes a frontend rendering bug.

4. **Type duplication between Python and TypeScript.** `PresetDataCard.tsx` and `AthenaPresetPanel.tsx` (added by SP3) define inline `AthenaSource` and `AthenaEntry` interfaces. These duplicate the Python-side dict structure with no shared source of truth. When the manifest schema changes, both sides must be updated manually and independently.

---

## 2. Goals

- Introduce Pydantic v2 models for both Athena manifest formats (`athena-encounters-manifest.json` and `athena-clinicaldocs-manifest.json`) in a new file `backend/models/athena_manifest.py`.
- Replace the raw `json.load()` call in `_load_athena_sources()` with model-validated parsing. Invalid manifests log a warning and are skipped (rather than crashing the request).
- Add corresponding TypeScript interfaces to `frontend/src/types/athena.ts` so frontend components import from one canonical location.
- Remove the inline `AthenaSource` and `AthenaEntry` interfaces from `PresetDataCard.tsx` and `AthenaPresetPanel.tsx`, replacing them with imports from `athena.ts`.
- Add unit tests that parse the actual manifest JSON files through the models.

---

## 3. Non-Goals

- **No changes to manifest file format.** The JSON files on disk remain exactly as SP3 wrote them. This sub-project only adds the parsing layer on top.
- **No runtime migration.** There is no existing data in a database to migrate. The manifests are static config files; this PR just validates them on load.
- **Not adding manifest models to worker logic.** The Athena worker (`backend/workers/athena_worker.py`) fetches live API data and uses the models in `backend/models/athena.py`. Manifest models are unrelated to that pipeline and must not be imported there.
- **No changes to the HTTP API contract.** The shape of `GET /care_plan/datasets` response is unchanged — `athena_sources` is still a list of JSON objects. The internal representation becomes validated dicts (via `.model_dump()`), but the wire format is identical.

---

## 4. Architecture Decisions

### 4.1 New file: `backend/models/athena_manifest.py`

This file defines four Pydantic v2 `BaseModel` classes and one Union type alias. It must not import from `backend/models/athena.py` (those models are for live API responses, not static config).

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
- `ConfigDict(extra="ignore")` on all models: future manifest fields added by SP3+ are silently tolerated rather than raising `ValidationError`. This is the correct default for static config files that may gain optional keys over time.
- `Literal["athena_encounter"]` / `Literal["athena_clinical_doc"]` on `source_kind` means Pydantic will reject a manifest with the wrong kind before the caller even inspects entries.
- `encounter_id` exists only on `AthenaEncounterManifestEntry`; `document_id` exists only on `AthenaClinicalDocManifestEntry`. These are not shared — the two entry types are intentionally distinct.
- All ID fields (`practice_id`, `patient_id`, `encounter_id`, `document_id`) are `str`, not `int`. The manifest JSON contains them as strings and the API paths embed them as strings.
- `preview_content: Optional[str] = None` covers entries where the field is `null` in JSON.

### 4.2 Modified: `backend/routes/datasets.py`

`_load_athena_sources()` switches from raw `json.load()` to model-validated parsing. Invalid files log a warning and are skipped.

**Old:**
```python
def _load_athena_sources() -> list[dict]:
    sources = []
    for name in _ATHENA_MANIFEST_NAMES:
        path = DATA_DIR / name
        if path.is_file():
            with path.open("r", encoding="utf-8") as f:
                sources.append(json.load(f))  # raw dict, no validation
    return sources
```

**New:**
```python
import logging
from pydantic import ValidationError
from models.athena_manifest import AthenaEncounterManifest, AthenaClinicalDocManifest

logger = logging.getLogger(__name__)

_SOURCE_KIND_MODEL_MAP = {
    "athena_encounter": AthenaEncounterManifest,
    "athena_clinical_doc": AthenaClinicalDocManifest,
}

def _load_athena_sources() -> list[dict]:
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

Behaviour contract:
- Missing file: silently skipped (same as before).
- Unknown `source_kind`: logs a warning, skips the file. No exception propagates.
- Valid manifest: validated, serialized to dict via `.model_dump()`, appended. Shape is identical to what `json.load()` would have returned for a well-formed file — the HTTP response is unchanged.
- Invalid manifest (field type mismatch, required field missing): logs a warning with the `ValidationError` detail, skips the file.

### 4.3 Modified: `frontend/src/types/athena.ts`

Append the following interfaces and type alias to the existing file (after the existing exports). Do not remove or alter existing interfaces.

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

### 4.4 Modified: `frontend/src/components/PresetDataCard.tsx`

Remove the inline `AthenaEntry` and `AthenaSource` interface declarations. Replace with imports:

```typescript
import type { AthenaManifest, AthenaEncounterManifestEntry, AthenaClinicalDocManifestEntry } from "@/types/athena";

// AthenaSource → AthenaManifest
// AthenaEntry  → AthenaEncounterManifestEntry | AthenaClinicalDocManifestEntry
```

Update all type annotations in the component to use the imported names. The runtime behaviour is unchanged — only the type source changes.

### 4.5 Modified: `frontend/src/components/AthenaPresetPanel.tsx`

Same pattern as `PresetDataCard.tsx`. Remove any inline `AthenaEntry` / `AthenaSource` interface declarations and import from `@/types/athena` instead.

---

## 5. API Change Summary

The `GET /care_plan/datasets` response shape is **unchanged**. Before and after this sub-project, `athena_sources` is a JSON array of objects with the same keys. The only internal change is that those objects are now produced by `.model_dump()` on a validated Pydantic model rather than returned directly from `json.load()`. Because `ConfigDict(extra="ignore")` is used, any extra fields in the manifest file are excluded from `.model_dump()` output — this is intentional and consistent with the typed contract. If any manifest currently carries undocumented extra fields that the frontend depends on, they must be added to the model before this sub-project ships.

No client-side HTTP contract change. No version bump needed.

---

## 6. Frontend Change Summary

| File | Change |
|---|---|
| `frontend/src/types/athena.ts` | Add 4 interfaces + 1 type alias for manifest models |
| `frontend/src/components/PresetDataCard.tsx` | Remove inline `AthenaSource`/`AthenaEntry`; import from `athena.ts` |
| `frontend/src/components/AthenaPresetPanel.tsx` | Remove inline `AthenaSource`/`AthenaEntry`; import from `athena.ts` |

No new components. No routing changes. No state management changes.

---

## 7. Testing

New test file: `backend/tests/models/test_athena_manifest.py`

### test_encounters_manifest_parses

Load `backend/data/athena-encounters-manifest.json` from disk. Pass its contents to `AthenaEncounterManifest.model_validate()`. Assert no `ValidationError` is raised. Assert `manifest.source_kind == "athena_encounter"`. Assert `len(manifest.entries) >= 1`. Assert the first entry has non-empty `encounter_id` and `practice_id`.

### test_clinical_docs_manifest_parses

Load `backend/data/athena-clinicaldocs-manifest.json` from disk. Pass its contents to `AthenaClinicalDocManifest.model_validate()`. Assert no `ValidationError` is raised. Assert `manifest.source_kind == "athena_clinical_doc"`. Assert `len(manifest.entries) >= 1`. Assert the first entry has non-empty `document_id` and `patient_id`.

### test_invalid_source_kind_raises

Construct a minimal dict with `source_kind: "athena_unknown"` and an empty `entries` list. Attempt `AthenaEncounterManifest.model_validate(data)`. Assert `pydantic.ValidationError` is raised.

### test_encounter_entry_missing_encounter_id_raises

Construct a dict for `AthenaEncounterManifestEntry` omitting the `encounter_id` field. Assert `pydantic.ValidationError` is raised.

### test_extra_fields_are_ignored

Construct a valid encounter manifest dict with an extra key `"metadata": {"version": 1}` at the top level. Assert `AthenaEncounterManifest.model_validate(data)` succeeds (no error) and that `"metadata"` is absent from `manifest.model_dump()`.

### test_load_athena_sources_skips_invalid_manifest (integration)

Monkeypatch `_ATHENA_MANIFEST_NAMES` in `backend/routes/datasets.py` to point to a temporary file containing JSON with `source_kind: "bad_kind"`. Assert `_load_athena_sources()` returns an empty list (the invalid file is skipped). Assert that a `logger.warning` call was made (use `caplog` or mock).

---

## 8. Manual Intervention Required

None. All changes are confined to Python model definitions, a route function update, TypeScript type additions, and frontend import refactors. No database migrations, no environment variable changes, no infrastructure changes.

---

## 9. Open Questions & Decisions

**Q1: Where should the manifest models live?**

RESOLVED: `backend/models/athena_manifest.py` — a new file separate from `backend/models/athena.py`. Rationale: `athena.py` models live API responses from the Athena Health OAuth + REST APIs (token exchange, encounter summaries, clinical document metadata). Manifest models describe static local config files that ship with the codebase. They have different lifecycles, different validation concerns, and different consumers. Keeping them in separate files prevents the growing `athena.py` from becoming a grab-bag and makes the distinction between "live API contract" and "local config schema" immediately obvious to future maintainers.

**Q2: Should `_load_athena_sources()` raise on invalid manifest or silently skip?**

RESOLVED: Log a warning and skip the invalid file. Raising would crash `GET /care_plan/datasets` for all users any time a single manifest file has a schema problem — a disproportionate failure mode for what is effectively a developer-facing data file. The current code already silently skips missing files (`if path.is_file()`). Extending that pattern to invalid files is consistent and keeps the endpoint resilient. The warning log provides observability without crashing the request.

**Q3: Should `PresetDataCard.tsx` and `AthenaPresetPanel.tsx` inline interfaces be replaced by imports from `athena.ts`?**

RESOLVED: Yes. The inline `AthenaSource` and `AthenaEntry` interfaces in those components are duplicates of what the Pydantic models define. Deduplication is mandatory — a single source of truth for the manifest shape must exist. The mapping is:
- `AthenaSource` (inline) → `AthenaManifest` (from `athena.ts`)
- `AthenaEntry` (inline) → `AthenaEncounterManifestEntry | AthenaClinicalDocManifestEntry` (from `athena.ts`)

Both components update their import statements; no runtime behaviour changes. TypeScript will catch any field name mismatches at compile time after the refactor.
