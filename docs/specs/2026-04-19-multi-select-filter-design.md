# Multi-Select Filter Bar — Design Spec

**Goal:** Allow selecting multiple tag pills simultaneously in the sidebar filter bar.

## Background

Currently `activeFilter` is a single string or null. Clicking a pill replaces the previous selection. Users want to see e.g. `[TODO]` AND `[BUG]` conversations at the same time.

## Design

### Behavior

- **No pills active** = "All" is highlighted, all conversations visible (current default behavior).
- **Click a tag pill** = toggle it on/off. Multiple pills can be active simultaneously.
- **"All" pill** = clears all selections, returns to show-all state. "All" is highlighted when no tag pills are active.
- **Click the last active pill off** = returns to show-all (same as clicking "All").
- Active pills get the existing strong-background style (colored border + bg).

### Data model change

```js
// Before:
let activeFilter = null;           // null | string

// After:
let activeFilters = new Set();     // empty = show all
```

### Filter logic change

- **Empty set** → show all (respect `hide` rules as before).
- **Non-empty set** → show conversations whose matched rule tag is in the set. Hide the rest.

### Files changed

Only `src/content.js` — the filter bar rendering, click handlers, and `applyFilter()`.

## Non-Goals

- No config persistence (filter state remains ephemeral).
- No changes to options page, background.js, or tests.

## Test Strategy

- **Unit tests:** No new pure functions — this is DOM behavior.
- **Live test:** Verify multi-select works on chatgpt.com by clicking multiple pills and checking sidebar visibility.
- **E2E automated tests:** Existing tests should still pass (no schema changes).
