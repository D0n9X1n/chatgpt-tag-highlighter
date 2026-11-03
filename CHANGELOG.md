# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.3.1] — 2026-11-03

### Fixed
- **The settings window is wide enough for the rules**
  ([#79](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues/79)).
  It now opens at 1040×760, so every rule fits on one line with no cut-off
  menus, and it is never larger than the browser window it opens from.
  Below 1000 px wide each rule shows as a stacked card (previously only at
  640 px or narrower), so the fields stay readable. Colour presets now
  show just their names; the hex code stays in its own column.
- **The quick tag menu no longer lists Hide rules**
  ([#80](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues/80)).
  Picking one made the chat vanish from the sidebar at once. A chat that
  already starts with a hidden tag (shown with `Alt+H`) still offers
  **Remove tag**, and picking another tag replaces it. **New tag…** with a
  Hide rule's exact text still applies that rule.
- **The chat's new name shows right after a quick tag rename**
  ([#81](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues/81)).
  The sidebar kept the old name when ChatGPT split the title into several
  pieces or showed a scrolling copy of it; every copy is now updated, and
  a copy ChatGPT redraws with the old name is corrected again.
  Renaming the open chat, or undoing that rename, also updates its name in
  the browser tab title.
- Rules that don't match in the settings' rule tester are no longer faded,
  so they are easier to read.
- Rules can be reordered from the keyboard with **Move up** / **Move down**
  ([#77](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues/77)).
  The ↑/↓ buttons sit next to the ≡ drag handle; the first rule's ↑ and
  the last rule's ↓ are disabled, and focus stays on the moved rule.

## [1.3.0] — 2026-11-03

### Added
- **Quick tag**
  ([#73](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues/73)).
  Hover or focus a chat in the sidebar and click its tag button, or press
  `Alt+T` for the focused or open chat. The menu lists your `startsWith`
  rules in order with their colors and checks the current tag. Picking a
  tag renames the chat on ChatGPT: the current prefix tag and the spaces
  after it are replaced. **Remove tag** strips it, and **New tag…** adds a
  `startsWith` rule with the next unused palette color (1–40 characters;
  an existing tag is reused) and applies it. The menu works with arrow
  keys, Home/End, Enter, Escape and Tab.
- **Undo** after a quick tag rename: a toast shows “Tagged · Undo” for
  6 seconds (it stays while hovered or focused). Undo is refused if the
  chat was renamed again in the meantime. Errors appear in a toast and
  change nothing.
- Every quick tag rename and Undo first reads the chat's current title from
  ChatGPT and is refused if it changed. Renames of the same chat from
  different tabs in this browser run one at a time. If a rename's result is
  unknown (the request was cut off or its tab closed), that chat stays
  blocked until you reload ChatGPT to check the title or choose **Tag
  anyway**. ChatGPT has no conditional rename, so a rename made in ChatGPT
  itself or on another device at the same moment can still race.
- **Show quick tag button** option, on by default.
- **Settings button** in the sidebar filter bar
  ([#74](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues/74)).
  An icon-only gear sits after **Delete untagged…**, and the filter bar
  now shows whenever at least one rule exists. Pills still need two
  visible rules.
- **Floating settings window**
  ([#75](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues/75)).
  The gear and the toolbar icon open the settings in a 560×720 popup
  window, or focus the one already open. If the browser can't open a
  popup, the usual options page opens instead. The toolbar icon works
  even with no rules, and Firefox now has a toolbar button too.

### Changed
- **Settings are not silently overwritten in this browser**
  ([#76](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues/76)).
  `background.js` is now the only script that writes settings, one write
  at a time. A save from the options page is applied only if the stored
  settings haven't changed since that page loaded them (compare-and-set).
  An options page with no unsaved edits picks up changes made elsewhere;
  one with unsaved edits keeps its draft and shows “Settings changed in
  another window” with **Reload**. A save that fails to reach the
  extension shows “Not saved — retrying” and is sent again; a save the
  browser refuses (for example over the sync size limit) shows the error and
  lets your next edit save. A change synced from another device at the same
  moment can still win.
- Rule cards stack in windows 640 px wide or narrower, so the settings fit
  the floating window without scrolling sideways.
- Long titles in the rule tester wrap instead of overflowing.

## [1.2.0] — 2026-10-27

### Added
- **Choose which untagged chats to delete**
  ([#70](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues/70)).
  The **Delete untagged…** preview now has a checkbox for every chat,
  **Select all** / **Select none** buttons and an “N of M selected” count.
  Every chat starts checked, so the old flow still works. Only checked chats
  are deleted, the button reads “Delete N chats”, and it stays disabled
  while nothing is checked, even after you type `delete`. The selection is
  frozen once you confirm. The confirm-time re-check still skips chats that
  were tagged, pinned, starred, archived or deleted since the preview, and
  unchecked chats are never sent a delete request.

## [1.1.3] — 2026-10-17

### Changed
- Softer selected-chat highlight
  ([#61](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues/61)).
  The open tagged chat gets a gentler tag-colored fill, a thin translucent
  tag-colored outline and a 6 px stripe, in place of the bright fill and
  full-color outline from 1.1.2.
- The open untagged chat gets a neutral default highlight with a **hollow**
  stripe, so it's clearly selected and clearly untagged.
- CI uses `github/codeql-action` v4.38.3, `actions/setup-node` v7.1.0,
  `actions/upload-artifact` v7.0.2 and `actions/download-artifact` v8.0.2,
  still pinned to commit SHAs. Test dependency: Playwright 1.63.0.
- The Playwright suite runs headless by default, so local runs don't open
  a window or take focus. Set `HEADED=1` to watch the browser.

## [1.1.2] — 2026-09-27

### Added
- **Delete untagged chats** (off by default,
  [#46](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues/46)).
  Turn on “Show ‘Delete untagged chats’ button” in Options to get a
  **Delete untagged…** button in the sidebar filter bar. It lists every
  chat in your history whose title matches no rule, keeps pinned, starred,
  archived and tagged chats, and deletes the rest one at a time only after
  you type `delete`. The list is checked again right before deleting, so
  chats tagged, pinned, starred, archived or deleted since the preview are
  skipped. It sends the same request as ChatGPT's own Delete,
  stops at the first error, and can be stopped between chats.

### Changed
- Make the selected chat more distinct with a stronger tag-colored fill,
  an inset outline and a wider stripe. Untagged selected chats use a
  neutral outline and are not dimmed
  ([#51](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues/51)).

### Fixed
- Deleting the last rule now saves an empty configuration, preserves it
  across startup and import/export, and keeps General settings editable
  ([#49](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues/49)).
- Importing rules immediately refreshes an existing Rule Tester result
  ([#50](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues/50)).
- Restore compatibility with ChatGPT's current app-shell layout
  ([#48](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues/48)):
  sidebar highlighting, filtering, hiding and the active-chat overlay
  recover with the new sidebar rows and composer, while legacy hooks
  remain supported. Pinned rows hide as complete items, including menus
  and spacing. The overlay scrolls to the bottom of reversed timelines.
- Long-chat lazy rendering and pruning now recognize grouped turn
  containers: a whole user/assistant exchange on the current layout,
  rather than individual messages on older layouts. The lazy threshold
  remains 20 containers, with the newest 4 always rendered normally.
- Removing rules clears stale sidebar styling and filters instead of
  leaving chats hidden. Current-layout fixtures cover compatibility
  regressions; live checks used a short thread only, not a long-thread
  performance test. Deletion is tested with mocked routes only; no real
  account chats were modified.
- Options page: a General option whose description wraps onto a second
  line now keeps its checkbox beside the first line instead of centered
  between the lines.

## [1.1.1] — 2026-09-24

Maintenance release. No changes to the extension's behavior.

### Changed
- CI uses `actions/setup-node` v7.0.0 and `actions/setup-python` v7.0.0,
  still pinned to commit SHAs.
- Test dependencies: Playwright 1.62.0 and pytest 9.1.1.

## [1.1.0] — 2026-09-24

Compatibility and performance release for the current ChatGPT layout.

### Added
- **Speed up long chats** (on by default). In chats with 20 or more
  messages, off-screen older messages use `content-visibility: auto`
  with their measured height as the placeholder, so the browser skips
  their style/layout work and the scrollbar doesn't jump. The newest 4
  always render normally. Nothing is removed, so scrolling and Find keep
  working. On a ~200-message live thread: style recalculation across 4
  resizes went from 2,059 ms to 449 ms, and the slowest scroll frame
  from 120 ms to 27 ms.
- `TestContentScript` Playwright tests that run the packaged
  `content.js` against synthetic ChatGPT pages.
- `CLAUDE.md` agent guidance.

### Fixed
- Active-chat overlay did not appear: the composer anchor is now found
  via `form[data-type="unified-composer"]` (legacy
  `div.bg-token-bg-primary` still supported).
- Overlay now reappears when the composer is re-mounted instead of
  staying hidden.
- Overlay chevron scrolled nothing and turn pruning removed nothing:
  conversation turns are now `<section>` elements, so turns are matched
  by `data-testid` and the scroller search walks past `<main>`.
- ChatGPT's native scroll-to-bottom button is only hidden while the
  overlay is actually shown, so it is no longer lost on untagged chats.
  The current unlabelled button (inside a `data-scroll-from-end`
  wrapper) is now recognised too, so it no longer shows through the
  overlay.
- `data-active="false"` is no longer treated as the selected chat.
- The overlay chevron finishes at the real bottom even if its smooth
  scroll stops short (for example when a reply grows while scrolling);
  it stops helping as soon as you scroll or type. Pressing the overlay
  no longer steals focus from the composer.
- `Alt+H` now actually reveals rule-hidden chats (it was overridden by
  the extension's own CSS), and works with macOS Option key layouts.
- Renaming a chat in place (text-only change) now re-applies styling.
- On first install, chats added after the settings load are styled and
  the filter bar appears without a reload (the sidebar observer now
  attaches when settings arrive after the page).
- Filter pills work from the keyboard: Enter or Space toggles the
  focused pill, focus stays on it, and pills expose `role="button"` and
  `aria-pressed`.
- Settings migration no longer stores the color name `Green` for a rule
  without a color; it stores `#b8bb26`.

### Changed
- CI hardened: every action is pinned to a commit SHA, every job and
  step has a timeout, the Playwright cache is only saved from `main`,
  and a single `CI status` check aggregates build, Chrome tests, Firefox
  lint, and the wiki/release-tooling checks.
- Releases now require the tagged commit to be on `main` with a green
  `Tests` run, validate the tag against both manifests and the CHANGELOG
  (`scripts/release-check.py`), attach SHA-256 checksums, use the
  CHANGELOG section as release notes, and mark `-suffix` tags as
  prereleases. Only the publish job can write.
- The wiki now lives in `wiki/` (English + Simplified Chinese) and is
  published to the GitHub wiki from `main`.
- Privacy Policy now says settings use browser sync storage, and
  explains the long-chat options.
- README redesigned with new light/dark screenshots (demo titles only)
  and measured long-chat numbers; the privacy text now says settings
  use browser sync storage.
- Settings hints: "Max chat turns" says messages are removed from the
  page only until reload; "Hide right navigation bar" notes the current
  ChatGPT layout has no minimap, so it has no effect there.
- Development docs now say to build and load `dist/chrome/` or
  `dist/firefox/manifest.json`; `src/` has no `manifest.json`.
- Removed copied overlay assertions from `tests/unit_test.html` in
  favour of the real content-script tests.

## [1.0.0] — 2026-05-04

First stable release. The extension is now considered feature-complete
for v1: tag-based highlighting, sidebar filter, hide / dim / overlay
controls, multi-select filter persistence, and a hardened CI/release
pipeline.

### Added
- Continuous Integration pipeline (`.github/workflows/test.yml`) that
  builds the Chrome and Firefox bundles, runs the Playwright suite under
  Xvfb, and lints the Firefox `.xpi` with `web-ext`.
- Tag-driven release pipeline (`.github/workflows/release.yml`) that
  reuses the test workflow and publishes a GitHub Release with both the
  `.zip` and `.xpi` attached.
- Weekly CodeQL static-analysis scan (`.github/workflows/codeql.yml`).
- Dependabot configuration for GitHub Actions and pip dependencies.
- Issue templates (bug report, feature request) and a pull-request
  template.
- `CONTRIBUTING.md` and `SECURITY.md`.
- Pinned test dependencies in `tests/requirements.txt`.
- Persisted multi-select filter selection: pills clicked above the
  ChatGPT sidebar now survive page refresh and live-sync across tabs.
  Stored under a new `tagHighlighterUiStateV1` key in `storage.local`.
  Stale tags (deleted from rules) are pruned silently on load.

### Changed
- Hardened the Playwright fixture in `tests/test_extension.py` to derive
  the extension ID from the loaded MV3 service worker rather than
  scraping the `chrome://extensions` shadow DOM. The CI environment
  uses a throwaway profile under `/tmp` while local development keeps
  the persistent `tests/.test-profile/`.
- Editing rules in the Options page no longer wipes the active filter
  selection; instead, the selection is pruned to the new visible-rule
  set and persisted.
- `LICENSE` replaced with the canonical SPDX `MIT License` header so
  GitHub now reports the repository as MIT.

## [0.1.3] — 2026-04-19

### Added
- Auto-save in the Options page; rule changes persist without an
  explicit Save click.
- Multi-select filter bar above the ChatGPT sidebar — click pills to
  show only chats matching one or more tags.
- Per-rule overlay toggle so rules can highlight without the floating
  banner.
- Rule numbers and inline rule tester in the Options page.

### Changed
- Centralised every rule mutation through `onRulesChanged()` so row
  numbers, the debug tester, and auto-save always stay in sync.
- Layout polish in the Options page; `Add Tag` moved below the table.

## [0.1.2] — earlier

### Added
- Includes-style demo rules for friendlier onboarding.
- Multi-select tag filter bar pills (initial drop).

## [0.1.1]

### Fixed
- Rules with `hide: true` no longer appear as filter pills.

## [0.1.0]

### Added
- Keyboard focus on filter pills via `Alt+F`.

### Fixed
- Sidebar/nav hide selectors updated for the refreshed ChatGPT layout.

## [0.0.3]

### Added
- Dim Untagged, Badge Counter, and Keyboard Shortcut affordances.
- Sidebar tag filter bar with pill toggles.
- Per-rule overlay toggle, theme-aware overlay, Import/Export settings,
  drag-to-reorder rules.
- Live config reload and the option to hide the right nav bar.
- Initial pytest + Playwright suite.

## [0.0.2] — early release

Initial public release with tag-based highlighting in the ChatGPT
sidebar.

[Unreleased]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v1.1.3...v1.2.0
[1.1.3]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v1.1.2...v1.1.3
[1.1.2]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.1.3...v1.0.0
[0.1.3]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.0.3...v0.1.0
[0.0.3]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/releases/tag/v0.0.2
