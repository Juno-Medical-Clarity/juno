# Task 05: Move Download Buttons Off Sticky Bar

## Goal

The "Download JSON" and "Download Report/PDF" buttons currently float in a fixed bar pinned to the bottom of the viewport at all times while the user is viewing a simplified note. The desired behavior is: these buttons should live at the **end of the report content**, in normal document flow. The user must scroll to the bottom of the report to see and click them. They should not be visible until the user has scrolled past all the note content.

---

## Current State

### Why they are sticky

**`/root/projects/juno/frontend/src/App.css` (lines 658-671)**

```css
/* Lines 658–671 */
.download-bar {
  position: fixed;      /* <-- pins to viewport */
  bottom: 0;            /* <-- stuck to bottom of screen */
  left: 0;
  right: 0;
  z-index: 50;          /* <-- floats above all content */
  padding: 16px 24px;
  background: rgba(244, 242, 255, 0.92);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-top: 1px solid rgba(124, 58, 237, 0.15);
  display: flex;
  justify-content: center;
}
```

The three properties `position: fixed`, `bottom: 0`, and `z-index: 50` together cause the bar to be removed from document flow and pinned to the bottom of the screen.

### Where the download bar is rendered in JSX

**`/root/projects/juno/frontend/src/pages/v1_2/V1_2Page.tsx` (lines 370-381)**

The download bar is rendered **outside and after** the result `<section>` block — it is a sibling of the main content container, not a child of the result section:

```tsx
{/* result-section closes here, line 366 */}
        </div>   {/* closes inner scroll container */}
      </div>     {/* closes outer layout wrapper */}

      {/* download-bar is a sibling rendered AFTER the main content wrapper */}
      {appState === 'result' && result && (
        <div className="download-bar">
          <div className="download-actions">
            <button className="download-btn-json" onClick={handleDownloadJson}>
              ↓ Download JSON
            </button>
            <button className="download-btn-pdf" onClick={handleDownloadPdf}>
              ↓ Download Report
            </button>
          </div>
        </div>
      )}
```

**`/root/projects/juno/frontend/src/pages/v1_1/V1_1Page.tsx` (lines 750-761)**

Identical pattern in V1_1 — rendered outside and after the result section, as a sibling of the layout root:

```tsx
      {appState === 'result' && result && (
        <div className="download-bar">
          <div className="download-actions">
            <button className="download-btn-json" onClick={handleDownloadJson}>
              ↓ Download JSON
            </button>
            <button className="download-btn-pdf" onClick={handleDownloadPdf}>
              ↓ Download PDF
            </button>
          </div>
        </div>
      )}
```

The `.download-bar` styles in `App.css` apply globally to both pages. V1_1 also has `.download-actions`, `.download-btn-json`, and `.download-btn-pdf` defined in `/root/projects/juno/frontend/src/pages/v1_1/V1_1Page.css` (lines 93-126) — those button styles must not change.

---

## Exact Changes Required

### Change 1: Update `.download-bar` CSS in `App.css`

**File:** `/root/projects/juno/frontend/src/App.css`

**Before (lines 655-671):**

```css
/* ============================================================
   Sticky Download Bar
   ============================================================ */
.download-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 50;
  padding: 16px 24px;
  background: rgba(244, 242, 255, 0.92);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-top: 1px solid rgba(124, 58, 237, 0.15);
  display: flex;
  justify-content: center;
}
```

**After:**

```css
/* ============================================================
   Download Bar (end of report content, normal flow)
   ============================================================ */
.download-bar {
  display: flex;
  justify-content: center;
  margin-top: 40px;
  margin-bottom: 48px;
  padding: 0 24px;
}
```

Remove `position: fixed`, `bottom: 0`, `left: 0`, `right: 0`, `z-index: 50`, `background`, `backdrop-filter`, `-webkit-backdrop-filter`, and `border-top`. Replace with a simple flex container with top/bottom margin so the buttons appear centered, below the note, with breathing room above and below.

---

### Change 2: Move the download bar JSX into the result section in `V1_2Page.tsx`

**File:** `/root/projects/juno/frontend/src/pages/v1_2/V1_2Page.tsx`

The download bar must move from its current position (outside/after the outer layout wrapper) to **inside the `result-section`**, placed after the "Simplify another note" button div and before `</section>`.

**Before — result section ends and download bar comes after (lines 326-381):**

```tsx
          {appState === 'result' && result && (
            <section className="result-section">
              <div className="result-header">
                {/* ... */}
              </div>

              <AppointmentNoteV12View result={result} />

              <div style={{ marginTop: '32px', textAlign: 'center' }}>
                <button onClick={handleReset} style={{ /* ... */ }}>
                  ← Simplify another note
                </button>
              </div>
            </section>
          )}
        </div>
      </div>

      {appState === 'result' && result && (
        <div className="download-bar">
          <div className="download-actions">
            <button className="download-btn-json" onClick={handleDownloadJson}>
              ↓ Download JSON
            </button>
            <button className="download-btn-pdf" onClick={handleDownloadPdf}>
              ↓ Download Report
            </button>
          </div>
        </div>
      )}
```

