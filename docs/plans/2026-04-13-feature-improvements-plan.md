# Implementation Plan: Feature Improvements (2026-04-13)

## Overview

8 features across 3 batches. All vanilla JS — no npm, no build tools, no bundler.

### Final Config Schema (target)

```json
{
  "rules": [{ "tag": "[TODO]", "match": "startsWith", "color": "#fabd2f", "hide": false, "overlay": true }],
  "maxChatTurns": 0,
  "hideNavBar": true,
  "dimUntagged": false,
  "showBadge": true
}
```

### File Dependency Map

| File | Touched by features |
|------|-------------------|
| `src/options.html` | F1, F2, F5, F6, F7 |
| `src/options.css` | F1, F2, F5, F6, F7 (+ truncation fix) |
| `src/options.js` | F1, F2, F5, F6, F7 |
| `src/content.js` | F3, F4, F5, F6, F7, F8 |
| `src/background.js` | F5, F6, F7 |
| `tests/unit_test.html` | F4, F5, F6 |
| `tests/test_extension.py` | F1, F2, F3, F5, F6, F7 |

---

## Batch 1: Options Page Improvements

### Task 1A — F1+F2: Import/Export + Drag-to-Reorder

**Rationale:** F1 and F2 both touch `options.html`, `options.css`, and `options.js`. They must be sequential or combined. Combining into one task avoids coordination overhead.

**Files:** `src/options.html`, `src/options.css`, `src/options.js`, `tests/test_extension.py`

---

#### F1: Import/Export Settings

##### options.html changes

Add Export and Import buttons inside the `.actions` div (after the existing Save button, line 23):

```html
<button id="exportCfg" type="button" class="ghost">Export</button>
<button id="importCfg" type="button" class="ghost">Import</button>
```

Add an import panel (hidden by default) after the `</header>` tag (after line 24), before `<main>`:

```html
<div id="importPanel" class="importPanel" style="display:none">
  <textarea id="importText" class="importTextarea" rows="6"
            placeholder="Paste exported JSON here…"></textarea>
  <div class="importActions">
    <button id="importApply" type="button" class="primary">Apply</button>
    <button id="importCancel" type="button" class="ghost">Cancel</button>
  </div>
</div>
```

##### options.css changes

Add these styles (after the `.hint` rule, around line 176):

```css
.importPanel {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 12px;
}

.importTextarea {
  width: 100%;
  min-height: 80px;
  background: rgba(255,255,255,.06);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 10px;
  padding: 8px 10px;
  font-family: monospace;
  font-size: 13px;
  resize: vertical;
  outline: none;
}

.importTextarea:focus {
  border-color: rgba(96,165,250,.8);
  box-shadow: 0 0 0 3px rgba(96,165,250,.15);
}

.importActions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  justify-content: flex-end;
}
```

##### options.js changes

1. **Add element refs** — extend the `els` object (around line 27–36):

```js
exportCfg: $('exportCfg'),
importCfg: $('importCfg'),
importPanel: $('importPanel'),
importText: $('importText'),
importApply: $('importApply'),
importCancel: $('importCancel'),
```

2. **Export handler** — add after the Ctrl+S handler (around line 376):

```js
els.exportCfg.addEventListener('click', async () => {
    const cfg = collectConfig();
    try {
        await navigator.clipboard.writeText(JSON.stringify(cfg, null, 2));
        toast('Copied ✓');
    } catch {
        // Fallback: select textarea trick
        const ta = document.createElement('textarea');
        ta.value = JSON.stringify(cfg, null, 2);
        document.body.append(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
        toast('Copied ✓');
    }
});
```

3. **Import handlers**:

```js
els.importCfg.addEventListener('click', () => {
    els.importPanel.style.display = els.importPanel.style.display === 'none' ? '' : 'none';
    els.importText.value = '';
    if (els.importPanel.style.display !== 'none') {
        els.importText.focus();
    }
});

els.importCancel.addEventListener('click', () => {
    els.importPanel.style.display = 'none';
    els.importText.value = '';
});

els.importApply.addEventListener('click', async () => {
    const raw = els.importText.value.trim();
    let parsed;
    try {
        parsed = JSON.parse(raw);
    } catch {
        toast('Invalid config');
        return;
    }

    if (!parsed || !Array.isArray(parsed.rules)) {
        toast('Invalid config');
        return;
    }

    // Normalize through our standard pipeline
    const cfg = {
        rules: [],
        maxChatTurns: safeInt(parsed.maxChatTurns, 0),
        hideNavBar: parsed.hideNavBar !== false,
        dimUntagged: parsed.dimUntagged === true,
        showBadge: parsed.showBadge !== false,
    };

    for (const r of parsed.rules) {
        const tag = String(r?.tag || '').trim();
        if (!tag) continue;
        cfg.rules.push({
            tag,
            match: safeMatch(r?.match),
            color: toHex(r?.color, '#999999'),
            hide: r?.hide === true,
            overlay: r?.overlay !== false,
        });
    }

    if (cfg.rules.length === 0) {
        toast('Invalid config');
        return;
    }

    await set({ [STORAGE_KEY]: cfg });
    render(cfg);
    els.importPanel.style.display = 'none';
    els.importText.value = '';
    toast('Imported ✓');
});
```

