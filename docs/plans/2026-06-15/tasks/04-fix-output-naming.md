# Task 04: Fix Output Naming — Use Appointment Content Instead of Generic Labels

**Status:** Ready for implementation  
**Affects:** `simplify_v1_2.py` only (v1.1 does not save outputs — see Note on v1.1 below)

---

## 1. Goal

When a user's appointment note is saved, it should receive a human-readable name that reflects what the appointment was actually about — not a machine-internal label like `text_input` or a raw filename like `note.pdf`.

**What a good name looks like:**

| Input | Bad (current) | Good (target) |
|---|---|---|
| Pasted text | `text_input` | `Knee Pain & Physical Therapy` |
| Uploaded file | `discharge_summary.pdf` | `High Blood Pressure Follow-Up` |
| Stored doc | `doc:abc123` | `Diabetes Management Check` |

The name is displayed directly in the sidebar (via `output.name` in `Sidebar.tsx` line 113). It is the primary label the user sees when returning to a saved result. A generic name forces users to click in to find out what the result is — defeating the purpose of the history sidebar.

---

## 2. Current State — Exactly Where the Name Is Set

### In `simplify_v1_2.py`

The `name` field passed to `save_simplify_output()` is always `resolved.source_description`, which is set in `_resolve_input()` (lines 182–229) and `_resolve_uploaded_files()` (lines 108–158).

**Text input path** (`_resolve_input()`, line 192–196):
```python
return ResolvedInput(
    text=text_input,
    source_description="text_input",   # <-- hardcoded string
    source_filename="text_input",
    source_kind="text",
)
```

**File upload path** (`_resolve_uploaded_files()`, lines 152–158):
```python
source_filename = ", ".join(filenames)
return ResolvedInput(
    text="\n".join(text_parts).strip(),
    source_description=source_filename,  # <-- e.g. "note.pdf" or "a.pdf, b.pdf"
    source_filename=source_filename,
    combined_pdf_bytes=combined_pdf_bytes,
)
```

**Stored doc (doc_id) path** (`_resolve_input()`, lines 221–227):
```python
return ResolvedInput(
    text=_extract_text_from_bytes(file_bytes, filename),
    source_description=f"doc:{doc_id}",  # <-- e.g. "doc:abc123"
    source_filename=filename,
    ...
)
```

**Where name is consumed** (`_generate_stream()`, lines 341–347):
```python
saved_id = save_simplify_output(
    user_id=user_id,
    name=resolved.source_description,   # <-- this becomes the Firestore `name` field
    source_filename=resolved.source_filename,
    input_pdf_gcs=input_pdf_gcs,
    output_data=result,
)
```

Note: the `doc_id` path returns early at line 333–334 before reaching `save_simplify_output()`, so `doc_id` results are never saved and this bug does not affect them.

### In `save_output.py`

`save_simplify_output()` (lines 37–62) stores `name` verbatim into Firestore:
```python
db.collection("simplify_outputs").document(output_id).set({
    "uid": user_id,
    "name": name,   # <-- stored exactly as passed in
    ...
})
```

No transformation happens here. The fix must happen in `simplify_v1_2.py` before calling `save_simplify_output()`.

### In `Sidebar.tsx`

Line 113 renders the name directly:
```tsx
<div className="sidebar-item-name">{output.name}</div>
```

No frontend changes are needed.

### Note on v1.1

`simplify_v1_1.py` does **not** call `save_simplify_output()` at all — it only yields the result via SSE and never persists anything. The naming bug does not exist in v1.1, and no changes are needed there.

---

## 3. What's Available in the Output

After the pipeline completes, the `result` dict is built at lines 318–330 of `simplify_v1_2.py`. It contains the full structured appointment schema (from `backend/simplify/v1_2/appointment.schema.json`). The fields most useful for generating a name are:

### `reason_for_visit` (array of objects)
Each object has:
- `reason` — plain-language reason for the visit (e.g. `"knee pain"`, `"follow-up for high blood pressure"`)
- `description` — additional patient-facing details

The first `reason_for_visit[0].reason` is the most direct, patient-friendly summary of what the visit was for. This is the best candidate for the name.

### `diagnosis.main_conclusion` (string)
One plain-language sentence of the doctor's overall clinical judgment (e.g. `"Your blood pressure is improving but still elevated"`). This is a fallback if `reason_for_visit` is absent.

