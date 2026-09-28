# Configuration

[简体中文](Configuration-zh-CN)

Open the extension's **Options** page from the browser's extension menu. Don't open `options.html` as a `file://` path; the storage APIs aren't available there. Every change saves automatically.

![Settings page](https://raw.githubusercontent.com/D0n9X1n/chatgpt-tag-highlighter/main/img/settings.png)

## Tag rules

Rules are checked top to bottom and the **first match wins** for color, hiding, filtering and the banner. Drag ≡ to reorder.

| Field | Meaning |
|---|---|
| Tag | Text to look for. Case-sensitive. |
| Match | `startsWith`: the title begins with the tag (best for `[TAG]` prefixes). `includes`: the tag appears anywhere in the title. |
| Color | A preset or any `#RRGGBB`. Colors are always saved as hex. |
| Hide | Hide matching chats from the sidebar. `Alt+H` reveals them. |
| Overlay | Show the tag banner when a matching chat is open. |

Rule changes apply live to open ChatGPT tabs. Removing rules clears their stale highlighting and filter selection so chats do not stay hidden by a removed filter.

## General options

| Option | Default | What it does |
|---|---|---|
| Speed up long chats | On | In chats with 20 or more turn containers, off-screen turns skip rendering. The newest 4 always render; nothing is removed. See [Long Chats](Long-Chats). |
| Max chat turns to keep | 0 (off) | Keeps the selected number of complete turn containers, removing older ones from the page (not your account) until you reload or reopen the chat. |
| Hide right navigation bar | On | Hides the message minimap on older ChatGPT layouts. The current layout has no minimap, so it has no effect there. |
| Dim untagged conversations | Off | Fades chats that match no rule, except the selected chat. |
| Show badge counter | On | Shows the number of visible tagged chats on the extension icon. |
| Show “Delete untagged chats” button | Off | Adds a **Delete untagged…** button to the filter bar. See [Usage](Usage). |

Both long-chat options count **turn containers**: a whole user/assistant exchange on the current layout, or an individual message on older layouts. Pruning never splits a grouped exchange. The performance measurements in [Long Chats](Long-Chats) came from the older, individual-message layout; the Sep 28, 2026 compatibility checks used a short live thread and synthetic fixtures, not a long current-layout live thread.

## Rule tester

Type a chat title in **Rule Tester** to see which rule would match it and why the others don't.

## Import and export

**Export** copies all settings as JSON to the clipboard. **Import** takes pasted JSON; invalid JSON and settings with no rules are rejected.
