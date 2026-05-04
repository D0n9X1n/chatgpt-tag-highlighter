# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.1.3...v1.0.0
[0.1.3]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.0.3...v0.1.0
[0.0.3]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/D0n9X1n/chatgpt-tag-highlighter/releases/tag/v0.0.2