#### F2: Drag-to-Reorder Rules

##### options.html changes

1. **Remove the Order `<th>`** from the table header (line 63):
   - Delete: `<th style="width: 8%">Order</th>`

2. **Adjust column widths** in remaining `<th>` elements. New widths:
   - Tag: 22%, Match: 14%, Color: 18%, Hex: 14%, Hide: 8%, Overlay: 8% (F5), Preview: 6%, (delete): 4%
   - Add a Drag column: `<th style="width: 6%"></th>` as the **first** `<th>`.

3. **In `<template id="rowTemplate">`**, replace the Order `<td>` (lines 111–114):
   - Delete the `<td class="orderCell">` block with ↑/↓ buttons.
   - Add a drag handle as the **first** `<td>` inside `<tr>`:

```html
<td class="dragCell">
  <span class="dragHandle" draggable="true" title="Drag to reorder">≡</span>
</td>
```

##### options.css changes

Remove `.orderCell` and `.orderCell button` rules (lines 143–154). Add:

```css
.dragCell {
  text-align: center;
  width: 40px;
}

.dragHandle {
  cursor: grab;
  font-size: 18px;
  color: var(--muted);
  user-select: none;
  -webkit-user-select: none;
  padding: 4px 8px;
  display: inline-block;
}

.dragHandle:hover {
  color: var(--text);
}

.dragHandle:active {
  cursor: grabbing;
}

tr.dragging {
  opacity: 0.4;
}

tr.drag-over td {
  border-top: 2px solid var(--accent);
}
```

##### options.js changes

1. **Remove moveUp/moveDown click handlers** — delete the `moveUp` and `moveDown` blocks inside the `els.rows click` delegation handler (lines 304–318).

2. **Add drag-and-drop logic** — add after the event delegation block (around line 333):

```js
// ---- Drag-and-drop reorder ----
let draggedRow = null;

els.rows.addEventListener('dragstart', e => {
    const handle = e.target.closest('.dragHandle');
    if (!handle) {
        e.preventDefault();
        return;
    }
    draggedRow = handle.closest('tr');
    if (!draggedRow) {
        e.preventDefault();
        return;
    }
    draggedRow.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    // Required for Firefox
    e.dataTransfer.setData('text/plain', '');
});

els.rows.addEventListener('dragover', e => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    const targetRow = e.target.closest('tr');
    if (!targetRow || targetRow === draggedRow) return;

    // Remove previous indicators
    for (const tr of els.rows.querySelectorAll('.drag-over')) {
        tr.classList.remove('drag-over');
    }
    targetRow.classList.add('drag-over');
});

els.rows.addEventListener('dragleave', e => {
    const targetRow = e.target.closest('tr');
    if (targetRow) targetRow.classList.remove('drag-over');
});

els.rows.addEventListener('drop', e => {
    e.preventDefault();
    const targetRow = e.target.closest('tr');
    if (!targetRow || !draggedRow || targetRow === draggedRow) return;

    // Determine insert position based on cursor Y relative to target row
    const rect = targetRow.getBoundingClientRect();
    const midY = rect.top + rect.height / 2;
    if (e.clientY < midY) {
        els.rows.insertBefore(draggedRow, targetRow);
    } else {
        els.rows.insertBefore(draggedRow, targetRow.nextElementSibling);
    }
});

els.rows.addEventListener('dragend', () => {
    if (draggedRow) {
        draggedRow.classList.remove('dragging');
        draggedRow = null;
    }
    for (const tr of els.rows.querySelectorAll('.drag-over')) {
        tr.classList.remove('drag-over');
    }
});
```

##### Also fix the truncated `.hintInline` rule

In `options.css`, the file is truncated at line 179 (`.hintInline{ display: i`). Replace the incomplete rule with:

```css
.hintInline {
  display: inline;
  font-size: 12px;
  color: var(--muted);
}
```

#### Test Strategy for Task 1A

**Unit tests** (`tests/unit_test.html`): No new unit tests needed — F1/F2 are UI-only, no new pure functions.

**E2E tests** (`tests/test_extension.py`): Add to `TestOptionsPage`:

