# ChatGPT Tag Highlighter

Yet, just another lightweight browser extension that highlights ChatGPT sidebar conversations based on **title tags** like **[TODO]** and **[BUG]**. 
It adds a **colored left stripe** + subtle background so tagged chats are easy to scan and jump to.

![LOGO](./src/icon.png)

## Installation
### For Chrome: visit [ChatGPT Tag Highlighter](https://chromewebstore.google.com/detail/chatgpt-tag-highlighter/lplghggkggkbkkakjabafjenjlekogbm?authuser=0&hl=en)
### For Firefox: visit [ChatGPT Tag Highlighter](https://addons.mozilla.org/en-US/firefox/addon/chatgpt-tag-highlighter/)

---

## Why this exists

When you use ChatGPT for many ongoing tasks, the sidebar quickly becomes noisy. ChatGPT Tag Highlighter helps you:
- spot important threads instantly (**[BUG]**, **[TODO]**, etc.)
- keep debugging / notes organized without changing your workflow
- stay fast: minimal DOM work, incremental updates, low overhead

---

## Features

- **Tag-based highlighting** in the ChatGPT sidebar (e.g. `[TODO]`, `[BUG]`)
- **Configurable rules** in a Settings page:
  - add/remove tags
  - choose match type: `startsWith` (recommended) or `includes`
  - choose color from a preset palette or use a custom `#RRGGBB`
- **Selected vs. unselected styles**:
  - selected chat gets a stronger background + thicker stripe
- **Performance-first implementation**:
  - rules are compiled once
  - only processes sidebar chat items (not the whole page)
  - batches DOM updates and handles dynamic loading
- **Hide right navigation bar** for faster loading on long conversations
- **Chat turn pruning** — limit visible turns to reduce DOM overhead

---

## Screenshots

### Sidebar preview
![Sidebar Preview](./img/1.png)

### Settings page
![Settings](./img/2.png)

---

## Installation

### Chrome (Developer Mode)
1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select the project folder (the folder that contains `src/`)

### Firefox (Temporary Add-on for development)
1. Open `about:debugging#/runtime/this-firefox`
2. Click **Load Temporary Add-on**
3. Select the extension build output (or the Firefox package if you have one)

---

## Usage

### 1) Add tags to your ChatGPT chat titles
Name your conversations with a prefix tag, for example:
- `[TODO] Fix the build pipeline`
- `[BUG] Cosmos auth token issue`

### 2) Configure highlighting rules
Open extension **Options / Settings**, then configure:
- **Tag**: the text to match (recommended format: `[TAG]`)
- **Match**:
  - `startsWith` (fastest, recommended)
  - `includes` (more flexible, slightly slower)
- **Color**:
  - choose from preset palette
  - or enter a custom hex like `#fabd2f`

---

## Default rules

Out of the box, ChatGPT Tag Highlighter seeds these rules:
- **[TODO]** → Bright Yellow
- **[BUG]** → Bright Red

You can modify or remove them anytime in Settings.

---

## Permissions

- `storage`: saves your tag/color rules locally in the browser.

Host access:
- `https://chatgpt.com/*`
- `https://chat.openai.com/*`

---

## Privacy

- No analytics.
- No tracking.
- No data is sent to any server.
- Your configuration is stored locally using the browser’s extension storage.
- The extension reads **sidebar conversation titles** only to apply your selected styles.

---

## Troubleshooting

### Nothing is highlighted
- Make sure your chat titles actually contain the tag (e.g. `[TODO] ...`)
- Open Settings and verify rules exist
- Settings now apply live — no page reload needed

### Options page crashes
- Don’t open `options.html` via `file://...`
- Open it via the extension’s **Options / Preferences** page so storage APIs are available.

---

## Development & Testing Guide

This section helps contributors (human or AI agent) understand how to make and test code changes.

### Architecture overview

All runtime code lives in `src/`. Chrome and Firefox share the same JS/HTML/CSS but use separate manifests:
- `src/manifest.chrome.json` — Chrome (Manifest V3, `service_worker`)
- `src/manifest.firefox.json` — Firefox (Manifest V3, `scripts` array + gecko ID)

Key files:
| File | Role |
|------|------|
| `content.js` | Content script injected into `chatgpt.com`. Scans sidebar, applies highlights, hides chats, prunes turns, manages overlay. |
| `background.js` | Service worker. Seeds default config on install, migrates schema. |
| `options.js` + `options.html` | Settings page. Renders tag rules, persists config. |

