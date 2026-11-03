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
		if (!Array.isArray(rules)) {
			return null;
		}
		// An explicit empty list means the user removed every rule.
		if (rules.length === 0) {
			return [];
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
				color: String(r?.color || '#b8bb26'), // hex only; never persist color names
				hide: safeBool(r?.hide),
				overlay: r?.overlay !== false,
			});
		}

		return out.length > 0 ? out : null;
	}

	// ---- Config writer: every config write runs on one promise chain ----
	const PALETTE_HEX = ['#fb4934', '#b8bb26', '#fabd2f', '#83a598', '#d3869b', '#8ec07c', '#fe8019', '#928374', '#a7a7a7', '#ffffff']; // keep in sync with options.js PALETTE

	let chain = Promise.resolve();
	function enqueue(job) {
		const run = chain.then(job);
		chain = run.catch(() => {});
		return run;
	}

	// Key order does not matter when comparing configs.
	function canon(value) {
		return JSON.stringify(value, (k, x) => {
			if (x && typeof x === 'object' && !Array.isArray(x)) {
				return Object.fromEntries(Object.keys(x).sort().map(key => [key, x[key]]));
			}

			return x;
		});
	}

	const same = (a, b) => canon(a ?? null) === canon(b ?? null);

	async function readCfg() {
		const data = await storageGet(STORAGE_KEY);
		return data?.[STORAGE_KEY] ?? null;
	}

	// Compare-and-set: never applies a write made against an outdated value.
	function writeConfig(base, next) {
		return enqueue(async () => {
			if (!next || !Array.isArray(next.rules)) {
				throw new Error('Invalid config');
			}

			const current = await readCfg();
			if (same(current, base)) {
				await storageSet({[STORAGE_KEY]: next});
				return {value: next};
			}

			if (same(current, next)) {
				return {value: current}; // A retried write that already landed.
			}

			return {conflict: true, value: current}; // Changed elsewhere: write nothing.
		});
	}

	function validTag(t) {
		const s = String(t ?? '').trim();
		return s.length >= 1 && s.length <= 40 ? s : null;
	}

	// content.js "New tag": appended to the freshest stored value.
	function addRule(rawTag) {
		const tag = validTag(rawTag);
		if (!tag) {
			return Promise.reject(new Error('Tags are 1–40 characters.'));
		}

		return enqueue(async () => {
			const cfg = (await readCfg()) || {};
			const rules = Array.isArray(cfg.rules) ? cfg.rules : [];
			const existing = rules.find(r => String(r.tag).trim() === tag); // Any match type.
			if (existing) {
				return {rule: existing, created: false};
			}

			const used = new Set(rules.map(r => String(r.color).toLowerCase()));
			const rule = {
				tag, match: 'startsWith', color: PALETTE_HEX.find(h => !used.has(h)) || '#a7a7a7', hide: false, overlay: true,
			};
			await storageSet({[STORAGE_KEY]: {...cfg, rules: [...rules, rule]}});
			return {rule, created: true};
		});
	}

	async function seedOrMigrateNow() {
		try {
			const data = await storageGet(STORAGE_KEY);
			const existing = data?.[STORAGE_KEY];

			if (!existing) {
				await storageSet({
					[STORAGE_KEY]: {rules: DEFAULT_RULES, maxChatTurns: DEFAULT_MAX_CHAT_TURNS, hideNavBar: DEFAULT_HIDE_NAV_BAR, dimUntagged: false, showBadge: true, lazyRenderTurns: true, showDeleteUntagged: false, showQuickTag: true},
				});
				return;
			}

			const normalizedRules = normalizeRules(existing.rules);
			const rules = normalizedRules ?? DEFAULT_RULES;
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
			const lazyRenderTurns = existing.lazyRenderTurns !== false;
			const showDeleteUntagged = existing.showDeleteUntagged === true;
			const showQuickTag = existing.showQuickTag !== false;

			// Only write if missing/invalid fields.
			const needWrite
        = normalizedRules === null
        	|| typeof existing.maxChatTurns !== 'number'
        	|| typeof existing.hideNavBar !== 'boolean'
        	|| (existing.rules || []).some(r => typeof r.hide !== 'boolean')
        	|| (existing.rules || []).some(r => typeof r.overlay !== 'boolean')
        	|| typeof existing.dimUntagged !== 'boolean'
        	|| typeof existing.showBadge !== 'boolean'
        	|| typeof existing.lazyRenderTurns !== 'boolean'
        	|| typeof existing.showDeleteUntagged !== 'boolean'
        	|| typeof existing.showQuickTag !== 'boolean';

			if (needWrite) {
				await storageSet({[STORAGE_KEY]: {rules, maxChatTurns, hideNavBar, dimUntagged, showBadge, lazyRenderTurns, showDeleteUntagged, showQuickTag}});
			}
		} catch {
			// Best-effort: do not block extension startup.
		}
	}

	const seedOrMigrate = () => enqueue(seedOrMigrateNow); // Migration shares the write chain.

	// ---- Settings popup ----
	// storage.session survives worker restarts (Chrome 102+, Firefox 115+); memory otherwise.
	const SETTINGS_WIN_KEY = 'cthSettingsWindowId';
	const winMem = {};
	const sessionArea = API.storage?.session ?? {
		async get(k) {
			return {[k]: winMem[k]};
		},
		async set(o) {
			Object.assign(winMem, o);
		},
	};

	// Rapid clicks open one window.
	let settingsChain = Promise.resolve();
	function settingsQueue(job) {
		const run = settingsChain.then(job);
		settingsChain = run.catch(() => {});
		return run;
	}

	async function storedSettingsWindowId() {
		return (await sessionArea.get(SETTINGS_WIN_KEY))?.[SETTINGS_WIN_KEY];
	}

	// Wide enough for every rule row on one line; never larger than the browser window.
	const SETTINGS_WIDTH = 1040;
	const SETTINGS_HEIGHT = 760;

	const usableSize = w => Number.isFinite(w?.width) && w.width > 0 && Number.isFinite(w?.height) && w.height > 0;

	// The last-focused window, else the current one, else the default size.
	async function settingsWindowSize() {
		for (const get of ['getLastFocused', 'getCurrent']) {
			try {
				const win = await API.windows[get]?.();
				if (usableSize(win)) {
					return {width: Math.min(SETTINGS_WIDTH, win.width), height: Math.min(SETTINGS_HEIGHT, win.height)};
				}
			} catch {}
		}

		return {width: SETTINGS_WIDTH, height: SETTINGS_HEIGHT};
	}

	function openSettings() {
		return settingsQueue(async () => {
			try {
				if (!API.windows?.create) {
					throw new Error('no windows API');
				}

				const id = await storedSettingsWindowId();
				if (typeof id === 'number') {
					try {
						await API.windows.get(id);
						await API.windows.update(id, {focused: true});
						return {};
					} catch {} // Closed while we were not watching: open a new one.
				}

				const {width, height} = await settingsWindowSize();
				const w = await API.windows.create({
					url: API.runtime.getURL('options.html'), type: 'popup', width, height, focused: true,
				});
				await sessionArea.set({[SETTINGS_WIN_KEY]: w?.id ?? null});
			} catch {
				await API.runtime.openOptionsPage?.();
			}

			return {};
		});
	}

	API.windows?.onRemoved?.addListener?.(id => settingsQueue(async () => {
		if (await storedSettingsWindowId() === id) {
			await sessionArea.set({[SETTINGS_WIN_KEY]: null});
		}
	}));
	(API.action ?? API.browserAction)?.onClicked?.addListener?.(() => {
		openSettings();
	});

	API.runtime?.onInstalled?.addListener(() => seedOrMigrate());
	API.runtime?.onStartup?.addListener?.(() => seedOrMigrate());

	// Helpful for dev: seed on background load.
	seedOrMigrate();

	// ---- Per-chat rename lock (quick tag), across tabs in this browser ----
	// content.js connects a port named `cth-chat-lock:<id>` and first posts
	// {type: 'acquire'}, or {type: 'override'} after the user chose "Tag anyway".
	// Ports queue per chat; the head is granted (phase 'pre'). Before its PATCH
	// the holder posts {type: 'write'}: the write is recorded in storage.session
	// first (so a restarted worker honours it), then acknowledged ('writing').
	// After the PATCH it posts {type: 'done', outcome}: 'ok', 'refused' and
	// 'not-sent' clear the record and release at once. 'unknown', or leaving
	// mid-PATCH (its tab closed), marks the record unknown: that chat is then
	// blocked, with no expiry, until an override or the browser session ends.
	// Fail closed: an unreadable record refuses; an unwritable one is never acked.
	const CHAT_LOCK_PREFIX = 'cth-chat-lock:';
	const WRITING_KEY = 'cthWritingChats';
	const chatLocks = new Map(); // id -> [{port, phase, ready, override}], head holds the lock
	let lockChain = Promise.resolve();

	// Every lock change runs on one chain, so storage reads never race.
	function lockJob(job) {
		lockChain = lockChain.then(job).catch(() => {});
		return lockChain;
	}

	// Throws when storage.session can't be read: callers fail closed.
	async function writingRecords() {
		const all = (await sessionArea.get(WRITING_KEY))?.[WRITING_KEY];
		return all && typeof all === 'object' ? all : {};
	}

	async function setWritingRecord(id, record) {
		const all = {...await writingRecords()};
		if (record === null) {
			delete all[id];
		} else {
			all[id] = record;
		}

		await sessionArea.set({[WRITING_KEY]: all});
	}

	async function markUnknown(id) {
		try {
			const since = (await writingRecords())[id]?.since ?? Date.now();
			await setWritingRecord(id, {since, unknown: true});
		} catch {} // The 'writing' record still blocks the chat.
	}

	function postTo(port, msg) {
		try {
			port.postMessage(msg);
		} catch {} // Already gone: its onDisconnect moves the queue on.
	}

	function removeLockEntry(id, entry) {
		const queue = chatLocks.get(id);
		const i = queue ? queue.indexOf(entry) : -1;
		if (i === -1) {
			return false;
		}

		queue.splice(i, 1);
		if (queue.length === 0) {
			chatLocks.delete(id);
		}

		return true;
	}

	function refuseHead(id, head, reason) {
		removeLockEntry(id, head);
		head.phase = 'refused';
		postTo(head.port, {type: 'blocked', reason});
	}

	async function grantNext(id) {
		for (;;) {
			const head = chatLocks.get(id)?.[0];
			if (!head || head.phase !== 'waiting' || !head.ready) {
				return;
			}

			let record;
			try {
				record = (await writingRecords())[id];
				if (record && head.override) {
					await setWritingRecord(id, null); // "Tag anyway": this chat only.
					record = undefined;
				}
			} catch {
				refuseHead(id, head, 'storage');
				continue;
			}

			if (record) {
				// No live holder owns it: an earlier rename never confirmed.
				refuseHead(id, head, 'unknown');
				continue;
			}

			head.phase = 'pre';
			postTo(head.port, {granted: true});
			return;
		}
	}

	async function onLockMessage(id, entry, msg) {
		const type = msg?.type;
		if ((type === 'acquire' || type === 'override') && !entry.ready && entry.phase === 'waiting') {
			entry.ready = true;
			entry.override = type === 'override';
			await grantNext(id);
			return;
		}

		if (chatLocks.get(id)?.[0] !== entry) {
			return;
		}

		if (type === 'write' && entry.phase === 'pre') {
			try {
				await setWritingRecord(id, {since: Date.now(), unknown: false});
			} catch {
				postTo(entry.port, {type: 'write-denied'}); // Not recorded: never let it PATCH.
				return;
			}

			entry.phase = 'writing';
			postTo(entry.port, {type: 'write-ack'});
		} else if (type === 'done' && entry.phase === 'writing') {
			entry.phase = 'settled';
			removeLockEntry(id, entry);
			if (msg.outcome === 'ok' || msg.outcome === 'refused' || msg.outcome === 'not-sent') {
				try {
					await setWritingRecord(id, null);
				} catch {} // Left in place, it blocks the chat: safe.
			} else {
				await markUnknown(id);
			}

			await grantNext(id);
		}
	}

	async function leaveLock(id, entry) {
		const wasHead = chatLocks.get(id)?.[0] === entry;
		if (!removeLockEntry(id, entry)) {
			return;
		}

		if (entry.phase === 'writing') {
			await markUnknown(id); // Its tab closed mid-PATCH: the outcome is unknown.
		}

		if (wasHead) {
			await grantNext(id);
		}
	}

	API.runtime?.onConnect?.addListener?.(port => {
		if (!String(port?.name || '').startsWith(CHAT_LOCK_PREFIX)) {
			return;
		}

		const id = port.name.slice(CHAT_LOCK_PREFIX.length);
		const entry = {port, phase: 'waiting', ready: false, override: false};
		lockJob(() => {
			const queue = chatLocks.get(id) || [];
			chatLocks.set(id, queue);
			queue.push(entry);
		});
		port.onMessage?.addListener?.(msg => lockJob(() => onLockMessage(id, entry, msg)));
		port.onDisconnect.addListener(() => lockJob(() => leaveLock(id, entry)));
	});

	// ---- Messages: badge counter + config writes ----
	API.runtime?.onMessage?.addListener((msg, sender, sendResponse) => {
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

		let job = null;
		if (msg?.type === 'writeConfig') {
			job = writeConfig(msg.base ?? null, msg.next);
		} else if (msg?.type === 'addRule') {
			job = addRule(msg.tag);
		} else if (msg?.type === 'openSettings') {
			job = openSettings();
		}

		if (!job) {
			return false;
		}

		job.then(
			r => sendResponse({ok: !r.conflict, ...r}),
			e => sendResponse({ok: false, error: String(e?.message || e)}),
		);
		return true; // Reply asynchronously.
	});
})();
