# PRD: Output History Regrouping

Sub-project 5 of 5. **Depends on Sub-project 4** (the `batch_group_id` concept must exist to have
anything to group by) and **Sub-project 1** (envelope shape).

## 1. Problem

The Sidebar today (`Sidebar.tsx`) shows every saved output as one flat, newest-first list — name and
date, no grouping. Once batch runs (Sub-project 4) exist, N outputs from one batch submission would
just appear as N indistinguishable rows, with no way to tell they came from the same batch or browse
them together.

You want: group by calendar date first, then — within a date — cluster outputs that share a batch
run under a sub-heading named after that batch (e.g. `DocConv-20260616153012`), while individual
(non-batch) runs stay as plain rows directly under the date, no extra nesting.

## 2. Goals

- `batch_group_id` (already produced per-output by Sub-project 4) becomes queryable/listable at the
  top level of each saved-output's metadata, not buried inside `output_data`.
- The existing `/simplify/saved` list endpoint returns it.
- The Sidebar groups the existing flat list **client-side** — date headers, then batch sub-headings
  for outputs that share a `batch_group_id`, then plain rows for everything else.

## 3. Non-Goals

- Not changing how outputs are stored beyond adding one field — no new collection, no new index
  required (the existing `(uid, created_at)` composite index already supports the query; grouping
  happens after the data is fetched, not via a new Firestore query shape).
- Not adding pagination (out of scope; the existing list endpoint has none today, and grouping doesn't
  require it — flagged only if the list ever grows large enough to matter, which isn't a problem this
  PRD needs to solve).
- Not adding a "view all members of this batch" detail endpoint — the flat list already contains every
  member, so the client-side grouping has everything it needs without a new API.

## 4. Architecture Decisions

**Storage:** `save_simplify_output(...)` (`backend/utils/save_output.py` per the original Explore
findings) gains one new optional parameter, `batch_group_id: str | None`, stored as a top-level field
on the Firestore document (sibling to `uid`, `name`, `created_at` — not nested inside `output_data`,
even though it's *also* present inside `output_data.input.batch_group_id` per Sub-project 4's `Input`
model). Top-level storage exists purely so the list endpoint can return it without parsing the
(potentially large) nested `output_data` blob for every row — this is a small, deliberate duplication
for query efficiency, not a new source of truth (the value always originates from the same place:
the batch route's computed `batch_group_id`).

**List endpoint:** `GET /simplify/saved` (`backend/routes/saved_outputs.py`, `list_saved`) adds
`batch_group_id` to each item in its response:
```json
{ "outputs": [
  { "id": "...", "name": "...", "source_filename": "...", "created_at": "...", "updated_at": "...", "batch_group_id": "DocConv-20260616153012" },
  { "id": "...", "...": "...", "batch_group_id": null }
]}
```

**Client-side grouping (no new backend work beyond the field above).** The Sidebar already fetches the
full, newest-first list. A new pure function, `groupSavedOutputs(outputs)`, transforms it into:
```ts
type DateGroup = { date: string; batches: BatchGroup[]; standalone: SavedOutputMeta[] };
type BatchGroup = { batch_group_id: string; items: SavedOutputMeta[] };
```
Algorithm: bucket by the calendar-date portion of `created_at` (preserving overall newest-first
order, so date buckets come out newest-first too); within each date bucket, further bucket items by
`batch_group_id` — items with a non-null id become a `BatchGroup` (one per distinct id, so two
batches from the same dataset on the same day naturally produce two separate
`DocConv-<timestamp1>` / `DocConv-<timestamp2>` sub-headings, per your example); items with a null id
go into that date's `standalone` list, rendered as plain rows with no extra nesting, exactly as today.

**Date header formatting.** Plain calendar dates (e.g. "June 16, 2026"), not relative labels like
"Today"/"Yesterday" — simpler, unambiguous, and naturally satisfies "by default grouped by today's
date" since today's date is just the first/topmost bucket in a newest-first list. Relative labels are
a cosmetic nice-to-have you can request separately later; not building them now keeps this scoped.

**Rendering.** `Sidebar.tsx` renders: date header → for each `BatchGroup`, a collapsible sub-heading
(batch id as the label, collapsed or expanded by default is a small UX call — default **expanded**
seems right since batch outputs are usually what someone just ran and wants to see) listing its
`items`; then the date's `standalone` items as plain rows, same as the component's current row
rendering (no change to the individual row component itself, only to what wraps it).

## 5. API Change Summary

```
GET /simplify/saved
  response items add: "batch_group_id": string | null
```

## 6. Frontend Change Summary

- `groupSavedOutputs()` pure function (new, easily unit-testable without any component rendering).
- `Sidebar.tsx` restructured to render the grouped shape: date headers, batch sub-headings
  (collapsible), standalone rows — reusing the existing single-row rendering/rename/delete menu
  unchanged for every leaf item regardless of which grouping level it's under.

## 7. Testing

- Unit test `groupSavedOutputs()` with a fixture list spanning two dates, two distinct batches on one
  of those dates, and a few standalone items — assert the exact nested shape.
- Backend test: `save_simplify_output(..., batch_group_id="DocConv-x")` then `GET /simplify/saved`
  returns that id on the right item; an output saved without a `batch_group_id` returns `null`.
- Manual run: with at least one batch run (from Sub-project 4's manual verification) and at least one
  regular single upload both present, confirm the Sidebar shows them grouped correctly.

## 8. Manual Intervention Required From You

- **Default expand/collapse state for batch sub-headings** — this PRD defaults to expanded; say so if
  you'd rather they start collapsed. Cosmetic, not blocking.
- None of this sub-project's other decisions need your sign-off before implementation — it's a small,
  low-risk addition once Sub-project 4 exists.
