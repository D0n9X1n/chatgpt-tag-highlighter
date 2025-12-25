// content.js
// ChatGPT Sidebar Tag Highlighter (ultra perf, config-driven only)
//
// Behavior:
// - Reads rules from extension storage key "tagHighlighterConfigV1" (set by options page).
// - If no rules exist, early return (does nothing).
// - Supports palette names (Gruvbox-ish) OR custom hex "#RRGGBB" in stored rules.
// - Distinguishes selected vs non-selected chat item styles.
//
// Notes:
// - Comments are English by request.
// - Designed for maximum performance: pre-compiled rules, incremental DOM processing, minimal observers.

(() => {
  "use strict";

  /***********************
   * 1) Storage: config only
   ***********************/
  const STORAGE_KEY = "tagHighlighterConfigV1";

  const API =
    (typeof browser !== "undefined" && browser?.storage) ? browser :
    (typeof chrome !== "undefined" && chrome?.storage) ? chrome :
    null;

  if (!API) return;

  const storageArea =
    API.storage?.sync ? API.storage.sync :
    API.storage?.local ? API.storage.local :
    null;

  if (!storageArea) return;

  function storageGet(key) {
    try {
      const r = storageArea.get(key);
      if (r && typeof r.then === "function") return r; // Firefox Promise
    } catch {}
    return new Promise((resolve) => storageArea.get(key, resolve)); // Chrome callback
  }

  async function getRulesOrNull() {
    const data = await storageGet(STORAGE_KEY);
    const rules = data?.[STORAGE_KEY]?.rules;
    if (!Array.isArray(rules) || rules.length === 0) return null;
    return rules;
  }

  /***********************
   * 2) Palette + style constants
   ***********************/
  // Palette is needed because options page may store color as a palette name (e.g. "BrightYellow").
  // If you always store hex in options page, you can remove this palette and keep hex-only.
  const PALETTE = {
    Green:        "#98971a",
    BrightGreen:  "#b8bb26",
    Aqua:         "#689d6a",
    BrightAqua:   "#8ec07c",
    Blue:         "#458588",
    BrightBlue:   "#83a598",
    Yellow:       "#d79921",
    BrightYellow: "#fabd2f",
    Orange:       "#d65d0e",
    BrightOrange: "#fe8019",
    Red:          "#cc241d",
    BrightRed:    "#fb4934",
    Purple:       "#b16286",
    BrightPurple: "#d3869b",
    Gray:         "#928374",
  };

  const OP = {
    normal: 0.14,
    hover: 0.20,
    active: 0.28,
    activeHover: 0.34,
    outline: 0.25,
    outlineHover: 0.35,
  };

  const STYLE_ID = "tag-highlighter-style";
  const CLASS = "tag-highlight";
  const HISTORY_ID = "history";

  const css = `
    #${HISTORY_ID} a.${CLASS}{
      background: var(--tag-bg) !important;
      border-left: 4px solid var(--tag-color) !important;
      padding-left: 12px !important;
      border-radius: 10px !important;
      font-weight: 600 !important;
    }
    #${HISTORY_ID} a.${CLASS}:hover{
      background: var(--tag-bg-hover) !important;
    }
    #${HISTORY_ID} a.${CLASS}[data-active],
    #${HISTORY_ID} a.${CLASS}[aria-current="page"]{
      background: var(--tag-bg-active) !important;
      border-left-width: 6px !important;
      box-shadow: inset 0 0 0 1px rgba(var(--tag-rgb), ${OP.outline}) !important;
    }
    #${HISTORY_ID} a.${CLASS}[data-active]:hover,
    #${HISTORY_ID} a.${CLASS}[aria-current="page"]:hover{
      background: var(--tag-bg-active-hover) !important;
      box-shadow: inset 0 0 0 1px rgba(var(--tag-rgb), ${OP.outlineHover}) !important;
    }
  `;

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const s = document.createElement("style");
    s.id = STYLE_ID;
    s.textContent = css;
    document.head.appendChild(s);
  }

  /***********************
   * 3) Compiler (rules -> ultra-fast matchers)
   ***********************/
  function isHex(s) {
    return /^#[0-9a-fA-F]{6}$/.test(String(s || "").trim());
  }

  function normalizeColor(c) {
    const raw = String(c || "").trim();
    if (isHex(raw)) return raw;

    const key = Object.keys(PALETTE).find((k) => k.toLowerCase() === raw.toLowerCase());
    return key ? PALETTE[key] : null;
  }

  function hexToRgbStr(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `${r},${g},${b}`;
  }

  function compileRules(rules) {
    // Compiled rules are split into:
    // - prefix rules: startsWith (fast, usually "[TAG]")
    // - includes rules: includes (slower; evaluated last)
    const prefix = [];
    const incl = [];

    for (const r of rules) {
      const tag = String(r?.tag || "").trim();
      if (!tag) continue;

      const match = String(r?.match || "startsWith").toLowerCase() === "includes" ? "includes" : "startsWith";
      const hex = normalizeColor(r?.color);
      if (!hex) continue;

      const rgbStr = hexToRgbStr(hex);
      const compiled = {
        tag,
        match,
        colorHex: hex,
        rgbStr,
        bg:        `rgba(${rgbStr},${OP.normal})`,
        bgHover:   `rgba(${rgbStr},${OP.hover})`,
        bgActive:  `rgba(${rgbStr},${OP.active})`,
        bgActHov:  `rgba(${rgbStr},${OP.activeHover})`,
      };

      if (match === "includes") incl.push(compiled);
      else prefix.push(compiled);
    }

    return { prefix, incl };
  }

  /***********************
   * 4) DOM helpers (fast paths)
   ***********************/
  function isChatLink(a) {
    if (!a || a.nodeType !== 1 || a.tagName !== "A") return false;
    if (a.getAttribute("data-sidebar-item") !== "true") return false;
    const href = a.getAttribute("href") || "";
    return href.startsWith("/c/");
  }

  function readTitle(a) {
    // Prefer the visible span; fallback to full text.
    const t = a.querySelector('span[dir="auto"]')?.textContent;
    return (t ? t.trim() : (a.textContent || "").trim());
  }

  /***********************
   * 5) Engine (incremental + batched updates)
   ***********************/
  const engine = {
    compiled: null,
    historyRoot: null,
    historyMO: null,
    parentMO: null,

    // WeakMap for diffing per <a>
    last: new WeakMap(), // a -> { title, tag, colorHex }

    // Batch queue
    queue: new Set(),
    scheduled: false,

    running: false,
  };

  function pickRule(title) {
    const { prefix, incl } = engine.compiled;

    // Ultra fast skip for common prefix style tags:
    // Only run startsWith checks if title begins with '['.
    if (title.charCodeAt(0) === 91) { // '['
      for (const r of prefix) if (title.startsWith(r.tag)) return r;
    }

    // Includes rules last (slower).
    for (const r of incl) if (title.includes(r.tag)) return r;

    return null;
  }

  function setVars(a, r) {
    a.classList.add(CLASS);
    a.style.setProperty("--tag-color", r.colorHex);
    a.style.setProperty("--tag-rgb", r.rgbStr);
    a.style.setProperty("--tag-bg", r.bg);
    a.style.setProperty("--tag-bg-hover", r.bgHover);
    a.style.setProperty("--tag-bg-active", r.bgActive);
    a.style.setProperty("--tag-bg-active-hover", r.bgActHov);
  }

  function clearVars(a) {
    a.classList.remove(CLASS);
    a.style.removeProperty("--tag-color");
    a.style.removeProperty("--tag-rgb");
    a.style.removeProperty("--tag-bg");
    a.style.removeProperty("--tag-bg-hover");
    a.style.removeProperty("--tag-bg-active");
    a.style.removeProperty("--tag-bg-active-hover");
  }

  function enqueue(a) {
    engine.queue.add(a);
    if (engine.scheduled) return;
    engine.scheduled = true;
    requestAnimationFrame(flush);
  }

  function processOne(a) {
    const title = readTitle(a);
    const rule = pickRule(title);
    const prev = engine.last.get(a);

    if (!rule) {
      if (prev?.tag) clearVars(a);
      engine.last.set(a, { title, tag: null, colorHex: null });
      return;
    }

    // Skip if unchanged
    if (prev && prev.title === title && prev.tag === rule.tag && prev.colorHex === rule.colorHex) return;

    setVars(a, rule);
    engine.last.set(a, { title, tag: rule.tag, colorHex: rule.colorHex });
  }

  function flush() {
    engine.scheduled = false;
    const items = engine.queue;
    engine.queue = new Set();

    for (const a of items) processOne(a);
  }

  function scanExisting(root) {
    const links = root.querySelectorAll('a[data-sidebar-item="true"][href^="/c/"]');
    for (const a of links) enqueue(a);
  }

  function collectLinksFromNode(node) {
    if (node.nodeType !== 1) return;

    if (node.tagName === "A") {
      if (isChatLink(node) && node.closest(`#${HISTORY_ID}`) === engine.historyRoot) enqueue(node);
      return;
    }

    // Faster than querySelectorAll in many cases
    const as = node.getElementsByTagName?.("a");
    if (!as || as.length === 0) return;

    for (let i = 0; i < as.length; i++) {
      const a = as[i];
      if (isChatLink(a) && a.closest(`#${HISTORY_ID}`) === engine.historyRoot) enqueue(a);
    }
  }

  function observeHistory(root) {
    const mo = new MutationObserver((mutations) => {
      for (const m of mutations) {
        for (const n of m.addedNodes) collectLinksFromNode(n);
      }
    });

    mo.observe(root, { childList: true, subtree: true });
    return mo;
  }

  function attachHistory() {
    const root = document.getElementById(HISTORY_ID);
    if (!root || root === engine.historyRoot) return false;

    engine.historyMO?.disconnect();
    engine.parentMO?.disconnect();

    engine.historyRoot = root;
    scanExisting(root);
    engine.historyMO = observeHistory(root);

    // Tiny parent observer to detect replacement/removal of #history
    const parent = root.parentElement;
    if (parent) {
      engine.parentMO = new MutationObserver(() => {
        if (!document.contains(engine.historyRoot)) attachHistory();
      });
      engine.parentMO.observe(parent, { childList: true });
    }

    return true;
  }

  function stopEngineAndClear() {
    engine.historyMO?.disconnect();
    engine.parentMO?.disconnect();
    engine.historyMO = null;
    engine.parentMO = null;

    const root = engine.historyRoot;
    engine.historyRoot = null;
    engine.running = false;

    // Clear highlights (best effort)
    if (root) {
      const links = root.querySelectorAll('a[data-sidebar-item="true"][href^="/c/"]');
      for (const a of links) clearVars(a);
    }
  }

  function startEngine(compiled) {
    engine.compiled = compiled;
    engine.running = true;
    ensureStyle();

    // Attach now
    attachHistory();

    // Lightweight retry for SPA lazy-load
    let tries = 0;
    const timer = setInterval(() => {
      if (!engine.running) return clearInterval(timer);
      const ok = attachHistory();
      if (++tries >= 20 || ok) clearInterval(timer);
    }, 500);
  }

  function rescanAll() {
    if (!engine.historyRoot) return;
    scanExisting(engine.historyRoot);
  }

  /***********************
   * 6) Boot: config-driven only (early return if missing)
   ***********************/
  (async () => {
    const rules = await getRulesOrNull();
    if (!rules) return; // EARLY RETURN: do nothing if no config exists

    const compiled = compileRules(rules);
    startEngine(compiled);

    // Optional: live update when options page changes
    if (API.storage?.onChanged?.addListener) {
      API.storage.onChanged.addListener(async (changes, areaName) => {
        // Only react to the exact key we use
        if (!changes || !changes[STORAGE_KEY]) return;

        const newRules = await getRulesOrNull();

        // If config was removed, stop and clear (still respects "no config => do nothing")
        if (!newRules) {
          stopEngineAndClear();
          return;
        }

        // Update compiled rules and rescan existing items
        engine.compiled = compileRules(newRules);
        rescanAll();
      });
    }
  })();
})();

