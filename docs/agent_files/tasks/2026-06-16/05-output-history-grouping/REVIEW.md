# Code Review — 05-output-history-grouping

Branch: `feature/structured-output-grading-batch-input`
Reviewer: automated production-readiness review (review-only, no code modified)
Tests run: backend `test_saved_outputs_route.py` + `test_save_output.py` = 4 passed; frontend `vitest run` = 5 passed.

---

## Summary Verdict — Quality Score: 4 / 5

This is a small, well-scoped sub-project that does almost exactly what the PRD/TASKS describe, and it
does it cleanly. All five tasks are implemented: `batch_group_id` is persisted as a top-level Firestore
field (conditionally, only when non-null), the list endpoint returns it, the `groupSavedOutputs` pure
function matches the PRD's reference algorithm verbatim, and the Sidebar renders date headers with
collapsible batch groups reusing the existing row component. Tenant isolation in the list endpoint is
correct (server-side `where('uid','==',user_id)` filter), and React's JSX escaping neutralizes the
obvious XSS vector for the rendered `batch_group_id`. The grouping util is genuinely reusable and
well-tested for its happy paths.

It falls short of 5/5 for two reasons. First, there is a real **timezone consistency bug**: date
bucketing uses the UTC calendar date (`created_at.slice(0,10)`) while date headers and the default
"expand today's batches" logic mix UTC and what the user perceives as local time — outputs created
late evening local time land under tomorrow's UTC date header. Second, **test coverage has clear gaps**:
`groupSavedOutputs` has no test for items with the same `batch_group_id` split across two dates, for
falsy-but-present batch ids, or for input ordering assumptions; and there are **zero Sidebar component
tests** despite the component carrying all the non-trivial rendering/timezone/collapse logic. Neither
gap is a blocker, but both should be closed before this is considered hardened.

---

## Correctness vs PRD / TASKS

| Task | Status | Notes |
|------|--------|-------|
| 1 — Persist `batch_group_id` on save | Done | `save_output.py` adds the optional param, stored top-level via `if batch_group_id is not None`. Batch route (`batch.py:201-209`) passes it on every per-input save. Single runs omit it. Matches §4. |
| 2 — Return from list endpoint | Done | `saved_outputs.py:71` adds `'batch_group_id': data.get('batch_group_id')` — returns `None` for legacy/standalone docs. Exactly per TASKS. |
| 3 — `groupSavedOutputs()` util | Done | Implementation is character-for-character the PRD reference algorithm. Preserves encounter order (newest-first), buckets by date then by batch id, standalone for falsy ids. |
| 4 — Sidebar rendering | Done | Date header via `toLocaleDateString`, `<details>` collapsible per batch (`open` when date === today), standalone rows after. Reuses `renderRow` unchanged for rename/delete/click-to-load. |
| 5 — Tests | Partial | Backend round-trip test present and passing; `groupSavedOutputs` unit test present (5 cases); Task 4 "manual check" not evidenced and no automated Sidebar test. |

**Design deviations / observations (all benign):**
- `save_output.py` also added `dataset_group` (Sub-project 4 concern) in the same change — out of this
  sub-project's strict scope but consistent and harmless.
- The PRD says batch groups default **expanded**. The implementation only expands batches whose
  `dateGroup.date === today` (UTC); batches on *prior* dates render **collapsed**. This is a reasonable
  UX refinement (only expand the most recent day) but it is a deviation from the literal PRD §8
  default of "expanded" and should be confirmed as intentional.

---

## Bugs & Edge Cases

### HIGH

- **Timezone inconsistency in date bucketing vs. "today".**
  `groupSavedOutputs` buckets by `o.created_at.slice(0,10)` — the **UTC** calendar date. The Sidebar
  computes `today = new Date().toISOString().slice(0,10)` — also UTC — and uses it for the `open`
  default. The date *header* is rendered via `new Date(dateGroup.date + 'T12:00:00').toLocaleDateString(...)`
  which constructs a **local-time** Date from the UTC date string. Net effect for a user west of UTC:
  an output saved at, say, 20:00 local (= 02:00 next-day UTC) is bucketed under tomorrow's UTC date and
  labeled with tomorrow's date — i.e. it shows a future date and may not be grouped with other outputs
  the user made "the same evening." For a user east of UTC the symmetric early-morning case applies.
  Because both the spec and the reference algorithm explicitly chose UTC slicing, this may be accepted,
  but it is the single most likely user-visible defect and is untested. At minimum the choice should be
  documented; ideally bucket by local date to match the header and user expectation.

