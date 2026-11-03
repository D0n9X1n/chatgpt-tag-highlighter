# Quick tag + floating settings — design spec (v1.3.0)

**Goal:** one-click chat tagging and floating settings, without losing settings or corrupting chats.

## Requirements (one issue each)

- **R1 Quick tag.** Hovering or focusing a sidebar chat shows a tag button; its menu lists every `startsWith` rule (rule order, colour swatch, current tag checked), **Remove tag** when the title starts with a `startsWith` tag, and **New tag…**. Picking a tag renames the chat on ChatGPT: strip any existing `startsWith` tag prefix (longest match) and following spaces, then prepend `tag + ' '`. Picking the current tag is a no-op. `Alt+T` opens the menu for the focused or open chat. Option `showQuickTag` (default **on**).
- **R2 New tag.** Typed text (trimmed, 1–40 chars) becomes a `startsWith` rule with the first unused palette colour (else `#a7a7a7`) unless the tag already exists, then is applied as in R1.
- **R3 Undo + errors.** After a rename, a toast shows "Tagged · Undo" for 6 s; Undo restores the previous title with the same request. Failures show an error toast and change nothing.
- **R4 Settings button.** An icon-only gear (`aria-label` "Tag Highlighter settings") is the last item in the filter bar, after "Delete untagged…". The bar shows whenever ≥1 rule exists; pills still need ≥2 visible rules.
- **R5 Floating settings.** The gear and the toolbar icon open `options.html` in a popup window (560×720) via `background.js`; an open one is focused instead. If `windows.create` is missing or fails, fall back to `runtime.openOptionsPage()`. The toolbar icon works even with zero rules; the Firefox manifest gains an `action` key.
- **R6 No silently lost settings.** One writer: `background.js` applies every config write on one promise chain. content.js sends `{type:'addRule', tag}` (append to the freshest value). options.js sends `{type:'writeConfig', base, next}`: the write happens only if storage still equals `base` (compare-and-set); otherwise it returns `conflict` and nothing is written — if storage already equals `next` (a retried write that landed) it counts as saved. One options save is in flight at a time. On `storage.onChanged`, an options page with no unsaved edits re-renders; one with unsaved edits, or a save that hits `conflict`, keeps its draft on screen and shows "Settings changed in another window" with **Reload** (discards the draft). On messaging failure it keeps the draft, shows "Not saved — retrying", and retries the same write (1 s, 3 s, then on the next change); it never writes storage directly.
- **R7 Narrow options layout.** ≤640 px: wrapped header, stacked rule cards, no horizontal scroll.

UI detail: `2026-11-02-quick-tag-settings-ui-brief.md`.

## Rename mechanics

- Request: `PATCH /backend-api/conversation/{id}` `{"title": newTitle}`, Bearer token from `getAccessToken()`, via `pageFetch`. Failure = network error, `!ok`, or `success === false`; 401/403 → "Sign in to ChatGPT first", 429 → rate-limit text. Chat id comes from the row link `href` `/c/{id}` and must match `CHAT_ID_RE`; other links get no button.
- Identity guard: the menu binds the chat **id** and shown title at open. On pick, before PATCH, and again before updating the DOM, the row is re-found by id; missing or a different title aborts ("Title changed — try again"). Undo is refused ("Title changed — not undone") unless the chat's current title still equals the tagged title.
- Display: on success set `nodeValue` of the existing title text node (never add/remove nodes) and record `titleOverrides` id → {old, new}. While the DOM shows `old`, styling uses `new` and the scan re-applies `nodeValue`; the entry is dropped only when the DOM shows a third title (renamed elsewhere).
- Tests mock the routes; never a real account.

## Component map

| component | job | interface | reuses / extends | likely change | test seam |
|---|---|---|---|---|---|
| `quickTag` (content.js) | own the shared button, menu, toast | `showFor(anchor)`, `openMenu(anchor)`, `hide()` | `el()`, `getChatTargets`, `getChatTitleText`, cth-style CSS | ChatGPT row layout | Playwright app-shell + legacy fixtures |
| `computeTaggedTitle(title, tag, rules)` | pure prefix replace/remove | string → string | `matchRule` semantics | tag rules | unit_test.html copy + e2e |
| `renameChat(id, title)` | one PATCH, error mapping | `Promise<void>` throws `Error(message)` | `pageFetch`, `getAccessToken`, `readJson` | API shape | mocked route |
| config writer (background.js) | serialised compare-and-set + append | `writeConfig`, `addRule` messages | `storageGet/Set`, palette | config schema | background.js in a page with mocked storage, forced interleavings |
| settings gear | open settings | last button in `renderFilterBar` | `createDeleteButton` pattern | bar layout | click → popup |
| `openSettings` (background.js) | popup or fallback | message `{type:'openSettings'}`, `action.onClicked` | existing `onMessage` | browser APIs | new page event in test |
| options sync | R6 | `storage.onChanged`, conflict banner | `render()`, `collectConfig()` | — | two-page test |

## Prior art (from the validated survey)

| practice | fit | used |
|---|---|---|
| PATCH `{title}` + token (5 tools) | reuses delete code | yes |
| Re-fetch to verify | extra GET | no |
| iframe via WAR | Firefox unresolved | no |
| `windows.create` popup | no new permission | yes |
| Button as row sibling | nodes in React rows | no |

## Design check

Normal: pick `[BUG]` → PATCH 200 → nodeValue + override → Undo toast. Failure: 429 → error toast. One body-level button, so nothing enters React rows.

## Tests (must pass)

`./publish.sh --version 0.0.99 && for f in src/*.js; do node --check "$f"; done && CI=true pytest tests/test_extension.py -v` plus `python3 scripts/check-wiki.py wiki` and `python3 scripts/release-check.py`.

Release gate: `python3 scripts/release-check.py --tag v1.3.0`. The full test matrix (≈25 cases: identity, Undo refusal, override vs. remount, error mapping, two-page edit survival, R2 merge helper, menu keyboard, toast, gear thresholds, popup/fallback, narrow layout) lives in the plan. Visual tokens are checked by designer screenshot critique, not computed-style asserts.

## Non-goals

Bulk tagging; `includes` rules in the menu; options light theme; in-page settings editor; Projects chats; Firefox runtime checks.

## Docs

CHANGELOG + manifests 1.3.0; wiki Usage/Configuration/Privacy (+zh-CN); CLAUDE.md rename note.
