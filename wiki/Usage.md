# Usage

[简体中文](Usage-zh-CN)

## Install

- **Chrome, Edge, Brave, Arc:** install from the [Chrome Web Store](https://chromewebstore.google.com/detail/chatgpt-tag-highlighter/lplghggkggkbkkakjabafjenjlekogbm).
- **Firefox:** install from [Firefox Add-ons](https://addons.mozilla.org/firefox/addon/chatgpt-tag-highlighter/).
- **Local build:** run `./publish.sh --version 0.0.99`, then load `dist/chrome/` with **Load unpacked** in `chrome://extensions`, or `dist/firefox/manifest.json` with **Load Temporary Add-on** in `about:debugging`. `src/` has no `manifest.json`, so it can't be loaded directly. See [Development and Release](Development-and-Release).

## Tag your chats

Rename a chat in ChatGPT so its title starts with a tag, for example `[TODO] Fix the build pipeline` or `[BUG] Login token expires early`. Four starter rules are set up on install: **[TODO]** (yellow), **[BUG]** (red), **code** (blue) and **help** (green). Change them in [Configuration](Configuration).

Tagged chats get a colored left stripe and background. The open chat gets a stronger background and a thicker stripe. Matching is case-sensitive, and `startsWith` rules need the tag at the very start of the title.

## Filter the sidebar

When at least two rules are not set to Hide, pills appear above the chat list. Click one or more tag pills to show only those chats (a chat shows if it matches any selected tag). **All** clears the selection. The selection survives a reload and is shared across ChatGPT tabs.

## Delete untagged chats

Off by default. Turn on **Show “Delete untagged chats” button** in [Configuration](Configuration), then click **Delete untagged…** at the end of the filter bar. The bar also appears for this button when there are too few rules for pills.

![Delete untagged chats dialog listing the chats that match no rule](https://raw.githubusercontent.com/D0n9X1n/chatgpt-tag-highlighter/main/img/delete-untagged-light.png)

1. The extension asks ChatGPT for your whole chat list, not just the chats loaded in the sidebar, and lists every chat whose title matches no rule. Nothing is deleted yet.
2. Pinned, starred and archived chats are kept, and so is every chat that matches a rule, including rule-hidden ones. Untitled chats count as untagged.
3. Type `delete` and confirm. The list is checked again first, and any chat you tagged, pinned, starred, archived or deleted since the preview is skipped. Chats are then deleted one at a time with the same request ChatGPT's own **Delete** sends, and disappear from the sidebar as they go. **Stop** halts after the current chat, and the first error stops the run.
4. **Reload page** refreshes ChatGPT's own list.

ChatGPT's sidebar can't restore deleted chats, so check the list before you confirm. The feature relies on ChatGPT's private web endpoints, which can change without notice. Chats inside Projects aren't covered.

## The tag banner

When the open chat matches a rule with **Overlay** on, a banner above the message box shows its tag color and title. Click it to jump to the latest message; the message box keeps focus. While the banner is shown, ChatGPT's own scroll-to-bottom button is hidden so there's only one. In untagged chats ChatGPT's button is left alone.

## Badge

The extension icon shows how many loaded sidebar chats are tagged and not hidden by a rule. Turn it off in [Configuration](Configuration).

## Keyboard shortcuts

| Keys | Action |
|---|---|
| `Alt+H` (`Option+H` on macOS) | Show or hide chats hidden by a Hide rule |
| `Alt+F` | Move focus to the filter bar |
| `Enter` or `Space` | Toggle the focused filter pill |
