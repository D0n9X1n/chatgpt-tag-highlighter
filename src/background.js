// Background.js
// Seeds default config and performs a lightweight migration to add new fields:
// - rule.hide (boolean)
// - maxChatTurns (number)
//
// This prevents content.js from early returning due to missing config.

(() => {
	'use strict';

	const STORAGE_KEY = 'tagHighlighterConfigV1';

	const DEFAULT_RULES = [
		{
			tag: '[TODO]', color: '#fabd2f', match: 'startsWith', hide: false,
		}, // BrightYellow
		{
			tag: '[BUG]', color: '#fb4934', match: 'startsWith', hide: false,
		}, // BrightRed
	];

	const DEFAULT_MAX_CHAT_TURNS = 0;

	const API
    = (typeof browser !== 'undefined' && browser?.runtime)
    	? browser
    	: ((typeof chrome !== 'undefined' && chrome?.runtime)
    		? chrome
    		: null);

	if (!API) {
		return;
	}

	const storageArea
    = API.storage?.sync
    	? API.storage.sync
    	: (API.storage?.local
    		? API.storage.local
    		: null);

	if (!storageArea) {
		return;
	}

	function storageGet(key) {
		try {
			const r = storageArea.get(key);
			if (r && typeof r.then === 'function') {
				return r;
			}
		} catch {}

		return new Promise(resolve => storageArea.get(key, resolve));
	}

	function storageSet(object) {
		try {
			const r = storageArea.set(object);
			if (r && typeof r.then === 'function') {
				return r;
			}
		} catch {}

		return new Promise(resolve => storageArea.set(object, resolve));
	}

	function safeMatch(v) {
		return String(v || '').toLowerCase() === 'includes' ? 'includes' : 'startsWith';
	}

	function safeBool(v) {
		return v === true;
	}

	function safeInt(v, fallback) {
		const n = Number(v);
		if (!Number.isFinite(n)) {
			return fallback;
		}

		if (n < 0) {
			return 0;
		}

		return Math.floor(n);
	}

	function normalizeRules(rules) {
		if (!Array.isArray(rules) || rules.length === 0) {
			return null;
		}

		const out = [];
		for (const r of rules) {
			const tag = String(r?.tag || '').trim();
			if (!tag) {
				continue;
			}

			out.push({
				tag,
				match: safeMatch(r?.match),
				color: String(r?.color || 'Green'),
				hide: safeBool(r?.hide),
			});
		}

		return out.length > 0 ? out : null;
	}

	async function seedOrMigrate() {
		try {
			const data = await storageGet(STORAGE_KEY);
			const existing = data?.[STORAGE_KEY];

			if (!existing) {
				await storageSet({
					[STORAGE_KEY]: {rules: DEFAULT_RULES, maxChatTurns: DEFAULT_MAX_CHAT_TURNS},
				});
				return;
			}

			const rules = normalizeRules(existing.rules) || DEFAULT_RULES;
			const maxChatTurns
        = (typeof existing.maxChatTurns === 'number')
        	? safeInt(existing.maxChatTurns, DEFAULT_MAX_CHAT_TURNS)
        	: DEFAULT_MAX_CHAT_TURNS;

			// Only write if missing/invalid fields.
			const needWrite
        = !Array.isArray(existing.rules)
        	|| existing.rules.length === 0
        	|| typeof existing.maxChatTurns !== 'number'
        	|| (existing.rules || []).some(r => typeof r.hide !== 'boolean');

			if (needWrite) {
				await storageSet({[STORAGE_KEY]: {rules, maxChatTurns}});
			}
		} catch {
			// Best-effort: do not block extension startup.
		}
	}

	API.runtime?.onInstalled?.addListener(() => seedOrMigrate());
	API.runtime?.onStartup?.addListener?.(() => seedOrMigrate());

	// Helpful for dev: seed on background load.
	seedOrMigrate();
})();
