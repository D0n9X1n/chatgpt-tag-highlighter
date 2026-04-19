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
			tag: '[TODO]', color: '#fabd2f', match: 'startsWith', hide: false, overlay: true,
		}, // BrightYellow
		{
			tag: '[BUG]', color: '#fb4934', match: 'startsWith', hide: false, overlay: true,
		}, // BrightRed
		{
			tag: 'code', color: '#83a598', match: 'includes', hide: false, overlay: true,
		}, // Demo: highlights chats containing "code"
		{
			tag: 'help', color: '#8ec07c', match: 'includes', hide: false, overlay: true,
		}, // Demo: highlights chats containing "help"
	];

	const DEFAULT_MAX_CHAT_TURNS = 0;
	const DEFAULT_HIDE_NAV_BAR = true;

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
				overlay: r?.overlay !== false,
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
					[STORAGE_KEY]: {rules: DEFAULT_RULES, maxChatTurns: DEFAULT_MAX_CHAT_TURNS, hideNavBar: DEFAULT_HIDE_NAV_BAR, dimUntagged: false, showBadge: true},
				});
				return;
			}

			const rules = normalizeRules(existing.rules) || DEFAULT_RULES;
			const maxChatTurns
        = (typeof existing.maxChatTurns === 'number')
        	? safeInt(existing.maxChatTurns, DEFAULT_MAX_CHAT_TURNS)
        	: DEFAULT_MAX_CHAT_TURNS;

			const hideNavBar
        = (typeof existing.hideNavBar === 'boolean')
        	? existing.hideNavBar
        	: DEFAULT_HIDE_NAV_BAR;

			const dimUntagged = existing.dimUntagged === true;
			const showBadge = existing.showBadge !== false;

			// Only write if missing/invalid fields.
			const needWrite
        = !Array.isArray(existing.rules)
        	|| existing.rules.length === 0
        	|| typeof existing.maxChatTurns !== 'number'
        	|| typeof existing.hideNavBar !== 'boolean'
        	|| (existing.rules || []).some(r => typeof r.hide !== 'boolean')
        	|| (existing.rules || []).some(r => typeof r.overlay !== 'boolean')
        	|| typeof existing.dimUntagged !== 'boolean'
        	|| typeof existing.showBadge !== 'boolean';

			if (needWrite) {
				await storageSet({[STORAGE_KEY]: {rules, maxChatTurns, hideNavBar, dimUntagged, showBadge}});
			}
		} catch {
			// Best-effort: do not block extension startup.
		}
	}

	API.runtime?.onInstalled?.addListener(() => seedOrMigrate());
	API.runtime?.onStartup?.addListener?.(() => seedOrMigrate());

	// Helpful for dev: seed on background load.
	seedOrMigrate();

	// ---- Badge counter ----
	API.runtime?.onMessage?.addListener((msg) => {
		if (msg?.type === 'badgeCount') {
			const count = Number(msg.count) || 0;
			const text = count > 0 ? String(count) : '';
			try {
				API.action?.setBadgeText?.({ text });
				API.action?.setBadgeBackgroundColor?.({ color: '#fabd2f' });
			} catch {
				// Fallback for older APIs
				try {
					API.browserAction?.setBadgeText?.({ text });
					API.browserAction?.setBadgeBackgroundColor?.({ color: '#fabd2f' });
				} catch {}
			}
		}
	});
})();