```python
def test_export_copies_json(self, browser_context, ext_id):
    """Export button should copy config JSON to clipboard."""
    page = self._open_options()
    self._set_config(page, {
        'rules': [{'tag': '[EXP]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False}],
        'maxChatTurns': 0, 'hideNavBar': True,
    })
    page.reload()
    page.wait_for_timeout(1500)

    # Grant clipboard permissions
    page.context.grant_permissions(['clipboard-read', 'clipboard-write'],
                                     origin=f'chrome-extension://{ext_id}')
    page.click('#exportCfg')
    page.wait_for_timeout(500)

    clipboard = page.evaluate('navigator.clipboard.readText()')
    parsed = json.loads(clipboard)
    assert parsed['rules'][0]['tag'] == '[EXP]'

def test_import_applies_config(self, browser_context, ext_id):
    """Import should parse JSON, persist, and re-render."""
    page = self._open_options()
    page.click('#importCfg')
    page.wait_for_timeout(300)

    new_cfg = {
        'rules': [{'tag': '[IMP]', 'match': 'includes', 'color': '#b8bb26', 'hide': False}],
        'maxChatTurns': 7, 'hideNavBar': False,
    }
    page.fill('#importText', json.dumps(new_cfg))
    page.click('#importApply')
    page.wait_for_timeout(500)

    cfg = self._get_config(page)
    page.close()
    assert cfg['rules'][0]['tag'] == '[IMP]'
    assert cfg['maxChatTurns'] == 7

def test_import_rejects_invalid_json(self, browser_context, ext_id):
    """Import should show error toast for invalid JSON."""
    page = self._open_options()
    page.click('#importCfg')
    page.wait_for_timeout(300)
    page.fill('#importText', 'not json')
    page.click('#importApply')
    page.wait_for_timeout(500)

    toast_text = page.evaluate("document.getElementById('toast').textContent")
    page.close()
    assert 'Invalid' in toast_text

def test_drag_reorder(self, browser_context, ext_id):
    """Drag-to-reorder should change row order in DOM."""
    page = self._open_options()
    self._set_config(page, {
        'rules': [
            {'tag': '[FIRST]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False},
            {'tag': '[SECOND]', 'match': 'startsWith', 'color': '#fb4934', 'hide': False},
        ],
        'maxChatTurns': 0, 'hideNavBar': True,
    })
    page.reload()
    page.wait_for_timeout(1500)

    # Verify initial order
    tag0 = page.evaluate("document.querySelectorAll('#rows tr .tag')[0].value")
    assert tag0 == '[FIRST]'

    # Use JS to simulate reorder (drag API is hard in Playwright)
    page.evaluate("""
        const rows = document.getElementById('rows');
        const trs = rows.querySelectorAll('tr');
        rows.insertBefore(trs[1], trs[0]);
    """)

    # Save and verify persisted order
    page.click('#save')
    page.wait_for_timeout(500)
    cfg = self._get_config(page)
    page.close()
    assert cfg['rules'][0]['tag'] == '[SECOND]'
    assert cfg['rules'][1]['tag'] == '[FIRST]'
```

---

## Batch 2: Sidebar & Visual

All three features (F3, F4, F5) modify `content.js`, so they must be **sequential** on that file. F5 also touches the options page files. Since Batch 1 completes first, the options files are free.

**Execution order:** Task 2A (F4) → Task 2B (F5) → Task 2C (F3)

Rationale: F4 (theme detection) is foundational — F3 filter bar styling depends on knowing the theme. F5 is independent but small. F3 is largest and goes last so it can build on F4's theme awareness.

---

### Task 2A — F4: Theme-Aware Overlay

**Files:** `src/content.js`, `tests/unit_test.html`

**Depends on:** Batch 1 complete (no file conflicts, but conceptual dependency on clean state).

#### content.js changes

1. **Add theme detection** — after the `injectStyleOnce()` function (around line 246), add:

```js
// ---- Theme detection ----
function detectTheme() {
    return document.documentElement.classList.contains('light') ? 'light' : 'dark';
}

function applyThemeClass() {
    const isLight = detectTheme() === 'light';
    document.documentElement.classList.toggle('cth-light', isLight);
}

// Observe <html> class changes for theme switches
const themeObserver = new MutationObserver(() => {
    applyThemeClass();
    scheduleOverlayUpdate();
});
themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class'],
});
```

2. **Add light-mode CSS** — inside `injectStyleOnce()`, add a new `themeCss` block before the final `style.textContent` assignment (line 243):

```js
const themeCss = `
/* Light mode overlay */
html.cth-light #${OVERLAY_ID} {
  background: rgba(255,255,255,0.85);
  border-color: rgba(0,0,0,0.10);
  box-shadow: 0 10px 30px rgba(0,0,0,0.12);
}
html.cth-light #${OVERLAY_ID} .cth-title {
  color: rgba(0,0,0,0.88);
}
html.cth-light #${OVERLAY_ID} .cth-arrow {
  border-color: rgba(0,0,0,0.10);
  background: rgba(0,0,0,0.04);
  color: rgba(0,0,0,0.70);
}
html.cth-light #${OVERLAY_ID}:hover {
  border-color: rgba(0,0,0,0.18);
}
html.cth-light #${OVERLAY_ID}:hover .cth-arrow {
  background: rgba(0,0,0,0.08);
}