### MEDIUM

- **Same `batch_group_id` spanning a UTC midnight is silently split.** A batch that starts at 23:59
  UTC and finishes at 00:01 UTC produces two `BatchGroup`s with the *same* `batch_group_id` label under
  two different date headers. The UI would then show two identical-looking "DocConv-…" sub-headings on
  adjacent days. Unlikely but possible for long batch runs; not handled and not tested. (The batch route
  computes one timestamp per batch up front, so all members share an id, making this purely a
  date-boundary artifact.)

- **Collapse state is not persistent and resets on every refresh.** `<details open=...>` is controlled
  only by the initial `open` prop; there is no state persistence. Any `refreshTrigger` change re-renders
  and a user's manual expand/collapse of an older-date batch is lost when the list refetches (e.g. after
  a rename/delete elsewhere). Minor UX, but worth noting since the PRD calls out collapse as a UX point.

### LOW

- **Falsy-but-meaningful batch ids.** `groupSavedOutputs` treats any falsy `batch_group_id`
  (`null`, `undefined`, **and empty string `''`**) as standalone via `if (!o.batch_group_id)`. If a
  batch id were ever the empty string it would be miscategorized. Currently batch ids are always
  `f"{group}-{timestamp}"` (non-empty), so this is theoretical, but the `''` case is untested.

- **Date header reparsing relies on a hardcoded `T12:00:00` hack** to dodge the previous-day rollback
  that `new Date('YYYY-MM-DD')` (parsed as UTC midnight) would cause in negative-offset timezones. It
  works for all real offsets (±14h from noon), but it is an implicit, comment-free trick that a future
  editor could easily break.

- **Performance: grouping is O(n) and fine**, but the whole list is fetched unpaginated (PRD explicitly
  defers pagination). For a user with thousands of saved outputs, the full stream + client grouping +
  N `<details>`/row DOM nodes will degrade. Acceptable per Non-Goals, flagged for future scale.

- **Empty / loading states correct.** Empty input → `[]` (tested); `loading` gates grouping; empty
  list shows "No saved outputs yet." No crash paths found.

---

## Test Coverage Gaps

**`groupSavedOutputs.test.ts` (currently 5 tests) — missing cases:**
1. Same `batch_group_id` appearing under two different dates → asserts it produces two separate
   `BatchGroup`s (documents the midnight-split behavior).
2. Empty-string `batch_group_id` (`''`) → currently treated as standalone; lock the behavior in.
3. `undefined` batch_group_id (legacy field truly absent in JSON) vs explicit `null` → both → standalone.
4. Interleaved input ordering within a date (batch item, standalone, then another item of the same
   batch) → assert batch ordering follows first-encounter and standalone preserves order. The current
   fixture is already pre-sorted, so the "preserve encounter order, don't re-sort" contract is not
   actually exercised against an adversarial order.
5. Two batches plus standalone where standalone appears *before* a batch in encounter order → confirms
   standalone list and batch list are independent.

**Sidebar component tests (currently ZERO) — should exist:**
6. Renders a date header per `DateGroup` with the correct localized label.
7. Renders a `<details>` per batch with the `batch_group_id` as summary text, and standalone rows
   outside any `<details>`.
8. Today's batches render `open`; a prior-date batch renders collapsed (locks the PRD-deviation choice).
9. Rename/delete/click-to-load fire correctly on a row nested inside a batch group (the core "operations
   don't care about nesting" acceptance criterion from Task 4 is entirely unverified).
10. `batch_group_id` containing HTML/`<script>` is rendered as inert text (XSS regression guard).
11. Empty list → "No saved outputs yet."; loading → "Loading...".

**Backend:**
- `test_saved_outputs_route.py` covers the round-trip (present id + absent id → null). Good. Missing:
  a test asserting `list_saved` only returns the *authenticated* user's docs (the `where uid==` filter
  is the security boundary and is currently unasserted at the route level — see Security).
- `test_save_output.py` covers that `batch_group_id`/`dataset_group` are stored when passed, and that
  they are omitted when not passed is implicitly covered by the older test. Adequate.

---

## Security