### `summary` (string)
A 3-sentence summary: sentence 1 is why the patient came in, sentence 2 is the main clinical finding, sentence 3 is the next step. This is verbose for a name but sentence 1 could be extracted as a last resort.

### `diagnosis.details[0].plain_name` (string)
The plain-language name of the primary diagnosis (e.g. `"high blood pressure"`). Useful fallback if `reason_for_visit` is empty.

**Priority ranking for name extraction from output data:**

1. `result["reason_for_visit"][0]["reason"]` — most specific, patient-facing, usually 2–6 words
2. `result["diagnosis"]["main_conclusion"]` — sentence-length, truncate to ~60 chars
3. `result["diagnosis"]["details"][0]["plain_name"]` — single-condition fallback

---

## 4. Proposed Naming Logic

Add a helper function `_derive_output_name()` in `simplify_v1_2.py` that takes the structured `result` dict and the `resolved` input, and returns the best available name.

**Priority order:**

1. **From AI output data — `reason_for_visit[0].reason`**  
   If `result.get("reason_for_visit")` is a non-empty list and `result["reason_for_visit"][0].get("reason")` is a non-empty string, use it. Title-case it and truncate to 60 characters.

2. **From AI output data — `diagnosis.main_conclusion`**  
   If `result.get("diagnosis", {}).get("main_conclusion")` is a non-empty string, use the first sentence (split on `.`) truncated to 60 characters.

3. **From AI output data — `diagnosis.details[0].plain_name`**  
   If `result.get("diagnosis", {}).get("details")` is a non-empty list with a `plain_name`, use it. Title-case, truncate to 60 characters.

4. **From source filename (file uploads only)**  
   If `resolved.source_kind == "upload"` and `resolved.source_filename` is not `"text_input"`, use the filename stem (strip extension, replace underscores/hyphens with spaces, title-case). E.g. `discharge_summary.pdf` → `Discharge Summary`.

5. **Final fallback**  
   `"Appointment"` — a neutral, always-safe name.

Do **not** include the date in the auto-generated name. The date is already displayed separately in the sidebar via `output.created_at` (Sidebar.tsx line 115), so including it in the name would be redundant.

---

## 5. Exact Changes Required

### File: `/root/projects/juno/backend/routes/simplify_v1_2.py`

**Change 1: Add the `_derive_output_name()` helper.**

Insert this function after the `_score_or_none()` function (after line 237, before `_generate_stream()`):

```python
def _derive_output_name(result: dict, resolved: "ResolvedInput") -> str:
    """
    Derive a human-readable name for a saved output.

    Priority:
      1. reason_for_visit[0].reason  (from AI output)
      2. diagnosis.main_conclusion   (first sentence, from AI output)
      3. diagnosis.details[0].plain_name  (from AI output)
      4. source filename stem        (for file uploads)
      5. "Appointment"               (final fallback)
    """
    try:
        rfv = result.get("reason_for_visit")
        if rfv and isinstance(rfv, list):
            reason = (rfv[0].get("reason") or "").strip()
            if reason:
                return reason.title()[:60]

        diagnosis = result.get("diagnosis") or {}
        main = (diagnosis.get("main_conclusion") or "").strip()
        if main:
            first_sentence = main.split(".")[0].strip()
            if first_sentence:
                return first_sentence[:60]

        details = diagnosis.get("details")
        if details and isinstance(details, list):
            plain = (details[0].get("plain_name") or "").strip()
            if plain:
                return plain.title()[:60]
    except Exception:
        logger.exception("simplify_v1_2: failed to derive name from output - using fallback")

    # Fallback: use filename stem if it's a real filename, not "text_input"
    filename = resolved.source_filename or ""
    if filename and filename != "text_input":
        stem = filename.split(",")[0].strip()   # first file if multiple
        if "." in stem:
            stem = stem.rsplit(".", 1)[0]
        stem = stem.replace("_", " ").replace("-", " ").strip()
        if stem:
            return stem.title()[:60]

    return "Appointment"
```

**Change 2: Replace `name=resolved.source_description` with the derived name.**

In `_generate_stream()`, at lines 341–347, change:

