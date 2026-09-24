# Development and Release

[简体中文](Development-and-Release-zh-CN)

## Build

```sh
./publish.sh --version 0.0.99
```

This writes `dist/chrome/` and `dist/firefox/` (each with a generated `manifest.json`) plus a `.zip` and an `.xpi`. `dist/` is generated and gitignored; `src/` is the only source. Load `dist/chrome/` or `dist/firefox/manifest.json`, and rebuild after each edit. `publish.sh --version` only writes the version into the built manifests.

## CI gates

Every pull request and every push to `main` must pass:

- JavaScript syntax check, and `scripts/release-check.py`: both manifests have the same version and `CHANGELOG.md` has a section for it.
- Chrome and Firefox bundle build.
- The Playwright suite against the Chrome bundle under Xvfb.
- `web-ext lint` on the Firefox bundle.
- The wiki checker and the wiki publisher self-test.
- `CI status`, one aggregate job that fails unless every job above succeeded. Require this check in branch protection.

Every action is pinned to a commit SHA with a version comment, and every job and step has a timeout.

See [Testing](Testing) for running these locally.

## Releases

1. Bump `version` in **both** `src/manifest.chrome.json` and `src/manifest.firefox.json`, and add a matching `## [X.Y.Z]` section to `CHANGELOG.md`.
2. Merge to `main` and wait for CI to pass.
3. Tag that commit `vX.Y.Z` and push the tag. A tag like `vX.Y.Z-rc.1` publishes a prerelease.

The release workflow checks that the tag matches both manifests and has a CHANGELOG section, and that the tagged commit is on `main` with a successful CI run. It then builds the `.zip` and `.xpi` with SHA-256 checksums and publishes a GitHub Release whose notes come from the CHANGELOG section. Uploading to the Chrome Web Store and Firefox Add-ons is manual. Chrome only accepts numeric versions (up to four dot-separated parts), so the manifests stay `X.Y.Z` and a `-suffix` on the tag only marks the GitHub Release as a prerelease.

## Wiki source and publication

- The tracked `wiki/` folder is the only source for this wiki. Edit pages there, not on GitHub.
- Every page has an English file and a `-zh-CN` file with the same facts and matching heading depths. Links use bare page names without `.md`, Home links every page, and flow diagrams use Mermaid.
- `scripts/check-wiki.py` enforces these rules in CI.
- On every push to `main`, the Publish wiki workflow runs `scripts/publish-wiki.sh` to mirror `wiki/*.md` into the GitHub wiki's `master` branch. Pages removed from `wiki/` are removed from the wiki. It needs only the built-in `GITHUB_TOKEN`, with write access in that one job.
