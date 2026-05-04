# Security Policy

## Supported Versions

We support the latest published version of the extension on each store:

| Channel | Supported |
| --- | --- |
| Chrome Web Store — latest | ✅ |
| Firefox Add-ons (AMO) — latest | ✅ |
| Older versions | ❌ |

## Reporting a Vulnerability

**Please do not file a public GitHub issue for security reports.**

If you believe you have found a security vulnerability in
`chatgpt-tag-highlighter`, report it privately via GitHub's
[Security Advisories](https://github.com/D0n9X1n/chatgpt-tag-highlighter/security/advisories/new)
form. This routes the report to the maintainers without exposing it
publicly while we triage.

When reporting, please include:

1. A clear description of the issue and its impact.
2. Steps to reproduce, ideally with a minimal example or video.
3. Affected version(s) and browser(s).
4. Any proof-of-concept code or saved configuration.

We aim to:

- Acknowledge receipt within **3 working days**.
- Provide an initial assessment within **7 working days**.
- Ship a fix or mitigation as soon as practical, coordinated with you.

## Scope

In scope:

- The extension code under `src/`.
- The build pipeline under `publish.sh` and `.github/workflows/`.
- The published artifacts on the Chrome Web Store and AMO.

Out of scope:

- Issues in ChatGPT itself or unrelated browser features.
- Social-engineering or physical attacks against extension users.
- Vulnerabilities that require an attacker to already control the user's
  browser profile or operating system account.

## Disclosure

We follow coordinated disclosure: once a fix is shipped to both stores,
we publish the advisory and credit the reporter (unless they request
anonymity).
