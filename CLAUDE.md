# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Manifest V3 browser extension (Chrome + Firefox) that styles ChatGPT's sidebar chat list by literal title tags such as `[TODO]`. Plain vanilla JS in IIFEs — no npm, bundler, transpiler, or runtime dependencies. Do not add any.

## Commands

`src/` is the only source of truth, but it has **no `manifest.json`** — only `manifest.chrome.json` / `manifest.firefox.json` templates. Always build before loading or testing; `dist/` is generated and gitignored.

```sh
# Build dist/chrome, dist/firefox, and the .zip/.xpi (needs bash, python3, zip)
./publish.sh --version 0.0.99

# JS syntax check (what CI runs; there is no linter config)
for f in src/*.js; do node --check "$f"; done

# One-time test setup (versions pinned in tests/requirements.txt)
python3 -m venv .venv && source .venv/bin/activate
pip install -r tests/requirements.txt && playwright install chromium

# Full suite — runs against dist/chrome, so rebuild first
CI=true pytest tests/test_extension.py -v

# Single test / single class
CI=true pytest tests/test_extension.py::TestOptionsPage::test_save_persists_config -v
CI=true pytest tests/test_extension.py -k TestContentScript -v

# Firefox bundle static lint (CI)
npx --yes web-ext@8.3.0 lint --source-dir dist/firefox --warnings-as-errors=false --self-hosted

# Wiki + release tooling (CI docs job)
python3 scripts/check-wiki.py wiki
bash scripts/test-wiki-publish.sh
python3 scripts/release-check.py            # manifests agree + CHANGELOG section exists
bash scripts/test-release-check.sh
```