- **Tenant isolation — OK.** `list_saved` filters server-side with
  `.where('uid', '==', user_id)` where `user_id` comes from the `@verify_firebase_token` decorator, not
  from client input. `batch_group_id` cannot leak across users because the query never returns another
  user's documents. The single-doc endpoints additionally re-check ownership via `_get_doc_or_403`.
  **Recommend adding an explicit route-level test** asserting that documents belonging to another uid are
  never returned, to prevent regression of this filter.
- **Auth enforced** on every endpoint (`@verify_firebase_token`). Good.
- **XSS — OK by default.** `batch_group_id` and `name` are rendered as JSX text children
  (`{batch.batch_group_id}`, `{output.name}`), which React auto-escapes. No `dangerouslySetInnerHTML`
  on this path. Since `batch_group_id` is server-generated (`f"{group}-{timestamp}"`) it is also not
  attacker-controlled today; the risk would only arise if a future change made it user-supplied, hence
  the suggested regression test (#10 above).
- **PII in logs — none added.** The list endpoint logs nothing (see below); no document names, uids, or
  batch ids are logged in this sub-project's changes. Good.
- **Note:** `batch_group_id` is stored top-level *and* inside `output_data.input.batch_group_id` — a
  deliberate, documented duplication (PRD §4). Since the top-level field is the only one returned by the
  list endpoint and both originate from the same computed value, there's no divergence risk in practice,
  but it is a second source that could drift if either write path changes independently.

## Logging & Metrics

- The list endpoint (`list_saved`) emits **no log lines and no metrics** at all — not even a debug-level
  "listed N outputs for user". This is consistent with the rest of the file (none of the CRUD endpoints
  log success paths; only the delete/signed-url failure paths use `logger.exception`). Per the review
  brief this is "minimal here," and that's accurate. Gap, not a defect:
  - No structured logging via `juno_logger`; the file uses the stdlib `logging` module directly, not the
    project's `JunoLogger`/`juno_metrics` helpers referenced in `backend/utils/LOGGING.md`. If the team
    wants consistent observability, a single info log + a counter metric on `list_saved` (count returned,
    latency) would align it with the logging standard. Not required by this PRD.
- No new metrics were warranted by the grouping feature itself (pure client-side transform).

## Extensibility

- **`groupSavedOutputs` is clean and reusable.** Pure, typed, no I/O, no React dependency, O(n). Easy to
  unit test (and is). The exported `DateGroup`/`BatchGroup`/`SavedOutputMeta` types are shared sensibly.
  Could be generalized (e.g. parameterize the date-key extractor and the group-key extractor) if other
  list groupings emerge, but YAGNI here.
- **Sidebar complexity is moderate and acceptable.** `renderRow` is a closure inside the component
  rather than an extracted memoized component — fine at this size, but as the row gains behavior (it
  already holds rename input + dropdown menu state) extracting a `SidebarRow` component would improve
  testability and reduce re-render scope. The menu's `menuRef`/outside-click logic is shared across all
  rows via a single ref, which works because only one menu is open at a time.
- **Code smells (minor):**
  - The `T12:00:00` date-parse trick is undocumented (see LOW bug).
  - `today` is recomputed on every render rather than memoized — negligible.
  - Inline styles on the rename `<input>` (lines 91–96) duplicate what could be a CSS class; cosmetic.

---

## Must-fix before production

1. **Decide and document the timezone behavior** (HIGH). Either bucket by local date to match the header
   and user expectation, or explicitly document that grouping is UTC-based and accept the late-evening
   "tomorrow" labeling. Add a test pinning whichever is chosen.
2. **Add a route-level tenant-isolation test** for `list_saved` (another user's docs are never returned).
   The security boundary is currently correct but unguarded by tests.
3. **Add Sidebar component tests** covering: rename/delete/click-to-load on a batch-nested row (Task 4's
   core acceptance criterion, currently unverified), date-header rendering, today-open vs prior-collapsed,
   and an XSS-inert `batch_group_id` regression guard.
4. **Add `groupSavedOutputs` tests** for the same-id-across-two-dates split, empty-string id, and an
   adversarially-unsorted input (to actually exercise the "preserve encounter order" contract).
5. **Confirm the expand default deviation** (only today's batches expand, not all) is intended vs. the
   PRD's literal "default expanded."

### Nice-to-have (non-blocking)
- Persist user expand/collapse state across refreshes.
- Add minimal info log + counter on `list_saved` to align with `LOGGING.md`.
- Extract `SidebarRow` into its own component and replace the `T12:00:00` parse hack with an explicit
  local-date formatter.
