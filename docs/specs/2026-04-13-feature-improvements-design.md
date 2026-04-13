# Feature Improvements — Design Spec

**Goal:** Add 8 new features to ChatGPT Tag Highlighter across 3 batches.

## Background

The extension currently highlights sidebar conversations by tag prefix, hides tagged items, prunes turns, and shows an overlay banner. These improvements add quality-of-life features to the options page, visual polish, and new runtime capabilities.

## Batch 1: Options Page Improvements

### F1: Import/Export Settings

Two buttons on the options page header: **Export** and **Import**.

- **Export:** Copies the full `tagHighlighterConfigV1` JSON to clipboard. Shows toast "Copied ✓".
- **Import:** Opens a `<textarea>` modal/inline area. User pastes JSON, clicks "Apply". Validates that it has a `rules` array. On success: persists to storage, re-renders UI, toast "Imported ✓". On invalid JSON or missing `rules`: toast "Invalid config".
- No file picker needed — clipboard/paste is sufficient.

### F2: Drag-to-Reorder Rules

Replace the ↑/↓ buttons in the rules table with native HTML5 drag-and-drop.

- Each `<tr>` gets a drag handle (≡ grip icon) on the left.
- Dragging a row reorders it in the `<tbody>`.
- The ↑/↓ buttons and their `<th>`/`<td>` column are removed.
- Keep the existing `moveUp`/`moveDown` click handlers as fallback for accessibility (triggered by handle keyboard events).
- Visual feedback: dragged row gets reduced opacity; drop target shows a 2px accent line.

## Batch 2: Sidebar & Visual

### F3: Sidebar Tag Filter Bar

Inject a horizontal pill bar at the top of the `#history` sidebar.

- Shows one pill per configured tag rule (e.g., `[TODO]`, `[BUG]`), plus an "All" pill.
- Pill color matches the tag's configured color.
- Clicking a pill filters the sidebar: only conversations matching that tag are visible. Others get `display: none`.
- Clicking "All" (or clicking the active pill again) removes the filter.
- Active pill gets a stronger background (same pattern as active sidebar item).
- The filter bar is only visible when there are 2+ rules.
- Filter state is ephemeral (not persisted — resets on page reload).

### F4: Theme-Aware Overlay

Detect ChatGPT's dark/light theme and adjust overlay + highlight colors.

- ChatGPT sets `class="dark"` or `class="light"` on `<html>`.
- **Dark mode** (current default): overlay background `rgba(0,0,0,0.72)`, highlight bg `rgba(color, 0.12)`.
- **Light mode**: overlay background `rgba(255,255,255,0.85)`, overlay text `rgba(0,0,0,0.88)`, highlight bg `rgba(color, 0.10)`, overlay border `rgba(0,0,0,0.10)`.
- Use a CSS class on `<html>` (e.g., `cth-light`) toggled by a small MutationObserver on `<html>` class attribute.
- All color adjustments via CSS — no JS style changes needed at runtime.

### F5: Per-Rule Overlay Toggle

Add a checkbox column "Overlay" to the rules table in options.

- Default: `true` (show overlay for this rule) — backward compatible.
- When `false`, the overlay banner is not shown for conversations matching this rule, even though the sidebar highlight still applies.
- Config schema adds `overlay: boolean` to each rule (default `true`).
- `content.js` checks `r.overlay !== false` before showing the overlay.

## Batch 3: New Capabilities

### F6: "Untagged" Catch-All Rule

A toggle in the General section: **"Dim untagged conversations"**.

- When enabled, sidebar items that match NO rule get reduced opacity (`opacity: 0.45`).
- Implemented via CSS: `#history a[data-sidebar-item="true"]:not([data-cth="1"]) { opacity: 0.45; }`.
- The CSS rule is injected only when the toggle is on.
- Config schema adds `dimUntagged: boolean` (default `false`).
- Toggled via a class on `<html>` (e.g., `cth-dim-untagged`).

### F7: Extension Badge Counter

Show the count of visible tagged conversations on the extension icon.

- `content.js` counts visible (non-hidden) tagged anchors after each sidebar scan.
- Sends count to background via `chrome.runtime.sendMessage({ type: 'badgeCount', count: N })`.
- `background.js` listens and calls `chrome.action.setBadgeText({ text: String(N) })` with badge background color from the first rule's color.
- When count is 0, clears the badge.
- Config schema adds `showBadge: boolean` (default `true`).

### F8: Keyboard Shortcuts

Global keyboard shortcuts on chatgpt.com (captured by content.js):

- **Alt+H**: Toggle visibility of hidden conversations (temporarily show all hidden items, press again to re-hide).
- **Alt+F**: Focus the filter bar (if F3 is active). If no filter bar, no-op.

Shortcuts are always active — no config toggle needed.

## Config Schema (after all features)

```json
{
  "rules": [
    { "tag": "[TODO]", "match": "startsWith", "color": "#fabd2f", "hide": false, "overlay": true }
  ],
  "maxChatTurns": 0,
  "hideNavBar": true,
  "dimUntagged": false,
  "showBadge": true
}
```

## Non-Goals

- No regex matching
- No file-based import/export (clipboard only)
- No persistent filter state
- No custom keyboard shortcut remapping

## Test Strategy

- **Unit tests (unit_test.html):** Add tests for any new pure functions (e.g., config migration with new fields).
- **E2E tests (test_extension.py):** Add tests for import/export, new config fields migration, badge counter, options page new UI elements.
- **Manual verification:** Sidebar filter bar, drag-to-reorder, theme detection, keyboard shortcuts (these require live ChatGPT DOM).
