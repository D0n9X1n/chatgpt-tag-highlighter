# Long Chats

[简体中文](Long-Chats-zh-CN)

## Why long chats get slow

In a very long conversation the browser keeps styling and laying out every message, even ones far off-screen. Resizing the window, switching theme, or scrolling then costs time for the whole thread.

## How "Speed up long chats" works

With the option on (the default), chats with **20 or more turn containers** get this treatment. A container is a whole user/assistant exchange on the current layout, or an individual message on older layouts:

- Every container except the **newest 4** is marked with `content-visibility: auto`, so the browser skips its style, layout and paint work until it comes near the screen.
- Each marked container keeps its **measured height** as a placeholder (`contain-intrinsic-block-size`), so the scrollbar doesn't jump.
- Nothing is removed: scrolling, Find (`Ctrl/Cmd+F`) and text selection keep working.
- Turning the option off restores normal rendering immediately, without a reload.

## Measured results

Measured on live ChatGPT's older, individual-message layout in Chrome, in a conversation of about 200 messages, with the option off and then on:

| Work | Off | On |
|---|---:|---:|
| Style recalculation across 4 window resizes | 2,059 ms | 449 ms |
| Layout across the same resizes | 59 ms | 20 ms |
| 10 page-wide style changes (for example, theme switches) | 1,255 ms | 296 ms |
| Slowest frame while scrolling the whole thread | 120 ms | 27 ms |

These numbers come from one machine and will vary. The Sep 28, 2026 compatibility checks used a short live thread and synthetic fixtures, not a long current-layout live thread. Chats under 20 turn containers are left alone. The extension's own work stayed small: showing the banner added under 0.1 ms per frame in the same legacy-layout benchmark.

## Compared with Max chat turns

**Max chat turns** (0/off by default) keeps the selected number of complete turn containers and removes older ones from the page, not your account. On the current layout this keeps or removes whole exchanges, never half an exchange; older layouts count individual messages. Removed containers can't be scrolled to or found until you reload or reopen the chat. Use it only if you want that; "Speed up long chats" is the non-destructive option. See [Configuration](Configuration).