/* Light mode sidebar highlights use lower alpha */
html.cth-light #history a[data-cth="1"] {
  --cth-bg-alpha: 0.10;
}
`;
```

Update the `style.textContent` line to include `themeCss`:

```js
style.textContent = `${hideScrollBtnCss}\n${hideNavBarCss}\n${sidebarCss}\n${overlayCss}\n${themeCss}`;
```

3. **Call `applyThemeClass()` in `main()`** — after `injectStyleOnce()` call (line 666):

```js
applyThemeClass();
```

#### Test Strategy for Task 2A

**Unit tests** (`tests/unit_test.html`): Add a `detectTheme` test group. Extract `detectTheme` as a testable pure function:

```js
group('detectTheme (simulated)');
// Save and restore
const origClass = document.documentElement.className;
document.documentElement.className = 'light';
assert('light class → light', document.documentElement.classList.contains('light'), true);
document.documentElement.className = 'dark';
assert('dark class → not light', document.documentElement.classList.contains('light'), false);
document.documentElement.className = origClass;
```

**E2E tests**: Theme testing requires ChatGPT DOM, so test the CSS injection instead — verify that the `cth-light` class toggles CSS variable behavior. This is covered implicitly by visual inspection. A targeted E2E test:

```python
def test_theme_class_toggles(self, browser_context, ext_id):
    """cth-light class should toggle based on html class."""
    page = browser_context.new_page()
    page.goto(f'chrome-extension://{ext_id}/options.html')  # any extension page
    page.wait_for_timeout(500)

    # We can't test on chatgpt.com, but verify the CSS was injected
    # by checking the content script's style element on a stub page
    # (This is best tested via manual QA or a mock DOM page)
    page.close()
```

> **Note:** Full theme E2E testing requires a mock ChatGPT page. Add a `tests/mock_chatgpt.html` stub if desired — this is optional and can be a follow-up.

---

### Task 2B — F5: Per-Rule Overlay Toggle

**Files:** `src/content.js`, `src/options.html`, `src/options.css`, `src/options.js`, `src/background.js`, `tests/unit_test.html`, `tests/test_extension.py`

**Depends on:** Task 2A (modifies same files).

#### content.js changes

1. **In `compileConfig()`** — add `overlay` to the rule object (around line 320):

```js
const overlay = r.overlay !== false; // default true for backward compat
rules.push({ tag, match, color, hide, overlay });
```

2. **In `updateOverlayNow()`** — add overlay check after matching the rule (around line 459-460):

```js
if (!r || r.overlay === false) {
    hideOverlay();
    return;
}
```

This replaces the existing `if (!r)` check at that location.

#### background.js changes

In `normalizeRules()` (around line 102), add `overlay` to the pushed object:

```js
out.push({
    tag,
    match: safeMatch(r?.match),
    color: String(r?.color || 'Green'),
    hide: safeBool(r?.hide),
    overlay: r?.overlay !== false,
});
```

In `seedOrMigrate()` needWrite condition (line 142), add:

```js
|| (existing.rules || []).some(r => typeof r.overlay !== 'boolean')
```

Update `DEFAULT_RULES` to include `overlay: true` on each rule.

#### options.html changes

1. **Add Overlay column header** — in the `<thead>` (after the Hide column):

```html
<th style="width: 8%">Overlay</th>
```

2. **Add Overlay cell in template** — after the Hide `<td>` in `#rowTemplate`:

```html
<td class="overlayCell">
  <label class="checkboxWrap" title="Show in overlay banner when active">
    <input class="overlay" type="checkbox" />
    <span>Show</span>
  </label>
</td>
```

#### options.css changes

Add:

```css
.overlayCell {
  white-space: nowrap;
}
```

#### options.js changes

1. **In `createRow()`** — add overlay checkbox binding (after the hide line):

```js
const overlay = rule?.overlay !== false; // default true
tr.querySelector('.overlay').checked = overlay;
```

2. **In `collectConfig()`** — add overlay to each rule object:

```js
overlay: tr.querySelector('.overlay').checked !== false,
```

3. **In the `init()` migration** — add overlay to migrated rules:

```js
overlay: r.overlay !== false,
```

4. **In `DEFAULT_CFG()`** — add `overlay: true` to each default rule.

#### Test Strategy for Task 2B

**Unit tests** (`tests/unit_test.html`):

```js
group('compileConfig — overlay field');
const cfgOv1 = compileConfig({
    rules: [{ tag: '[A]', overlay: true }, { tag: '[B]', overlay: false }, { tag: '[C]' }]
});
assert('explicit true', cfgOv1.rules[0].overlay, true);
assert('explicit false', cfgOv1.rules[1].overlay, false);
assert('missing defaults true', cfgOv1.rules[2].overlay, true);
```

