# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

### Fixed
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

[Unreleased]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.1.3...v1.0.0
[0.1.3]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.0.3...v0.1.0
[0.0.3]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/releases/tag/v0.0.2
