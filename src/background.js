// background.js
// Seeds default rules into storage on install/startup.
// This ensures content.js can read config from options storage;
// content.js will EARLY RETURN if config is missing, so we must seed it here.
//
// Works in both Chrome and Firefox (MV3 service worker in Chrome, background in Firefox).
// Requires: "permissions": ["storage"] and "background": { "service_worker": "background.js" } in manifest.

(() => {
  "use strict";

  const STORAGE_KEY = "tagHighlighterConfigV1";

  // Default rules (only TODO + BUG as requested)
  const DEFAULT_RULES = [
    { tag: "[TODO]", color: "BrightYellow", match: "startsWith" },
    { tag: "[BUG]",  color: "BrightRed",    match: "startsWith" },
  ];

  // Choose the extension API namespace (Firefox prefers `browser`, Chrome uses `chrome`)
  const API =
    (typeof browser !== "undefined" && browser?.runtime) ? browser :
    (typeof chrome !== "undefined" && chrome?.runtime) ? chrome :
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

  // Only seed defaults when storage is empty/missing.
  // This won't overwrite user customizations.
  async function seedIfMissing() {
    try {
      const data = await storageGet(STORAGE_KEY);
      const rules = data?.[STORAGE_KEY]?.rules;

      if (Array.isArray(rules) && rules.length > 0) return;

      await storageSet({ [STORAGE_KEY]: { rules: DEFAULT_RULES } });
    } catch {
      // Intentionally ignore errors: seeding is best-effort and should not break the extension.
    }
  }

  // Seed once on installation/update
  API.runtime?.onInstalled?.addListener(() => {
    seedIfMissing();
  });

  // Seed again on browser startup (best-effort)
  // Some environments may not support onStartup; guard it.
  API.runtime?.onStartup?.addListener?.(() => {
    seedIfMissing();
  });

  // Optional: also seed immediately when the background script loads.
  // This helps in dev when the service worker is started without onInstalled firing.
  seedIfMissing();
})();