**After — download bar moves inside the result section, after the reset button div:**

```tsx
          {appState === 'result' && result && (
            <section className="result-section">
              <div className="result-header">
                {/* ... */}
              </div>

              <AppointmentNoteV12View result={result} />

              <div style={{ marginTop: '32px', textAlign: 'center' }}>
                <button onClick={handleReset} style={{ /* ... */ }}>
                  ← Simplify another note
                </button>
              </div>

              <div className="download-bar">
                <div className="download-actions">
                  <button className="download-btn-json" onClick={handleDownloadJson}>
                    ↓ Download JSON
                  </button>
                  <button className="download-btn-pdf" onClick={handleDownloadPdf}>
                    ↓ Download Report
                  </button>
                </div>
              </div>
            </section>
          )}
        </div>
      </div>

      {/* download-bar conditional block removed from here */}
```

The outer `{appState === 'result' && result && ( ... )}` conditional wrapping the download bar is no longer needed because the div is now inside the `result-section` block which already guards on that condition.

---

### Change 3: Move the download bar JSX into the result section in `V1_1Page.tsx`

**File:** `/root/projects/juno/frontend/src/pages/v1_1/V1_1Page.tsx`

Same pattern as V1_2. Move the download bar from outside the layout wrapper (lines 750-761) to inside the `result-section`, after the "Simplify another note" button div.

**Before (lines 719-761):**

```tsx
          {appState === 'result' && result && (
            <section className="result-section">
              <div className="result-header">
                {/* ... */}
              </div>

              <AppointmentNoteV11View result={result} />

              <div style={{ marginTop: '32px', textAlign: 'center' }}>
                <button onClick={handleReset} style={{ /* ... */ }}>
                  ← Simplify another note
                </button>
              </div>
            </section>
          )}
        </div>
      </div>

      {appState === 'result' && result && (
        <div className="download-bar">
          <div className="download-actions">
            <button className="download-btn-json" onClick={handleDownloadJson}>
              ↓ Download JSON
            </button>
            <button className="download-btn-pdf" onClick={handleDownloadPdf}>
              ↓ Download PDF
            </button>
          </div>
        </div>
      )}
```

**After:**

```tsx
          {appState === 'result' && result && (
            <section className="result-section">
              <div className="result-header">
                {/* ... */}
              </div>

              <AppointmentNoteV11View result={result} />

              <div style={{ marginTop: '32px', textAlign: 'center' }}>
                <button onClick={handleReset} style={{ /* ... */ }}>
                  ← Simplify another note
                </button>
              </div>

              <div className="download-bar">
                <div className="download-actions">
                  <button className="download-btn-json" onClick={handleDownloadJson}>
                    ↓ Download JSON
                  </button>
                  <button className="download-btn-pdf" onClick={handleDownloadPdf}>
                    ↓ Download PDF
                  </button>
                </div>
              </div>
            </section>
          )}
        </div>
      </div>

      {/* download-bar conditional block removed from here */}
```

---

## Proposed Final CSS for `.download-bar`

```css
/* ============================================================
   Download Bar (end of report content, normal flow)
   ============================================================ */
.download-bar {
  display: flex;
  justify-content: center;
  margin-top: 40px;
  margin-bottom: 48px;
  padding: 0 24px;
}
```

No `position`, no `bottom`, no `z-index`, no `background`, no `backdrop-filter`, no `border-top`. The bar sits in the normal document flow, centered, with 40px above it (separating it from the "Simplify another note" button) and 48px below it before the end of the page.

---

## Do NOT Change

- **Button styles** — `.download-btn-json` and `.download-btn-pdf` rules in `V1_1Page.css` (lines 100-126) and the `.download-btn` rule in `App.css` (lines 673-705) must remain exactly as-is. Colors, shapes, font, hover states, and shimmer animation are all preserved.
- **`onClick` handlers** — `handleDownloadJson` and `handleDownloadPdf` (and `handleDownloadPdf` for V1_1) must not be touched.
- **Download logic** — no changes to any download-related functions.
- **`.download-actions`** — the flex container inside `.download-bar` (gap, justify-content, flex-wrap) stays unchanged.
- **Button labels** — "↓ Download JSON", "↓ Download Report" (V1_2), "↓ Download PDF" (V1_1) are not changed.

---

## Acceptance Criteria

1. When a user views a simplified note on the V1_2 page, the download buttons are **not visible** at the bottom of the viewport on page load or shortly after the result appears.
2. When the user **scrolls to the bottom** of the simplified note content, the download buttons appear naturally in the page flow, below the "Simplify another note" button.
3. The download buttons do not overlap any content at any scroll position.
4. Clicking "↓ Download JSON" and "↓ Download Report" still trigger downloads correctly.
5. The same behavior holds on the V1_1 page: buttons are below the note content, visible only on scroll.
6. No visual change to the buttons themselves (colors, shape, hover, shimmer).
7. There is no longer a frosted-glass/blurred bar visible at the bottom of the viewport when viewing a result.
