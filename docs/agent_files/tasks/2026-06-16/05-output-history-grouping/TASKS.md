# Tasks: Output History Regrouping

Read `PRD.md` in this folder first.

---

### Task 1 — Persist `batch_group_id` on save

**File:** `backend/utils/save_output.py` (the `save_simplify_output` function)

Add an optional parameter `batch_group_id: str | None = None`, stored as a top-level field on the
Firestore document alongside `uid`, `name`, `created_at`, etc. (sibling field, per PRD.md §4 — not
nested inside `output_data`).

Update the one call site this matters for: Sub-project 4 Task 6's batch route, which should now pass
`batch_group_id=batch_group_id` on every per-input save. Regular single-run saves (Sub-projects 1–3)
simply don't pass it, defaulting to `None`.

**Acceptance criteria:** A document saved via the batch route has a top-level `batch_group_id` field
matching the batch's id; a document saved via a regular single run has `batch_group_id: None`.

**Depends on:** Sub-project 4 Task 6 (needs `batch_group_id` to exist as a concept before this is
useful — can be implemented in either order, but won't be exercised until that lands).

---

### Task 2 — Return `batch_group_id` from the list endpoint

**File:** `backend/routes/saved_outputs.py` (`list_saved`)

Add `'batch_group_id': data.get('batch_group_id')` to the dict built for each item in the response
loop (currently builds `id`/`name`/`source_filename`/`created_at`/`updated_at`).

**Acceptance criteria:** `GET /simplify/saved` response items include `batch_group_id` (string or
`null`) for every item, matching what was stored in Task 1.

**Depends on:** Task 1.

---

### Task 3 — `groupSavedOutputs()` frontend util

**File (new):** `frontend/src/utils/groupSavedOutputs.ts`

```ts
export interface SavedOutputMeta {
  id: string; name: string; source_filename: string;
  created_at: string; updated_at: string; batch_group_id: string | null;
}
export interface BatchGroup { batch_group_id: string; items: SavedOutputMeta[] }
export interface DateGroup { date: string; batches: BatchGroup[]; standalone: SavedOutputMeta[] }

export function groupSavedOutputs(outputs: SavedOutputMeta[]): DateGroup[] {
  const dateOrder: string[] = [];
  const byDate = new Map<string, SavedOutputMeta[]>();
  for (const o of outputs) {
    const date = o.created_at.slice(0, 10); // YYYY-MM-DD; format for display separately
    if (!byDate.has(date)) { byDate.set(date, []); dateOrder.push(date); }
    byDate.get(date)!.push(o);
  }
  return dateOrder.map(date => {
    const items = byDate.get(date)!;
    const batchOrder: string[] = [];
    const byBatch = new Map<string, SavedOutputMeta[]>();
    const standalone: SavedOutputMeta[] = [];
    for (const o of items) {
      if (!o.batch_group_id) { standalone.push(o); continue; }
      if (!byBatch.has(o.batch_group_id)) { byBatch.set(o.batch_group_id, []); batchOrder.push(o.batch_group_id); }
      byBatch.get(o.batch_group_id)!.push(o);
    }
    return {
      date,
      batches: batchOrder.map(id => ({ batch_group_id: id, items: byBatch.get(id)! })),
      standalone,
    };
  });
}
```
(Note: relies on the input list already being newest-first, per the existing `list_saved` query order
— don't re-sort inside this function, just bucket in encounter order, preserving that ordering.)

**Acceptance criteria:** Unit test per PRD.md §7 — fixture with two dates, two batches on one date,
several standalone items, asserting the exact nested output shape.

**Depends on:** Task 2 (needs the field in the API response to be meaningful, though the function
itself can be written/tested against a hand-built fixture independently).

---

### Task 4 — `Sidebar.tsx` rendering

**File:** `frontend/src/components/Sidebar.tsx`

Replace the current flat `.map()` over outputs with: call `groupSavedOutputs(outputs)`, then render
per `DateGroup`:
- A date header (format `date` — a `YYYY-MM-DD` string — into a readable form, e.g.
  `new Date(date).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })`).
- For each `BatchGroup`: a collapsible sub-heading labeled `batch_group_id`, default expanded (per
  PRD.md §8's default), containing its `items` rendered with the **existing, unchanged** row
  component/markup used today for each output (same rename/delete menu, same click-to-load
  behavior).
- Then `standalone` items, rendered as plain rows exactly as all items are today (no wrapper).

**Acceptance criteria:** Manual run — confirm grouping renders correctly with a mix of batch and
standalone outputs (use Sub-project 4's manually-created test data). Rename/delete/click-to-load still
work identically on every item regardless of nesting level (these operations don't care about
grouping, only about the row component, which is unchanged).

**Depends on:** Task 3.

---

### Task 5 — Tests

Cover PRD.md §7's backend test (`batch_group_id` round-trips through save → list) and confirm the
Task 3 unit test and Task 4 manual check are both done.

**Depends on:** Tasks 1–4.

---

## Summary of what requires you (not a dev agent)

1. **Default expand/collapse state for batch sub-headings** — defaulted to expanded in this plan;
   say so before/during Task 4 if you'd prefer collapsed.

Nothing else in this sub-project is blocked on you.