### Data flow

All scripts share the storage key `tagHighlighterConfigV1`:
```json
{
  "rules": [{ "tag": "[TODO]", "match": "startsWith", "color": "#fabd2f", "hide": false }],
  "maxChatTurns": 0,
  "hideNavBar": true
}
```
- `background.js` seeds defaults and migrates on install
- `options.js` reads, edits, and persists config
- `content.js` reads config at load **and** listens to `storage.onChanged` for live updates

### Making code changes

1. **Edit files in `src/`** — this is the source of truth
2. **Load `src/` as an unpacked extension** in Chrome (`chrome://extensions` → Load unpacked) or Firefox (`about:debugging`)
3. **After editing, reload the extension** from `chrome://extensions` (click ↻) then refresh the ChatGPT tab
4. **Copy to `dist/`** when ready — `publish.sh` does this automatically, or copy manually:
   ```sh
   for f in content.js background.js options.js options.html options.css; do
     cp src/$f dist/chrome/$f && cp src/$f dist/firefox/$f
   done
   ```

### Adding new config fields

When adding a new config field (e.g. `hideNavBar`):
1. **`background.js`**: Add default value, add migration check in `seedOrMigrate()`
2. **`options.html`**: Add UI element (input/checkbox)
3. **`options.js`**: Add to `els`, `DEFAULT_CFG()`, `render()`, `collectConfig()`, and `init()` migration
4. **`content.js`**: Handle in `compileConfig()`, apply in the appropriate section, and ensure the `storage.onChanged` handler responds to it

### Testing with Playwright

Since this is a browser extension with no build step, testing is done via Playwright E2E automation:

```sh
# Setup (one-time)
python3 -m venv /tmp/pw-env
source /tmp/pw-env/bin/activate
pip install playwright
playwright install chromium
```

```python
# Launch Chrome with the extension loaded
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
ext_path = '/path/to/chatgpt-tag-highligher/dist/chrome'
profile_dir = '/tmp/pw-test-profile'

context = pw.chromium.launch_persistent_context(
    profile_dir,
    headless=False,
    args=[
        f'--disable-extensions-except={ext_path}',
        f'--load-extension={ext_path}',
        '--disable-blink-features=AutomationControlled',
    ],
    ignore_default_args=['--enable-automation'],
)

page = context.pages[0]
page.goto('https://chatgpt.com')
# ... interact and assert
```

**Key testing patterns:**

1. **Set config via storage** (from extension page context):
   ```js
   chrome.storage.sync.set({tagHighlighterConfigV1: config}, callback)
   ```

2. **Verify highlights** — check for `data-cth="1"` on sidebar anchors:
   ```js
   document.querySelectorAll('#history a[data-cth]').length
   ```

3. **Verify hide** — check `data-cth-hidden="1"`:
   ```js
   document.querySelectorAll('#history a[data-cth-hidden]').length
   ```

4. **Verify turn pruning** — count article elements:
   ```js
   document.querySelectorAll('article[data-testid^="conversation-turn-"]').length
   ```

5. **Verify nav bar hidden** — check CSS class on `<html>`:
   ```js
   document.documentElement.classList.contains('cth-hide-navbar')
   ```

6. **Live config reload** — change config via storage, wait 1–2s, verify DOM updated without `page.reload()`.

### Future: Automated test suite

| Test | Action | Assertion |
|------|--------|-----------|
| Sidebar highlights | Set rules, navigate to ChatGPT | `data-cth="1"` on matching anchors |
| Hide tags | Set `hide: true` for a tag | Matching anchors get `data-cth-hidden="1"` |
| Live config reload | Change config via `storage.onChanged` | DOM updates without page reload |
| Turn pruning | Set `maxChatTurns: 10` on a 100+ turn chat | `article` count ≤ 10 |
| Nav bar hiding | Set `hideNavBar: true` | `html.cth-hide-navbar` class present |
| Options page | Load options, modify rules, save | Config in storage matches UI state |
| Migration | Start with old config (missing fields) | `background.js` adds missing fields |

These tests can be scripted with Playwright + `pytest` or `@playwright/test`. Since the project has no npm/build tooling, a standalone Python script in `tests/` is the lightest approach.

## License
See [License](./LICENSE)
