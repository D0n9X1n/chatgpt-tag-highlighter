// options.js
// Options page for configuring tag rules (tag + match + color) saved into extension storage.
//
// Defaults:
// - Only [TODO] + [BUG] are created by default.
// - If storage has no config, we seed defaults so both options page and content.js can read them.
//
// Cross-browser:
// - Works in Firefox (browser.* Promise API) and Chrome (chrome.* callback API).

(() => {
  "use strict";

  const STORAGE_KEY = "tagHighlighterConfigV1";

  // Gruvbox-ish preset palette (names are case-insensitive)
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

  // Default rules: only TODO + BUG (as requested)
  const DEFAULT_RULES = [
    { tag: "[TODO]", color: "BrightYellow", match: "startsWith" },
    { tag: "[BUG]",  color: "BrightRed",    match: "startsWith" },
  ];

  // Choose the extension API namespace (Firefox prefers `browser`, Chrome uses `chrome`)
  const API =
    (typeof browser !== "undefined" && browser?.storage) ? browser :
    (typeof chrome !== "undefined" && chrome?.storage) ? chrome :
    null;

  if (!API) return;

  // Use sync storage if available, otherwise fallback to local storage
  const storageArea =
    API.storage?.sync ? API.storage.sync :
    API.storage?.local ? API.storage.local :
    null;

  if (!storageArea) return;

  // Promisified get/set that works for both browser (Promise) and chrome (callback) APIs
  function storageGet(key) {
    try {
      const r = storageArea.get(key);
      if (r && typeof r.then === "function") return r; // Firefox: Promise
    } catch {}
    return new Promise((resolve) => storageArea.get(key, resolve)); // Chrome: callback
  }

  function storageSet(obj) {
    try {
      const r = storageArea.set(obj);
      if (r && typeof r.then === "function") return r; // Firefox: Promise
    } catch {}
    return new Promise((resolve) => storageArea.set(obj, resolve)); // Chrome: callback
  }

  // Basic validators/helpers
  function isHex(s) {
    return /^#[0-9a-fA-F]{6}$/.test(String(s || "").trim());
  }

  function normalizeColorName(name) {
    const k = String(name || "").trim();
    const hit = Object.keys(PALETTE).find((x) => x.toLowerCase() === k.toLowerCase());
    return hit || null;
  }

  function safeMatch(v) {
    return String(v || "").toLowerCase() === "includes" ? "includes" : "startsWith";
  }

  function toast(msg) {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => (el.textContent = ""), 2000);
  }

  // Populate the preset color <select>
  function buildColorSelectOptions(selectEl) {
    selectEl.innerHTML = "";
    for (const [name, hex] of Object.entries(PALETTE)) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = `${name} (${hex})`;
      selectEl.appendChild(opt);
    }
  }

  // Determine what color should be previewed:
  // - If custom hex is valid, use it.
  // - Otherwise use selected palette color.
  function effectiveHexFromRow(row) {
    const hex = row.querySelector(".hex")?.value?.trim() || "";
    if (isHex(hex)) return hex;

    const name = row.querySelector(".color")?.value || "";
    return PALETTE[name] || "#999999";
  }

  function updatePreview(row) {
    const swatch = row.querySelector(".swatch");
    if (!swatch) return;
    swatch.style.background = effectiveHexFromRow(row);
  }

  // Add one editable row to the table
  function addRow(rule = { tag: "", color: "Green", match: "startsWith" }) {
    const tpl = document.getElementById("rowTemplate");
    if (!tpl) return;

    const row = tpl.content.firstElementChild.cloneNode(true);

    const tagInput = row.querySelector(".tag");
    const matchSel = row.querySelector(".match");
    const colorSel = row.querySelector(".color");
    const hexInput = row.querySelector(".hex");
    const delBtn = row.querySelector(".del");

    buildColorSelectOptions(colorSel);

    // Tag + match
    tagInput.value = String(rule.tag || "");
    matchSel.value = safeMatch(rule.match);

    // Color: accept either palette name or hex
    const colorRaw = String(rule.color || "");
    if (isHex(colorRaw)) {
      // If stored as hex, show it in custom hex field
      hexInput.value = colorRaw;
      // Keep a valid palette selection as a fallback
      colorSel.value = "Green";
    } else {
      const name = normalizeColorName(colorRaw) || "Green";
      colorSel.value = name;
      hexInput.value = "";
    }

    const onChange = () => updatePreview(row);
    tagInput.addEventListener("input", onChange);
    matchSel.addEventListener("change", onChange);
    colorSel.addEventListener("change", onChange);
    hexInput.addEventListener("input", onChange);

    delBtn.addEventListener("click", () => row.remove());

    updatePreview(row);
    document.getElementById("rows").appendChild(row);
  }

  // Read all rows from UI into rules array
  function readRulesFromUI() {
    const rows = [...document.querySelectorAll("#rows tr")];
    const rules = [];

    for (const row of rows) {
      const tag = row.querySelector(".tag")?.value?.trim() || "";
      if (!tag) continue;

      const match = safeMatch(row.querySelector(".match")?.value);

      // Save custom hex if valid; otherwise save palette name
      const hex = row.querySelector(".hex")?.value?.trim() || "";
      let color;
      if (isHex(hex)) color = hex;
      else color = row.querySelector(".color")?.value || "Green";

      rules.push({ tag, match, color });
    }

    return rules;
  }

  // Seed defaults into storage (only when missing/empty)
  async function seedIfMissing() {
    const data = await storageGet(STORAGE_KEY);
    const rules = data?.[STORAGE_KEY]?.rules;
    if (Array.isArray(rules) && rules.length > 0) return { rules };
    const cfg = { rules: DEFAULT_RULES };
    await storageSet({ [STORAGE_KEY]: cfg });
    return cfg;
  }

  async function load() {
    const cfg = await seedIfMissing();

    const rules = Array.isArray(cfg?.rules) && cfg.rules.length ? cfg.rules : DEFAULT_RULES;

    document.getElementById("rows").innerHTML = "";
    rules.forEach((r) => addRow(r));
    toast("Loaded.");
  }

  async function save() {
    const rules = readRulesFromUI();
    await storageSet({ [STORAGE_KEY]: { rules } });
    toast("Saved.");
  }

  async function reset() {
    document.getElementById("rows").innerHTML = "";
    DEFAULT_RULES.forEach((r) => addRow(r));
    await storageSet({ [STORAGE_KEY]: { rules: DEFAULT_RULES } });
    toast("Reset to default.");
  }

  // Wire up buttons
  document.getElementById("addRow").addEventListener("click", () => addRow());
  document.getElementById("save").addEventListener("click", save);
  document.getElementById("reset").addEventListener("click", reset);

  // Initial load
  load();
})();