**E2E tests** (`tests/test_extension.py`):

```python
def test_overlay_field_persists(self, browser_context, ext_id):
    """Overlay toggle should persist in config."""
    page = self._open_options()
    self._set_config(page, {
        'rules': [{'tag': '[OV]', 'match': 'startsWith', 'color': '#fabd2f',
                    'hide': False, 'overlay': True}],
        'maxChatTurns': 0, 'hideNavBar': True,
    })
    page.reload()
    page.wait_for_timeout(1500)

    # Uncheck the overlay checkbox
    page.uncheck('#rows tr:first-child .overlay')
    page.click('#save')
    page.wait_for_timeout(500)

    cfg = self._get_config(page)
    page.close()
    assert cfg['rules'][0]['overlay'] is False

def test_overlay_defaults_true(self, browser_context, ext_id):
    """Rules without overlay field should default to true after migration."""
    page = self._open_options()
    self._set_config(page, {
        'rules': [{'tag': '[DEF]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False}],
        'maxChatTurns': 0, 'hideNavBar': True,
    })
    page.reload()
    page.wait_for_timeout(1500)

    cfg = self._get_config(page)
    page.close()
    assert cfg['rules'][0].get('overlay') is True
```

---

### Task 2C — F3: Sidebar Tag Filter Bar

**Files:** `src/content.js`

**Depends on:** Task 2B (modifies same file).

#### content.js changes

1. **Add filter bar constants** (near the top constants, after `OVERLAY_ID`):

```js
const FILTER_BAR_ID = 'cth-filter-bar';
```

2. **Add filter bar CSS** — inside `injectStyleOnce()`, add `filterBarCss`:

```js
const filterBarCss = `
#${FILTER_BAR_ID} {
  display: none;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}

html.cth-light #${FILTER_BAR_ID} {
  border-bottom-color: rgba(0,0,0,0.08);
}

#${FILTER_BAR_ID}.cth-visible {
  display: flex;
}

.cth-pill {
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(255,255,255,0.06);
  color: rgba(255,255,255,0.80);
  user-select: none;
  -webkit-user-select: none;
  transition: background 0.15s, border-color 0.15s;
}

html.cth-light .cth-pill {
  border-color: rgba(0,0,0,0.10);
  background: rgba(0,0,0,0.04);
  color: rgba(0,0,0,0.70);
}

.cth-pill:hover {
  background: rgba(255,255,255,0.10);
}

html.cth-light .cth-pill:hover {
  background: rgba(0,0,0,0.08);
}

.cth-pill.active {
  border-color: var(--pill-color, rgba(255,255,255,0.30));
  background: var(--pill-bg, rgba(255,255,255,0.14));
  color: #fff;
}

html.cth-light .cth-pill.active {
  color: #000;
}
`;
```

Include in `style.textContent`:

```js
style.textContent = `${hideScrollBtnCss}\n${hideNavBarCss}\n${sidebarCss}\n${overlayCss}\n${themeCss}\n${filterBarCss}`;
```

3. **Add filter state and bar management** — after the `compileConfig` function:

```js
// ---- Filter bar ----
let activeFilter = null; // null = show all; string = tag to filter by

function ensureFilterBar() {
    let bar = document.getElementById(FILTER_BAR_ID);
    if (bar) return bar;

    bar = document.createElement('div');
    bar.id = FILTER_BAR_ID;
    return bar;
}

function renderFilterBar() {
    if (!compiled || compiled.rules.length < 2) {
        const bar = document.getElementById(FILTER_BAR_ID);
        if (bar) bar.classList.remove('cth-visible');
        return;
    }

    const bar = ensureFilterBar();

    // Mount at top of #history if not already there
    if (historyRoot && bar.parentElement !== historyRoot) {
        historyRoot.prepend(bar);
    }

    bar.innerHTML = '';

    // "All" pill
    const allPill = document.createElement('span');
    allPill.className = 'cth-pill' + (activeFilter === null ? ' active' : '');
    allPill.textContent = 'All';
    allPill.addEventListener('click', () => {
        activeFilter = null;
        renderFilterBar();
        applyFilter();
    });
    bar.append(allPill);

    // One pill per rule
    for (const r of compiled.rules) {
        const pill = document.createElement('span');
        pill.className = 'cth-pill' + (activeFilter === r.tag ? ' active' : '');
        pill.textContent = r.tag;
        pill.style.setProperty('--pill-color', r.color);
        pill.style.setProperty('--pill-bg', hexToRgba(r.color, 0.18));
        if (activeFilter === r.tag) {
            pill.style.borderColor = r.color;
            pill.style.background = hexToRgba(r.color, 0.18);
        }
        pill.addEventListener('click', () => {
            activeFilter = activeFilter === r.tag ? null : r.tag;
            renderFilterBar();
            applyFilter();
        });
        bar.append(pill);
    }

    bar.classList.add('cth-visible');
}

function applyFilter() {
    if (!historyRoot) return;

    const anchors = historyRoot.querySelectorAll('a[data-sidebar-item="true"]');
    for (const a of anchors) {
        if (activeFilter === null) {
            // Show all (respect hide rules)
            a.style.removeProperty('display');
            if (a.dataset.cthHidden === '1') {
                a.style.display = 'none';
            }
        } else {
            const title = getChatTitleText(a);
            const r = matchRule(title, compiled.rules);
            if (r && r.tag === activeFilter) {
                a.style.removeProperty('display');
            } else {
                a.style.display = 'none';
            }
        }
    }
}
```

