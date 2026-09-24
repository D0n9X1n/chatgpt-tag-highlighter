# Privacy

[简体中文](Privacy-zh-CN)

## What it reads

- **Sidebar chat titles**, to match your tag rules.
- **ChatGPT's theme** (light or dark), to match the banner's look.
- **Message sizes** on the page, for "Speed up long chats".
- If you set **Max chat turns**, the extension removes older message elements from the page. It never reads message text, prompts, replies, or files.

## What it stores

- **Tag rules and options** in the browser's extension storage, using `storage.sync` (with `storage.local` as a fallback).
- **Which filter pills are selected**, in `storage.local`.
- If browser sync is on, your browser may copy these settings to your other signed-in devices through its own sync service. The extension itself never sends them anywhere.

## What it never does

- No analytics, tracking, or telemetry.
- No servers of its own, and no third-party sharing.
- See the full [Privacy Policy](https://github.com/D0n9X1n/chatgpt-tag-highlighter/blob/main/Privacy%20Policy.md).

## Permissions

- `storage`: saves your rules and options.
- Site access to `https://chatgpt.com/*` and `https://chat.openai.com/*` only, to style those pages.
