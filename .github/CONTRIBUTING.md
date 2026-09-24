# Contributing to ChatGPT Tag Highlighter

Thanks for your interest in contributing! This is a small browser
extension that highlights ChatGPT sidebar conversations by title tags.
The codebase intentionally has **no build tools, no bundler, and no
runtime dependencies** — pure vanilla JS with two manifest templates.

## Getting Started

### Development install

`src/` contains only manifest templates, so build the unpacked bundles first:

```sh
./publish.sh --version 0.0.99
```

**Chrome / Edge / Brave / Arc:**

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked** and select `dist/chrome/`.

**Firefox:**

1. Open `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on…** and select `dist/firefox/manifest.json`.

After edits, rebuild, reload the extension, and refresh the ChatGPT tab.

## Project Layout

```
src/                    # Extension source (build to dist/ before loading)
  content.js            # Sidebar scanning + highlighting
  background.js         # Service worker / background script
  options.{html,css,js} # Settings page
  manifest.chrome.json  # MV3 manifest (Chrome)
  manifest.firefox.json # MV3 manifest with browser_specific_settings (Firefox)
publish.sh              # Builds dist/{chrome,firefox} + .zip / .xpi archives
tests/                  # pytest + Playwright suite (see "Running Tests")
.github/workflows/      # CI: tests, codeql, release
docs/specs/             # Design specs, one per feature
feature-crew/           # Submodule: agent-team workflow used by maintainers
```

## Making Changes

1. **Branch off `main`.** Use a short topic prefix:
   - `feat/<topic>` for new features
   - `fix/<topic>` for bug fixes
   - `ci/<topic>`, `docs/<topic>`, `chore/<topic>` for everything else
2. **Stick to vanilla JS.** No npm packages, no transpilation.
3. **Match existing patterns.** IIFE wrappers, `chrome.storage.sync` with
   `local` fallback, CSS custom properties for highlight colors, and
   batched DOM work via `requestAnimationFrame`.
4. **Keep `LEGACY` and `PALETTE` in sync** between `content.js` and
   `options.js` if you change the color palette.
5. **Add tests** under `tests/` for any non-trivial behaviour.

## Running Tests

The CI suite uses Playwright + pytest. There's no Node.js dependency.

### One-time setup

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r tests/requirements.txt
playwright install chromium
```

### Build the extension (tests need `dist/chrome/`)

```sh
./publish.sh --version 0.0.99
```

### Run the suite

```sh
source .venv/bin/activate
pytest tests/test_extension.py -v
```

### Live tests (require ChatGPT login)

There is also an in-browser unit test page at `tests/unit_test.html` that
the suite loads automatically.

If you want to run live ChatGPT tests interactively, log in **once** in
the persistent profile at `tests/.test-profile/` and reuse it across
runs. **Do not delete that directory** between runs — the cookies expire
quickly.

## Building Release Artifacts

```sh
./publish.sh --version X.Y.Z
```

Produces:

- `dist/chrome/`     — unpacked Chrome bundle (Load Unpacked friendly)
- `dist/firefox/`    — unpacked Firefox bundle
- `dist/chatgpt-tag-highlighter-chrome-X.Y.Z.zip`
- `dist/chatgpt-tag-highlighter-firefox-X.Y.Z.xpi`

## Releasing (Maintainers Only)

Releases are cut from a commit that is already on `main` and has a green
`Tests` run. The release workflow checks this; it does not re-run tests.

1. In a PR, bump the `version` field in **both** `src/manifest.chrome.json`
   and `src/manifest.firefox.json`, and add a `## [X.Y.Z]` section to
   `CHANGELOG.md`. `python3 scripts/release-check.py` must pass (CI runs it).
2. Merge to `main` and wait for `Tests` to go green on that commit.
3. Tag that commit and push:
   ```sh
   git tag vX.Y.Z          # vX.Y.Z-rc.1 publishes a prerelease
   git push origin vX.Y.Z
   ```
4. `.github/workflows/release.yml` validates the tag, builds the `.zip`
   and `.xpi` with SHA-256 checksums, and publishes a GitHub Release whose
   notes are the matching CHANGELOG section.
5. **Manually** upload the `.zip` to the Chrome Web Store dashboard and
   the `.xpi` to AMO. Store API publishing is intentionally not
   automated yet.

## Wiki

The GitHub wiki is generated from the tracked `wiki/` folder; don't edit
it on github.com. Each page has an English file and a `-zh-CN` file with
the same headings and facts. Check with `python3 scripts/check-wiki.py wiki`;
`.github/workflows/publish-wiki.yml` publishes it on every push to `main`.

## Pull Requests

- Keep PRs focused — one feature or fix per PR.
- Make sure `pytest tests/test_extension.py -v` passes locally before
  pushing. CI will re-run it on PR.
- The PR template will prompt you for the basics (what, why, how
  tested). Fill it in honestly.

## Code of Conduct

Be kind. Assume good intent. Focus on the code.

## Getting Help

- Open a [Discussion](https://github.com/D0n9X1n/chatgpt-tag-highlighter/discussions)
  for design questions.
- Open an [Issue](https://github.com/D0n9X1n/chatgpt-tag-highlighter/issues)
  for bugs and feature requests using the templates.