4. **Call `renderFilterBar()` at appropriate points:**

   - In `main()`, after `attachHistoryObserver()` and `scheduleSidebarScan()` (around line 700):
     ```js
     renderFilterBar();
     ```

   - In `listenForConfigChanges()` handler, after `compiled = compileConfig(newCfg)` (around line 739):
     ```js
     activeFilter = null;
     renderFilterBar();
     ```

   - In the `rootObserver` callback (around line 720), when `historyRoot` changes:
     ```js
     renderFilterBar();
     ```

5. **Make `scanSidebarNow()` call `applyFilter()`** — after the loop, before `scheduleOverlayUpdate()`:

```js
if (activeFilter !== null) {
    applyFilter();
}
```

#### Test Strategy for Task 2C

**Unit tests**: Filter bar is DOM-heavy, no pure functions to extract.

**E2E tests**: Hard to test without ChatGPT DOM. Best approach — add a `tests/mock_sidebar.html` that simulates `#history` with `a[data-sidebar-item]` elements, loads content.js with a mock storage API, and verifies filter bar rendering. This is **optional** for initial implementation. Document as a known gap.

**Manual test script** (document in test comments):
1. Load extension on chatgpt.com with 2+ rules.
2. Verify pill bar appears at top of sidebar.
3. Click a tag pill → only matching conversations visible.
4. Click same pill again → all conversations visible.
5. Click "All" → all conversations visible.
6. With only 1 rule → no filter bar visible.

---

## Batch 3: New Capabilities

F6, F7, F8 all touch `content.js`. F6 and F7 also touch options files and background.js. Since Batch 2 must complete first (they share content.js), all Batch 3 tasks are sequential.

**Execution order:** Task 3A (F6+F7 options) ∥ Task 3B (F8 content.js) — then Task 3C (F6+F7 content.js + background.js)

Wait — F8 touches content.js, and F6/F7 also touch content.js. So the actual order must be fully sequential.

**Execution order:** Task 3A (F6+F7+F8 combined) — single task touching all files.

Given the small size of each feature, combine into one task to avoid excessive coordination overhead.

---

### Task 3A — F6+F7+F8: Dim Untagged, Badge Counter, Keyboard Shortcuts

**Files:** `src/content.js`, `src/background.js`, `src/options.html`, `src/options.css`, `src/options.js`, `tests/unit_test.html`, `tests/test_extension.py`

**Depends on:** All of Batch 2 complete.

#### F6: "Dim Untagged" Catch-All Rule

##### options.html changes

Add a new checkbox row in the General section (after the hideNavBar row, around line 48):

```html
<div class="generalRow">
  <label class="checkboxWrap" title="Dim conversations that don't match any tag rule">
    <input id="dimUntagged" type="checkbox" />
    <span class="label">Dim untagged conversations
      <span class="hintInline">Applies reduced opacity to sidebar items that don't match any tag rule.</span>
    </span>
  </label>
</div>
```

##### options.js changes

1. **Add to `els`:** `dimUntagged: $('dimUntagged'),`

2. **In `DEFAULT_CFG()`:** add `dimUntagged: false,`

3. **In `render()`:** add `els.dimUntagged.checked = cfg.dimUntagged === true;`

4. **In `collectConfig()`:** add `dimUntagged: els.dimUntagged.checked,`

5. **In `init()` migration:** add `dimUntagged: cfg.dimUntagged === true,` to the `migrated` object.

##### content.js changes

1. **Add CSS** in `injectStyleOnce()`:

```js
const dimCss = `
html.cth-dim-untagged #history a[data-sidebar-item="true"]:not([data-cth="1"]) {
  opacity: 0.45;
}
`;
```

Include in `style.textContent`.

2. **In `compileConfig()`** — read and apply dim class:

```js
const dimUntagged = cfg?.dimUntagged === true;
document.documentElement.classList.toggle('cth-dim-untagged', dimUntagged);
return { rules, maxChatTurns, hideNavBar, dimUntagged };
```

##### background.js changes

