# Testing

[简体中文](Testing-zh-CN)

## Setup

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r tests/requirements.txt   # pinned Playwright + pytest
playwright install chromium
```

## Commands

```sh
./publish.sh --version 0.0.99                                   # tests run against dist/chrome
CI=true pytest tests/test_extension.py -v                       # full suite
CI=true pytest tests/test_extension.py::TestOptionsPage::test_save_persists_config -v
CI=true pytest tests/test_extension.py -k TestContentScript -v  # one class
for f in src/*.js; do node --check "$f"; done                   # syntax check
npx --yes web-ext@8.3.0 lint --source-dir dist/firefox --warnings-as-errors=false --self-hosted
python3 scripts/check-wiki.py wiki && bash scripts/test-wiki-publish.sh
```

Tests launch **headed** Chromium, because extensions don't load reliably headless. CI wraps pytest in `xvfb-run -a --server-args="-screen 0 1280x900x24"`.

## What the tests cover

- `TestContentScript` loads the **packaged** `content.js` and serves synthetic ChatGPT pages at `https://chatgpt.com/` with `page.route`. The fixtures mirror the live page hooks in [Architecture](Architecture) and contain no real account data.
- Other classes cover the options page, settings migration, and import/export.
- `tests/unit_test.html` tests copies of pure helpers only, not the real content script.
- Firefox is only linted in CI; its runtime behavior is not tested.

## Live-testing rules

- Always pass `CI=true` for automated runs. Without it the suite uses `tests/.test-profile/`, which holds a ChatGPT login. Never delete it, copy its cookies, or run two browsers on it at once.
- ChatGPT cookies are short-lived: use one persistent browser context for the whole live session, with `ignore_default_args=['--enable-automation', '--disable-extensions']`.
- Stay read-only on chatgpt.com: never send, create, rename, or delete chats.
- chatgpt.com's CSP forbids `unsafe-eval`. Pass a **function**, not a string, to Playwright's `wait_for_function`; a string predicate throws `EvalError` right away, which a `try/except` silently turns into a false "timeout".
- Passing fixtures is not proof of live compatibility; check the real extension on chatgpt.com too.
