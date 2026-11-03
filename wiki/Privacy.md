# Privacy

[简体中文](Privacy-zh-CN)

## What it reads

- **Sidebar chat titles**, to match your tag rules.
- **ChatGPT's theme** (light or dark), to match the banner's look.
- **Message sizes** on the page, for "Speed up long chats".
- If you set **Max chat turns**, the extension removes older message elements from the page. It never reads message text, prompts, replies, or files.
- Only if you use **Delete untagged chats**: your chat list from ChatGPT (ids, titles, and whether each is pinned, starred or archived) and your session's access token. The token stays in memory for that run and is never stored. Delete requests go only to ChatGPT, and only for the chats you selected and confirmed.
- Only if you use **Quick tag**: the extension renames a chat on ChatGPT only when you pick a tag, remove one, or press **Undo**. It sends `PATCH /backend-api/conversation/{id}` with the new title (the same request ChatGPT's own Rename sends), authorized with your session's access token. Right before each rename (including **Undo**), it reads that chat's current title with `GET /backend-api/conversation/{id}` and renames only if the title is still the one it expects. Renames of the same chat from different tabs in this browser run one at a time. ChatGPT's API has no conditional write, so a rename made in ChatGPT itself or on another device at the same moment can still race with it; this check is best-effort. The token is fetched for these requests and never stored. **New tag…** also adds the tag as a rule in your settings.

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

Quick tag and the floating settings window need no new permissions.
