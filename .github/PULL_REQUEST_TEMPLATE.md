<!--
  Thanks for contributing! Please fill out the relevant sections below.
  Remove sections that don't apply.
-->

## Summary

<!-- One or two sentences: what does this PR change and why? -->

## Type of change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that changes existing behaviour)
- [ ] Refactor / cleanup (no behavioural change)
- [ ] Docs / CI / chore

## Related issues

<!-- e.g. Closes #123 -->

## How was this tested?

- [ ] `pytest tests/test_extension.py -v` passes locally
- [ ] Manually verified in Chrome via `chrome://extensions` → Load unpacked
- [ ] Manually verified in Firefox via `about:debugging` → Load Temporary Add-on
- [ ] No tests needed (docs / CI only)

## Checklist

- [ ] My branch is up to date with `main`
- [ ] I've matched the existing code style (vanilla JS, IIFE wrappers, no new deps)
- [ ] I've updated `LEGACY` / `PALETTE` in both `content.js` and `options.js` if I changed colors
- [ ] I've added or updated tests under `tests/` for non-trivial changes
- [ ] I've updated documentation (`ReadMe.md`, `ReadMe.CN.md`, `CHANGELOG.md`) if user-facing behaviour changed