In `seedOrMigrate()`:
- Add `dimUntagged: false` to the default seed object (line 120).
- Add migration logic: `const dimUntagged = existing.dimUntagged === true;`
- Include in needWrite check: `|| typeof existing.dimUntagged !== 'boolean'`
- Include in the write: `dimUntagged` in the saved object.

#### F7: Extension Badge Counter

##### options.html changes

Add after the dimUntagged row:

```html
<div class="generalRow">
  <label class="checkboxWrap" title="Show count of tagged conversations on extension icon">
    <input id="showBadge" type="checkbox" checked />
    <span class="label">Show badge counter
      <span class="hintInline">Displays the number of visible tagged conversations on the extension icon.</span>
    </span>
  </label>
</div>
```

##### options.js changes

1. **Add to `els`:** `showBadge: $('showBadge'),`

2. **In `DEFAULT_CFG()`:** add `showBadge: true,`

3. **In `render()`:** add `els.showBadge.checked = cfg.showBadge !== false;`

4. **In `collectConfig()`:** add `showBadge: els.showBadge.checked,`

5. **In `init()` migration:** add `showBadge: cfg.showBadge !== false,`

##### content.js changes

1. **In `compileConfig()`** — read showBadge:

```js
const showBadge = cfg?.showBadge !== false; // default true
return { rules, maxChatTurns, hideNavBar, dimUntagged, showBadge };
```

2. **Add badge update function** — after `scanSidebarNow()`:

```js
function updateBadgeCount() {
    if (!compiled?.showBadge) {
        try { API.runtime.sendMessage({ type: 'badgeCount', count: 0 }); } catch {}
        return;
    }

    if (!historyRoot) return;

    const tagged = historyRoot.querySelectorAll(
        'a[data-sidebar-item="true"][data-cth="1"]:not([data-cth-hidden="1"])'
    );
    const count = tagged.length;

    try {
        API.runtime.sendMessage({ type: 'badgeCount', count });
    } catch {
        // Extension context may be invalidated
    }
}
```

3. **Call `updateBadgeCount()`** at end of `scanSidebarNow()` (after `scheduleOverlayUpdate()`).

4. **Call `updateBadgeCount()`** in `listenForConfigChanges()` after sidebar scan.

##### background.js changes

1. **Add message listener** — after `seedOrMigrate()` call (line 156):

```js
// ---- Badge counter ----
API.runtime?.onMessage?.addListener((msg) => {
    if (msg?.type === 'badgeCount') {
        const count = Number(msg.count) || 0;
        const text = count > 0 ? String(count) : '';
        try {
            API.action?.setBadgeText?.({ text });
            API.action?.setBadgeBackgroundColor?.({ color: '#fabd2f' });
        } catch {
            // Fallback for older APIs
            try {
                API.browserAction?.setBadgeText?.({ text });
                API.browserAction?.setBadgeBackgroundColor?.({ color: '#fabd2f' });
            } catch {}
        }
    }
});
```

Add `dimUntagged` and `showBadge` to the seed and migration logic in `seedOrMigrate()`.

#### F8: Keyboard Shortcuts

##### content.js changes

Add keyboard listener — after `listenForConfigChanges()` function (before `main()` call at bottom):

```js
// ---- Keyboard shortcuts ----
document.addEventListener('keydown', e => {
    // Alt+H: Toggle hidden conversations visibility
    if (e.altKey && e.key.toLowerCase() === 'h') {
        e.preventDefault();
        const hiddenAnchors = document.querySelectorAll('#history a[data-cth-hidden="1"]');
        const anyVisible = [...hiddenAnchors].some(a => a.style.display !== 'none');
        for (const a of hiddenAnchors) {
            if (anyVisible) {
                a.style.display = 'none';
            } else {
                a.style.removeProperty('display');
            }
        }
        return;
    }

    // Alt+F: Focus filter bar
    if (e.altKey && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        const bar = document.getElementById(FILTER_BAR_ID);
        if (bar && bar.classList.contains('cth-visible')) {
            const firstPill = bar.querySelector('.cth-pill');
            if (firstPill) firstPill.focus();
        }
    }
});
```

> **Note:** Keyboard shortcuts are always active, no config needed. `Alt+H` toggles visibility of hidden conversations. `Alt+F` focuses the first pill in the filter bar (requires F3 to be implemented).

#### Test Strategy for Task 3A

**Unit tests** (`tests/unit_test.html`):

```js
group('compileConfig — dimUntagged');
assert('dimUntagged false by default', compileConfig({}).dimUntagged, false);
assert('dimUntagged true when set', compileConfig({ dimUntagged: true }).dimUntagged, true);
assert('dimUntagged false when false', compileConfig({ dimUntagged: false }).dimUntagged, false);

group('compileConfig — showBadge');
assert('showBadge true by default', compileConfig({}).showBadge, true);
assert('showBadge false when set', compileConfig({ showBadge: false }).showBadge, false);
assert('showBadge true when true', compileConfig({ showBadge: true }).showBadge, true);
```