```python
# BEFORE
saved_id = save_simplify_output(
    user_id=user_id,
    name=resolved.source_description,
    source_filename=resolved.source_filename,
    input_pdf_gcs=input_pdf_gcs,
    output_data=result,
)
```

to:

```python
# AFTER
saved_id = save_simplify_output(
    user_id=user_id,
    name=_derive_output_name(result, resolved),
    source_filename=resolved.source_filename,
    input_pdf_gcs=input_pdf_gcs,
    output_data=result,
)
```

### File: `/root/projects/juno/backend/utils/save_output.py`

No changes needed. `save_simplify_output()` stores `name` verbatim and that is correct.

### Frontend

No changes needed. `Sidebar.tsx` renders `output.name` directly at line 113, which is already correct behavior.

---

## 6. Edge Cases

**What if `reason_for_visit` is present but empty list?**  
The check `if rfv and isinstance(rfv, list)` handles this. Falls through to the next priority.

**What if `reason_for_visit[0]` exists but `reason` is an empty string?**  
The `.strip()` + truthiness check handles this. Falls through.

**What if the AI returns `reason_for_visit` as `null` instead of `[]`?**  
`result.get("reason_for_visit")` returns `None`, which is falsy. Falls through.

**What if `diagnosis` key is missing entirely?**  
`result.get("diagnosis") or {}` returns an empty dict safely. Falls through to the filename fallback.

**What if multiple files were uploaded?**  
`resolved.source_filename` will be a comma-separated string like `"a.pdf, b.pdf"`. The fallback logic takes only `stem.split(",")[0].strip()` — i.e. the first filename — and uses its stem. This is acceptable. The AI output name (priority 1–3) will typically be used instead.

**What if the extracted name is very long (e.g. `main_conclusion` is a long sentence)?**  
All candidates are truncated to 60 characters. The sidebar has CSS overflow handling, but 60 chars is a safe display length.

**What if the entire `try` block in `_derive_output_name()` raises an unexpected exception?**  
The `except Exception` clause logs it and falls through to the filename/fallback logic below the `try` block.

**What if the pipeline itself failed structuring and `result` is partially empty?**  
The pipeline returns early with an SSE error step if `structure_appointment_note()` fails (line 307–308), so `save_simplify_output()` is never reached in that case. This edge case does not apply.

**What if the user manually renames the output after saving?**  
Renaming is handled separately via `renameSavedOutput` (Sidebar.tsx line 53). The auto-generated name is only set at save time. Renames overwrite it in Firestore and this task does not affect that flow.

---

## 7. Acceptance Criteria

After the fix, saved outputs must have names matching the following for each input type:

| Scenario | Expected `name` in Firestore |
|---|---|
| Text input, output has `reason_for_visit[0].reason = "knee pain and stiffness"` | `"Knee Pain And Stiffness"` |
| Text input, output has no `reason_for_visit`, `diagnosis.main_conclusion = "Your blood sugar is well-controlled."` | `"Your blood sugar is well-controlled"` |
| Text input, output has no `reason_for_visit` or `main_conclusion`, `diagnosis.details[0].plain_name = "type 2 diabetes"` | `"Type 2 Diabetes"` |
| Text input, output has none of the above (empty structured result) | `"Appointment"` |
| File upload `discharge_summary.pdf`, output has `reason_for_visit[0].reason = "hospital follow-up"` | `"Hospital Follow-Up"` |
| File upload `discharge_summary.pdf`, AI output empty/missing all name fields | `"Discharge Summary"` |
| File upload `my-appointment-note.docx`, AI output empty | `"My Appointment Note"` |
| Multiple file upload `a.pdf, b.pdf`, AI output empty | `"A"` (stem of first file — acceptable edge case) |
| `doc_id` input (any) | Not saved — acceptance criteria N/A |

**Manual verification steps:**
1. Open the app, paste appointment text, submit. Check the sidebar — the new result should have a content-derived name, not `text_input`.
2. Upload a PDF with a real appointment note. Check the sidebar — name should reflect the appointment content, not the filename.
3. Upload a PDF whose content the AI can't parse cleanly. Name should fall back to the filename stem (title-cased), not `text_input` or `Appointment`.
4. Open Firestore console and confirm the `name` field on the saved document matches what's shown in the sidebar.