Tests launch **headed** Chromium (extensions don't load reliably headless); CI wraps pytest in `xvfb-run -a --server-args="-screen 0 1280x900x24"`.

**Always pass `CI=true` for automated runs.** Without it the suite uses the persistent `tests/.test-profile/`, which holds the maintainer's ChatGPT login and extension settings. Never delete that directory, copy its cookies, or run two browsers on it at once. ChatGPT cookies are short-lived: for live checks use one `launch_persistent_context` for the whole session with `ignore_default_args=['--enable-automation', '--disable-extensions']` (see `.github/copilot-instructions.md`), and do not close/reopen between steps.

## Architecture

Three scripts share one storage key, `tagHighlighterConfigV1` (read from `storage.sync`, falling back to `storage.local`):

- `background.js` seeds defaults and migrates missing fields on install/startup, and sets the extension badge from `badgeCount` messages (one global badge, not per tab).
- `options.js` renders/edits rules and auto-saves the whole config. It has no `storage.onChanged` listener.
- `content.js` compiles the config, styles `#history` sidebar anchors, and live-reloads on `storage.onChanged`. Missing config or zero rules makes it return early by design.

Filter-pill selection is **separate UI state** under `tagHighlighterUiStateV1` in `storage.local` (debounced 400 ms), so options-page full-config writes never clobber it and pill clicks don't hit sync quotas.

Rule semantics: case-sensitive literal `startsWith` / `includes`; rules are evaluated in order and the **first match wins** for color, hiding, filtering, and overlay. Colors are always persisted as `#rrggbb`; legacy color names are only normalized on read. `LEGACY`/`PALETTE` are duplicated in `content.js` and `options.js` — keep them in sync. New config fields must default safely in all three scripts.

### content.js lifecycle and ChatGPT DOM hooks

ChatGPT's DOM changes without notice; these are the hooks `content.js` depends on (verified live Sep 2026):

- Sidebar: `#history` → `a[data-sidebar-item="true"]`, title in `.truncate span[dir="auto"]`. The selected chat has `data-active=""` (empty string) — test attribute *presence*, and treat `data-active="false"` as unselected.
- Composer (overlay geometry anchor): `#prompt-textarea` inside `form[data-type="unified-composer"]`; `div.bg-token-bg-primary` is the legacy fallback.
- Native scroll-to-bottom button: an unlabelled, `aria-hidden` `<button>` inside a `main` wrapper whose class contains the Tailwind variant `data-scroll-from-end` (no `aria-label`/`data-testid`). It is hidden only under `html.cth-overlay-active`.
- Turns: `[data-testid="conversation-turn-N"]` — now `<section>`, formerly `<article>`; match the attribute, not the tag. The real scroller is an `overflow-y:auto` ancestor **above** `<main>`, and the composer lives inside it.
- `scrollToBottom` watches its smooth scroll and jumps to the current bottom if it stops short (e.g. content grew); it stops watching on user wheel/touch/key/pointer input.
- The right-side turn-navigation minimap targeted by `hideNavBar` was not present on current layouts (checked chats up to 10 turns); that option is currently a no-op. Don't invent a replacement selector without observing the real element.

Work is batched through `requestAnimationFrame` schedulers (`scheduleSidebarScan`, `scheduleOverlayUpdate`, `scheduleOverlayLayout`, `scheduleTurnWork`), and a `WeakMap` title cache skips unchanged anchors. A history observer watches `#history` (child list, text, `data-active`/`aria-current`/`class`); a document-level root observer rebinds when `#history` is replaced and re-lays-out the overlay. The overlay tracks "wanted" (active chat matches an overlay rule) separately from "shown" (a measurable composer exists), so it recovers when the composer re-mounts. While shown it sets `html.cth-overlay-active`, which is the only time ChatGPT's native scroll-to-bottom button is hidden. Rule-hidden chats are hidden by CSS unless `html.cth-reveal-hidden` (Alt+H) is set. Styling uses `--cth-*` custom properties plus `data-cth*` attributes, not inline styles. The content script runs in an isolated world, so its `history.pushState` patch does not see ChatGPT's own navigations — rely on DOM observers.

Long conversations: `scheduleTurnWork` runs pruning (`maxChatTurns`, removes DOM nodes until reload) and lazy rendering (`lazyRenderTurns`, default on). With ≥ 20 turns, every turn except the newest 4 gets `data-cth-lazy="1"` and a measured `--cth-turn-h`; under `html.cth-lazy-turns` that applies `content-visibility: auto` with the measured height as `contain-intrinsic-block-size`, so the scrollbar doesn't jump. Heights are read in one batch before any writes. The document-level turn observer only runs while one of these features is enabled. On a ~200-turn live thread this cut style/layout work about 4×.

Keep new DOM work inside these schedulers, and avoid writing attributes the history observer watches from within a scan (mutation loops).

## Testing notes

- `TestContentScript` in `tests/test_extension.py` loads the **packaged** `dist/chrome` and serves synthetic ChatGPT markup at `https://chatgpt.com/` via `page.route`. Its fixtures mirror the live hooks above; when ChatGPT changes, update the fixture from inspected live DOM structure (never real titles/messages), write the failing test, then fix.
- `tests/unit_test.html` tests *copies* of pure helpers (`toHex`, `compileConfig`, `matchRule`, …); it does not exercise the real `content.js`.
- Fixture passes are not proof of live compatibility. For live checks, drive the real extension on chatgpt.com read-only: never send, create, rename, or delete chats.
- chatgpt.com's CSP forbids `unsafe-eval`: pass a **function**, not a string, to Playwright's `wait_for_function` there. A string predicate that isn't already true throws `EvalError` almost immediately, which a `try/except` or `.catch()` silently turns into a false "timeout".
- Firefox is only statically linted in CI; runtime behavior there is untested.

## Releasing

`publish.sh --version` only writes the version into the staged `dist/*/manifest.json`. For a release, bump `version` in **both** `src/manifest.*.json` and add a `## [X.Y.Z]` CHANGELOG section; `python3 scripts/release-check.py` verifies they agree (CI runs it on every PR). Tag `vX.Y.Z` only on a `main` commit with a green `Tests` run: `release.yml` validates the tag, manifests, CHANGELOG, main ancestry and CI result, builds with checksums, and publishes notes from the CHANGELOG. `-suffix` tags become prereleases (manifests stay numeric). Store uploads are manual.

CI (`test.yml`): all actions are SHA-pinned with a version comment, every job and step has `timeout-minutes`, and `CI status` is the single aggregate check. Keep that pattern when adding steps.

Wiki: `wiki/` is the source; the GitHub wiki is a generated mirror published by `publish-wiki.yml` on push to `main`. Every page is an English + `-zh-CN` pair with matching headings; links use bare page names (no `.md`); Home lists every page. Run `python3 scripts/check-wiki.py wiki` after editing.

Settings use `storage.sync` (browser sync may copy them across devices); don't describe them as local-only.