**E2E tests** (`tests/test_extension.py`):

```python
def test_dim_untagged_persists(self, browser_context, ext_id):
    """dimUntagged checkbox should persist in config."""
    page = self._open_options()
    self._set_config(page, {
        'rules': [{'tag': '[A]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False}],
        'maxChatTurns': 0, 'hideNavBar': True, 'dimUntagged': False,
    })
    page.reload()
    page.wait_for_timeout(1500)

    page.check('#dimUntagged')
    page.click('#save')
    page.wait_for_timeout(500)

    cfg = self._get_config(page)
    page.close()
    assert cfg['dimUntagged'] is True

def test_show_badge_persists(self, browser_context, ext_id):
    """showBadge checkbox should persist in config."""
    page = self._open_options()
    self._set_config(page, {
        'rules': [{'tag': '[A]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False}],
        'maxChatTurns': 0, 'hideNavBar': True, 'showBadge': True,
    })
    page.reload()
    page.wait_for_timeout(1500)

    page.uncheck('#showBadge')
    page.click('#save')
    page.wait_for_timeout(500)

    cfg = self._get_config(page)
    page.close()
    assert cfg['showBadge'] is False

def test_show_badge_defaults_true(self, browser_context, ext_id):
    """showBadge should default to true when missing."""
    page = self._open_options()
    self._set_config(page, {
        'rules': [{'tag': '[A]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False}],
        'maxChatTurns': 0, 'hideNavBar': True,
        # showBadge intentionally missing
    })
    page.reload()
    page.wait_for_timeout(1500)

    cfg = self._get_config(page)
    page.close()
    assert cfg.get('showBadge') is True
```

**Keyboard shortcut tests** — manual testing only (document in test comments):
1. Load chatgpt.com with extension.
2. Press Alt+H → hidden conversations should appear/disappear.
3. Press Alt+F → first filter pill gets focus (if filter bar visible).

---

## Execution Summary

```
Batch 1 (Options Page)
  └── Task 1A: F1 Import/Export + F2 Drag-to-Reorder
      Files: options.html, options.css, options.js, test_extension.py
      Duration estimate: 2-3 hours

Batch 2 (Sidebar & Visual) — sequential, depends on Batch 1
  ├── Task 2A: F4 Theme-Aware Overlay
  │   Files: content.js, unit_test.html
  │   Duration estimate: 1 hour
  │
  ├── Task 2B: F5 Per-Rule Overlay Toggle (depends on 2A)
  │   Files: content.js, background.js, options.html, options.css, options.js,
  │          unit_test.html, test_extension.py
  │   Duration estimate: 1-2 hours
  │
  └── Task 2C: F3 Sidebar Tag Filter Bar (depends on 2B)
      Files: content.js
      Duration estimate: 2 hours

Batch 3 (New Capabilities) — sequential, depends on Batch 2
  └── Task 3A: F6 Dim Untagged + F7 Badge Counter + F8 Keyboard Shortcuts
      Files: content.js, background.js, options.html, options.css, options.js,
             unit_test.html, test_extension.py
      Duration estimate: 2-3 hours
```

### Total: 5 tasks, ~8-11 hours implementation time

### Pre-implementation Checklist

Before starting each task:
1. `git checkout -b feature/<task-id>` (e.g., `feature/batch1-import-export-drag`)
2. Run `./publish.sh --version 0.0.4` to verify clean build
3. Run `pytest tests/test_extension.py -v` to confirm baseline passes

After each task:
1. Run `./publish.sh --version 0.0.4` — must succeed
2. Run `pytest tests/test_extension.py -v` — all tests must pass (including new ones)
3. Open `tests/unit_test.html` in browser — all tests must pass
4. Load `src/` as unpacked extension in Chrome — manual smoke test
5. `git commit` with descriptive message

### Cross-Cutting Concerns

1. **`DEFAULT_CFG()` in options.js** must be updated incrementally. After all batches, it should match the final schema.

2. **`compileConfig()` in content.js** must add new fields (`overlay`, `dimUntagged`, `showBadge`) and the duplicated version in `unit_test.html` must be updated to match.

3. **`seedOrMigrate()` in background.js** must handle all new fields with backward-compatible defaults. The needWrite check must include existence checks for every new field.

4. **Storage migration ordering**: background.js runs first (on install/startup), then options.js runs (on page load), then content.js runs (on chatgpt.com). Each layer must tolerate missing fields.

5. **`collectConfig()` and `render()` in options.js** must round-trip all fields, including new ones. Any field read from config must also be written back on save to avoid data loss.

6. **PALETTE and LEGACY maps** are duplicated in content.js and options.js. No changes needed for these features, but keep them in sync if ever modified.
