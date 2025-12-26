# Privacy Policy — ChatGPT Tag Highlighter

**Last updated:** 2025-12-26

ChatGPT Tag Highlighter (“the Extension”) highlights ChatGPT sidebar conversations based on tags in the conversation title (e.g., **[TODO]**, **[BUG]**). This policy explains what the Extension accesses and how it handles data.

---

## 1) What the Extension accesses on the website

To provide highlighting, the Extension runs on supported ChatGPT domains (e.g., `chatgpt.com` and optionally `chat.openai.com`) and **reads limited on-page content**:

- **Website content accessed:** the **visible conversation titles** shown in the **sidebar chat list** (the text you see in the left navigation).
- **Purpose:** to check whether a title matches your configured tags and apply styling (colored left stripe and background).

**The Extension does not read or process:**
- the message content inside a chat
- files you upload
- your prompts, responses, or attachments
- account profile details beyond what is visible in the sidebar title text

---

## 2) User activity

The Extension may observe **UI events on the page** (such as when the sidebar list updates or when you navigate between chats) only to keep highlighting accurate.

- **User activity observed:** navigation/selection state in the sidebar and DOM updates (e.g., newly loaded chat titles).
- **Purpose:** to update highlights when the sidebar content changes.

**The Extension does not:**
- record keystrokes
- track clicks outside the sidebar list
- build a browsing history
- log your activity or interactions for analytics

---

## 3) Data the Extension stores

The Extension stores only **non-sensitive settings** locally in your browser using the browser’s extension storage API, such as:
- tag rules (e.g., `[TODO]`, `[BUG]`)
- match type (`startsWith` / `includes`)
- color choices (preset names or `#RRGGBB`)

This configuration is used only to apply your chosen highlighting.

---

## 4) Data collection, transmission, and sharing

- **No external transmission:** The Extension does **not** send any website content or user activity data to any server.
- **No third-party sharing:** The Extension does **not** sell, share, or transfer data to third parties.
- **No analytics/telemetry:** The Extension does **not** include analytics, advertising, or telemetry services.

---

## 5) Permissions explanation

- **Storage permission:** required to save and load your tag/color rules and settings.
- **Host permissions (ChatGPT domains):** required to run on ChatGPT pages so the Extension can read sidebar titles and apply highlighting.

---

## 6) Data retention

- Your settings remain in your browser until you change them or remove the Extension.
- The Extension does not retain copies of website content or user activity logs.

---

## 7) Changes to this policy

If the Extension changes in a way that affects privacy, this policy will be updated and the “Last updated” date will change.

---

## 8) Contact

If you have questions about this policy, contact:

- **Email:** D0n9X1n@outlook.com
- **Project page:** https://github.com/D0n9X1n/chatgpt-tag-highlighter
