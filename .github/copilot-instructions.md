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

- **`content.js`** — Content script injected into `chatgpt.com`. Reads config from storage, compiles tag rules, scans the `#history` sidebar via MutationObserver, applies CSS custom properties (`--cth-color`, `--cth-bg`, `--cth-bg-strong`) to matching anchors, and manages a floating overlay above the composer box.
- **`background.js`** — Service worker / background script. Seeds default config on install/startup, performs lightweight migration to add new fields (`hide`, `maxChatTurns`).
- **`options.js` + `options.html` + `options.css`** — Settings page. Renders tag rules table from a `<template>`, handles palette/hex color selection, persists config.

### Data flow

All three scripts share the storage key `tagHighlighterConfigV1`. The config schema is:

```json
{
  "rules": [
    { "tag": "[TODO]", "match": "startsWith", "color": "#fabd2f", "hide": false }
  ],
  "maxChatTurns": 0
}
```

- `background.js` seeds defaults and migrates on install
- `options.js` reads, edits, and persists config
- `content.js` reads config once at load and applies it

### Browser API compatibility

All three scripts detect the extension API at runtime (`browser` vs `chrome`) and wrap `storage.get`/`storage.set` in a promise/callback-compatible helper. Storage prefers `sync`, falls back to `local`.

## Build & publish

```sh
./publish.sh --version 0.0.3
```

This produces `dist/chatgpt-tag-highlighter-chrome-0.0.3.zip` and `dist/chatgpt-tag-highlighter-firefox-0.0.3.xpi`. Requires `python3` and `zip`.

There is no build step for development — load `src/` directly as an unpacked extension in Chrome, or as a temporary add-on in Firefox.

## Conventions

- **No build tools or dependencies.** Everything is vanilla JS with IIFEs (`(() => { ... })()`). No npm, no bundler, no transpiler.
- **Colors are always stored as `#RRGGBB` hex.** Legacy color names (e.g. `"red"`, `"gruvboxYellow"`) are accepted on read and normalized to hex. Never persist non-hex color values.
- **Gruvbox palette.** The color scheme uses Gruvbox colors. The `LEGACY` and `PALETTE` maps are duplicated across `content.js` and `options.js` — keep them in sync when modifying.
- **Performance-first DOM work.** Sidebar scans and overlay updates are batched via `requestAnimationFrame`. The `itemCache` WeakMap skips unchanged items. Keep this pattern when adding DOM operations.
- **CSS custom properties for styling.** Highlight colors are applied as `--cth-*` CSS variables on each anchor, not inline styles. The `<style>` block injected by `content.js` references these variables.
- **`DEBUG` flag in `content.js`.** Set `const DEBUG = true` for console logging during development; flip to `false` for release.
