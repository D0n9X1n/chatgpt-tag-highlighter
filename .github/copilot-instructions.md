# Copilot Instructions — ChatGPT Tag Highlighter

## What this is

A browser extension (Chrome + Firefox) that highlights ChatGPT sidebar conversations based on title tags like `[TODO]` and `[BUG]`. It adds colored left stripes and backgrounds to matching items. No build tools, no bundler, no framework — plain vanilla JS.

## Architecture

### Dual-manifest, shared source

All runtime code lives in `src/`. Chrome and Firefox share the same JS/HTML/CSS but use separate manifest templates:

- `src/manifest.chrome.json` — uses `service_worker` for background
- `src/manifest.firefox.json` — uses `scripts` array for background, includes `browser_specific_settings.gecko`

The `publish.sh` script copies `src/` into `dist/chrome/` and `dist/firefox/`, injects the correct `manifest.json` with a bumped version, and produces `.zip` (Chrome) and `.xpi` (Firefox).

### Key files

- **`content.js`** — Content script injected into `chatgpt.com`. Reads config from storage, compiles tag rules, scans the `#history` sidebar via MutationObserver, applies CSS custom properties (`--cth-color`, `--cth-bg`, `--cth-bg-strong`) to matching anchors, manages a floating overlay, filter bar, theme detection, badge counter, and keyboard shortcuts.
- **`background.js`** — Service worker / background script. Seeds default config on install/startup, performs lightweight migration to add new fields, handles badge counter messages from content.js.
- **`options.js` + `options.html` + `options.css`** — Settings page. Renders tag rules table from a `<template>`, handles palette/hex color selection, import/export, drag-to-reorder, and persists config.

### Data flow

All three scripts share the storage key `tagHighlighterConfigV1`. The config schema is:

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

- `background.js` seeds defaults and migrates on install
- `options.js` reads, edits, and persists config
- `content.js` reads config at load and live-reloads via `storage.onChanged`

### Browser API compatibility

All three scripts detect the extension API at runtime (`browser` vs `chrome`) and wrap `storage.get`/`storage.set` in a promise/callback-compatible helper. Storage prefers `sync`, falls back to `local`.

## Build & publish

```sh
./publish.sh --version 1.0.0
```

This produces `dist/chatgpt-tag-highlighter-chrome-1.0.0.zip` and `dist/chatgpt-tag-highlighter-firefox-1.0.0.xpi`. Requires `python3` and `zip`.

There is no build step for development — load `src/` directly as an unpacked extension in Chrome, or as a temporary add-on in Firefox.

## Testing

### Setup (one-time)

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install playwright pytest
playwright install chromium
```

### Unit tests

Open `tests/unit_test.html` in a browser. Tests pure functions (`toHex`, `hexToRgba`, `compileConfig`, `matchRule`).

### E2E tests (automated, options page)

```sh
./publish.sh --version 1.0.0          # build dist/chrome/ first
source .venv/bin/activate
pytest tests/test_extension.py -v
```

These tests run headless-compatible Chrome with the extension loaded. They test the options page UI, config persistence, migration, import/export, and drag-reorder.

### Live tests (ChatGPT, requires login)

**CRITICAL — Playwright session management rules:**

1. **The user only logs in ONCE.** The login session is stored in `tests/.test-profile/`.
2. **NEVER delete `tests/.test-profile/`.** This contains the ChatGPT login cookies and session data.
3. **ChatGPT uses short-lived cookies** that expire when the browser closes. Therefore:
   - Run ALL live tests in a **single browser session** (one `launch_persistent_context` → all tests → one `close`).
   - Do NOT close and reopen the browser between test steps.
4. **Required launch args** for Playwright persistent context:
   ```python
   ctx = pw.chromium.launch_persistent_context(
       'tests/.test-profile',
       headless=False,
       args=[
           f'--disable-extensions-except={EXT_PATH}',
           f'--load-extension={EXT_PATH}',
           '--disable-blink-features=AutomationControlled',
       ],
       ignore_default_args=['--enable-automation', '--disable-extensions'],
   )
   ```
   - `ignore_default_args` **must** include both `--enable-automation` and `--disable-extensions`.
5. **If `tests/.test-profile/` does not exist**, launch the browser, let the user log in, close it, then run tests. Only do this once.

## Conventions

- **No build tools or dependencies.** Everything is vanilla JS with IIFEs (`(() => { ... })()`). No npm, no bundler, no transpiler.
- **Colors are always stored as `#RRGGBB` hex.** Legacy color names (e.g. `"red"`, `"gruvboxYellow"`) are accepted on read and normalized to hex. Never persist non-hex color values.
- **Gruvbox palette.** The color scheme uses Gruvbox colors. The `LEGACY` and `PALETTE` maps are duplicated across `content.js` and `options.js` — keep them in sync when modifying.
- **Performance-first DOM work.** Sidebar scans and overlay updates are batched via `requestAnimationFrame`. The `itemCache` WeakMap skips unchanged items. Keep this pattern when adding DOM operations.
- **CSS custom properties for styling.** Highlight colors are applied as `--cth-*` CSS variables on each anchor, not inline styles. The `<style>` block injected by `content.js` references these variables.
- **`DEBUG` flag in `content.js`.** Set `const DEBUG = true` for console logging during development; flip to `false` for release.
- **Backward-compatible config migration.** New config fields must default safely. `background.js`, `options.js`, and `content.js` all tolerate missing fields.
