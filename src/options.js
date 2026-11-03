// Options.js
// Stores ONLY hex colors (#RRGGBB) in storage. Order matters.
// UI is driven by options.html template (#rowTemplate) + tbody (#rows).

(() => {
	'use strict';

	const STORAGE_KEY = 'tagHighlighterConfigV1';

	const API
    = (typeof browser !== 'undefined' && browser?.storage)
    	? browser
    	: ((typeof chrome !== 'undefined' && chrome?.storage)
    		? chrome
    		: null);
	if (!API) {
		return;
	}

	const store = API.storage?.sync ?? API.storage?.local;
	if (!store) {
		return;
	}

	const $ = id => document.getElementById(id);

	const els = {
		rows: $('rows'),
		tpl: $('rowTemplate'),
		addRow: $('addRow'),
		maxChatTurns: $('maxChatTurns'),
		hideNavBar: $('hideNavBar'),
		dimUntagged: $('dimUntagged'),
		showBadge: $('showBadge'),
		lazyRenderTurns: $('lazyRenderTurns'),
		showDeleteUntagged: $('showDeleteUntagged'),
		showQuickTag: $('showQuickTag'),
		conflict: $('conflict'),
		conflictReload: $('conflictReload'),
		toast: $('toast'),
		exportCfg: $('exportCfg'),
		importCfg: $('importCfg'),
		importPanel: $('importPanel'),
		importText: $('importText'),
		importApply: $('importApply'),
		importCancel: $('importCancel'),
		debugTitle: $('debugTitle'),
		debugResult: $('debugResult'),
	};

	// ---- Palette (display only; stored as hex) ----
	const PALETTE = [
		['Gruvbox Red', '#fb4934'],
		['Gruvbox Green', '#b8bb26'],
		['Gruvbox Yellow', '#fabd2f'],
		['Gruvbox Blue', '#83a598'],
		['Gruvbox Purple', '#d3869b'],
		['Gruvbox Aqua', '#8ec07c'],
		['Gruvbox Orange', '#fe8019'],
		['Gruvbox Gray', '#928374'],
		['Light Gray', '#a7a7a7'],
		['White', '#ffffff'],
	];

	// Legacy mapping: accepts old non-hex values, but we ALWAYS save hex.
	const LEGACY = Object.freeze({
		red: '#fb4934',
		green: '#b8bb26',
		yellow: '#fabd2f',
		blue: '#83a598',
		purple: '#d3869b',
		aqua: '#8ec07c',
		orange: '#fe8019',
		gray: '#928374',
		grey: '#928374',
		brightred: '#fb4934',
		brightgreen: '#b8bb26',
		brightyellow: '#fabd2f',
		brightblue: '#83a598',
		brightpurple: '#d3869b',
		brightaqua: '#8ec07c',
		brightorange: '#fe8019',
		gruvboxred: '#fb4934',
		gruvboxgreen: '#b8bb26',
		gruvboxyellow: '#fabd2f',
		gruvboxblue: '#83a598',
		gruvboxpurple: '#d3869b',
		gruvboxaqua: '#8ec07c',
		gruvboxorange: '#fe8019',
		gruvboxgray: '#928374',
		gruvboxgrey: '#928374',
	});

	const DEFAULT_CFG = () => ({
		rules: [
			{
				tag: '[TODO]', match: 'startsWith', color: '#fabd2f', hide: false, overlay: true,
			},
			{
				tag: '[BUG]', match: 'startsWith', color: '#fb4934', hide: false, overlay: true,
			},
			{
				tag: 'code', match: 'includes', color: '#83a598', hide: false, overlay: true,
			},
			{
				tag: 'help', match: 'includes', color: '#8ec07c', hide: false, overlay: true,
			},
		],
		maxChatTurns: 0,
		hideNavBar: true,
		dimUntagged: false,
		showBadge: true,
		lazyRenderTurns: true,
		showDeleteUntagged: false,
		showQuickTag: true,
	});

	// ---- Storage helpers (promise + callback compatible) ----
	const get = key =>
		new Promise(resolve => {
			try {
				const r = store.get(key);
				if (r?.then) {
					r.then(resolve);
				} else {
					store.get(key, resolve);
				}
			} catch {
				store.get(key, resolve);
			}
		});

	// Config writes go through background.js (compare-and-set); this page never writes storage.
	function sendRuntimeMessage(msg) { // Keep in sync with content.js
		return new Promise((resolve, reject) => {
			try {
				const callback = API === globalThis.chrome
					? res => {
						const e = API.runtime.lastError;
						if (e) {
							reject(new Error(e.message));
						} else {
							resolve(res);
						}
					}
					: undefined;
				const r = API.runtime.sendMessage(msg, callback);
				if (r?.then) {
					r.then(resolve, reject);
				}
			} catch (e) {
				reject(e);
			}
		});
	}

	// ---- Color normalization (ALWAYS -> #rrggbb) ----
	const isHex6 = s => /^#[\da-fA-F]{6}$/.test(String(s || '').trim());
	const isHex3 = s => /^#[\da-fA-F]{3}$/.test(String(s || '').trim());
	const normKey = s => String(s || '').toLowerCase().replaceAll(/[^a-z\d]/g, '');

	const expandHex3 = h => {
		const x = h.slice(1);
		return (`#${x[0]}${x[0]}${x[1]}${x[1]}${x[2]}${x[2]}`).toLowerCase();
	};

	function toHex(value, fallback = '#999999') {
		const v = String(value || '').trim();
		if (!v) {
			return fallback;
		}

		if (isHex6(v)) {
			return v.toLowerCase();
		}

		if (isHex3(v)) {
			return expandHex3(v);
		}

		const k = normKey(v);
		if (LEGACY[k]) {
			return LEGACY[k];
		}

		// Allow palette label input
		for (const element of PALETTE) {
			if (normKey(element[0]) === k) {
				return element[1];
			}
		}

		return fallback;
	}

	const safeMatch = v => (String(v || '').toLowerCase() === 'includes' ? 'includes' : 'startsWith');
	const safeInt = (v, fb = 0) => {
		const n = Number(v);
		return Number.isFinite(n) ? Math.max(0, Math.floor(n)) : fb;
	};

	// Same key order as collectConfig().
	function normalizeCfg(raw) {
		return {
			rules: (raw.rules || []).map(r => ({
				tag: String(r?.tag || '').trim(),
				match: safeMatch(r?.match),
				color: toHex(r?.color, '#999999'),
				hide: r?.hide === true,
				overlay: r?.overlay !== false,
			})).filter(r => r.tag),
			maxChatTurns: safeInt(raw.maxChatTurns, 0),
			hideNavBar: raw.hideNavBar !== false,
			dimUntagged: raw.dimUntagged === true,
			showBadge: raw.showBadge !== false,
			lazyRenderTurns: raw.lazyRenderTurns !== false,
			showDeleteUntagged: raw.showDeleteUntagged === true,
			showQuickTag: raw.showQuickTag !== false,
		};
	}

	// Key order does not matter: chrome.storage returns objects with sorted keys. Keep in sync with background.js canon().
	function canon(value) {
		return JSON.stringify(value, (k, x) => {
			if (x && typeof x === 'object' && !Array.isArray(x)) {
				return Object.fromEntries(Object.keys(x).sort().map(key => [key, x[key]]));
			}

			return x;
		});
	}

	const eq = (a, b) => canon(a ?? null) === canon(b ?? null);

	// ---- Toast ----
	let toastTimer = 0;
	function toast(message, sticky = false) {
		els.toast.textContent = message;
		els.toast.classList.add('show');
		clearTimeout(toastTimer);
		if (sticky) {
			return;
		}

		toastTimer = setTimeout(() => {
			els.toast.classList.remove('show');
			els.toast.textContent = '';
		}, 1400);
	}

	// ---- Row creation / binding ----
	function buildPaletteOptions(selectElement) {
		// First option: Custom
		selectElement.innerHTML = '';
		const o0 = document.createElement('option');
		o0.value = '';
		o0.textContent = 'Custom…';
		selectElement.append(o0);

		for (const element of PALETTE) {
			const o = document.createElement('option');
			o.value = element[1];
			o.textContent = element[0]; // The hex is in its own column.
			selectElement.append(o);
		}
	}

	function setPreview(tr, hex) {
		const sw = tr.querySelector('.swatch');
		sw.style.background = hex;
		sw.style.boxShadow = `0 0 0 1px ${hex}55 inset`;
	}

	function setRowColor(tr, hex) {
		const h = toHex(hex);
		tr.dataset.color = h; // Last committed colour: a partially typed hex never replaces it.
		tr.querySelector('.hex').value = h;
		// Select preset if matches, else "Custom…"
		const sel = tr.querySelector('.color');
		sel.value = [...sel.options].some(o => o.value === h) ? h : '';
		setPreview(tr, h);
	}

	function createRow(rule) {
		const tr = els.tpl.content.firstElementChild.cloneNode(true);

		const tag = String(rule?.tag || '').trim();
		const match = safeMatch(rule?.match);
		const hide = rule?.hide === true;

		const sel = tr.querySelector('.color');
		buildPaletteOptions(sel);

		tr.querySelector('.tag').value = tag;
		tr.querySelector('.match').value = match;
		tr.querySelector('.hide').checked = hide;

		const overlay = rule?.overlay !== false;
		tr.querySelector('.overlay').checked = overlay;

		setRowColor(tr, rule?.color);

		return tr;
	}

	// ---- Render ----
	function clearRows() {
		els.rows.textContent = '';
	}

	function render(cfg) {
		clearRows();
		els.maxChatTurns.value = String(safeInt(cfg.maxChatTurns, 0));
		els.hideNavBar.checked = cfg.hideNavBar !== false;
		els.dimUntagged.checked = cfg.dimUntagged === true;
		els.showBadge.checked = cfg.showBadge !== false;
		els.lazyRenderTurns.checked = cfg.lazyRenderTurns !== false;
		els.showDeleteUntagged.checked = cfg.showDeleteUntagged === true;
		els.showQuickTag.checked = cfg.showQuickTag !== false;

		const rules = Array.isArray(cfg.rules) ? cfg.rules : [];
		for (const rule of rules) {
			els.rows.append(createRow(rule));
		}

		updateRowNumbers();
		runDebugTest();
	}

	// Also disables Move up on the first row and Move down on the last.
	function updateRowNumbers() {
		const trs = els.rows.querySelectorAll('tr');
		for (let i = 0; i < trs.length; i++) {
			const cell = trs[i].querySelector('.rowNum');
			if (cell) cell.textContent = String(i + 1);
			const up = trs[i].querySelector('.moveUp');
			const down = trs[i].querySelector('.moveDown');
			if (up) up.disabled = i === 0;
			if (down) down.disabled = i === trs.length - 1;
		}
	}

	// ---- Read UI -> config (enforce hex) ----
	function collectConfig() {
		const trs = els.rows.querySelectorAll('tr');
		const rules = [];

		for (const tr of trs) {
			const tag = String(tr.querySelector('.tag').value || '').trim();
			if (!tag) {
				continue;
			}

			rules.push({
				tag,
				match: safeMatch(tr.querySelector('.match').value),
				color: toHex(tr.querySelector('.hex').value, tr.dataset.color || '#999999'), // ONLY hex persisted
				hide: tr.querySelector('.hide').checked === true,
				overlay: tr.querySelector('.overlay').checked !== false,
			});
		}

		return {
			rules,
			maxChatTurns: safeInt(els.maxChatTurns.value, 0),
			hideNavBar: els.hideNavBar.checked,
			dimUntagged: els.dimUntagged.checked,
			showBadge: els.showBadge.checked,
			lazyRenderTurns: els.lazyRenderTurns.checked,
			showDeleteUntagged: els.showDeleteUntagged.checked,
			showQuickTag: els.showQuickTag.checked,
		};
	}

	// ---- Auto-save (compare-and-set through background.js) ----
	// base: the last stored value rendered or acknowledged; a save is written only if storage still equals it.
	// gen changes on every render from storage (incl. Reload); a reply from an older gen is ignored.
	// rendering blocks saves caused by our own render.
	let ready = false; // An empty table during storage loading isn't an empty config.
	let base = null;
	let dirty = false;
	let inFlight = false;
	let pending = false;
	let conflict = false;
	let failed = null;
	let sentNext = null;
	let sentGen = -1;
	let editSeq = 0;
	let gen = 0;
	let rendering = false;
	let retryTimer = 0;
	let retryStep = 0;
	let okMessage = 'Auto-saved ✓';
	let draggedRow = null;
	const uncommitted = new Set(); // Row text fields typed into but not yet committed (change/blur).
	const RETRY_MS = [1000, 3000];

	// Every programmatic render goes through here.
	function show(cfg) {
		gen++;
		uncommitted.clear();
		draggedRow = null; // The rows are rebuilt: a drag in progress is over (its dragend never reaches #rows).
		rendering = true;
		try {
			render(cfg);
		} finally {
			rendering = false;
		}
	}

	function buildWrite() {
		return {base, next: collectConfig(), seq: editSeq};
	}

	function autoSave(message) {
		if (!ready || rendering) {
			return;
		}

		dirty = true;
		if (message) {
			okMessage = message;
		}

		if (conflict) {
			return; // The banner is up: edits stay on screen, nothing is sent.
		}

		if (inFlight) {
			pending = true; // One save at a time.
			return;
		}

		if (failed) {
			pending = true;
			sendWrite(failed); // Retry the same write first.
			return;
		}

		sendWrite(buildWrite());
	}

	async function sendWrite(write) {
		clearTimeout(retryTimer);
		if (conflict) {
			return; // The banner suspends saving, including automatic retries.
		}

		inFlight = true;
		sentNext = write.next;
		sentGen = gen;
		const myGen = gen;
		const {seq, ...payload} = write; // seq stays local
		let res;
		try {
			res = await sendRuntimeMessage({type: 'writeConfig', ...payload});
			if (!res) {
				throw new Error('failed');
			}
		} catch {
			// Never write storage here: keep the draft and retry the same {base, next}.
			inFlight = false;
			if (myGen !== gen) {
				flushPending(); // Reloaded since: drop this write.
				return;
			}

			failed = write;
			toast('Not saved — retrying', true);
			if (retryStep < RETRY_MS.length) {
				retryTimer = setTimeout(() => sendWrite(write), RETRY_MS[retryStep++]);
			}

			return;
		}

		inFlight = false;
		if (myGen !== gen) {
			flushPending(); // Stale reply (Reload or re-render since): ignore it.
			return;
		}

		failed = null;
		retryStep = 0;
		if (!res.ok && !res.conflict) {
			// The background refused this write (e.g. storage quota): resending the
			// same payload can't help. Keep the draft; the next edit sends a fresh write.
			toast(`Couldn't save: ${res.error || 'unknown error'}`, true);
			if (pending) {
				pending = false;
				sendWrite(buildWrite());
			}

			return;
		}

		if (res.conflict) {
			pending = false;
			if (dirty) {
				showConflict();
			} else {
				// A lost init/migration race: just adopt the stored value.
				base = res.value;
				hideConflict();
				show(normalizeCfg(res.value || DEFAULT_CFG()));
			}

			return;
		}

		base = res.value;
		if (conflict) {
			pending = false; // The banner suspends saving: keep the draft, send nothing more.
			return;
		}

		if (pending) {
			pending = false;
			sendWrite(buildWrite()); // Carries its own seq.
			return;
		}

		if (editSeq === seq && uncommitted.size === 0) {
			dirty = false; // No edit since this write was built and nothing half-typed on screen.
		}

		toast(okMessage);
		okMessage = 'Auto-saved ✓';
	}

	// Edits made after a Reload.
	function flushPending() {
		if (pending && !conflict) {
			pending = false;
			sendWrite(buildWrite());
		}
	}

	function showConflict() {
		conflict = true;
		clearTimeout(retryTimer); // No automatic retry while the banner is up; Reload discards the draft.
		failed = null;
		retryStep = 0;
		els.conflict.hidden = false;
	}

	function hideConflict() {
		conflict = false;
		els.conflict.hidden = true;
	}

	// Discards the draft; any reply still in flight is now stale.
	async function reload() {
		const v = (await get(STORAGE_KEY))?.[STORAGE_KEY];
		clearTimeout(retryTimer);
		base = v ?? null;
		dirty = false;
		pending = false;
		failed = null;
		retryStep = 0;
		hideConflict();
		show(normalizeCfg(v || DEFAULT_CFG()));
	}

	els.conflictReload.addEventListener('click', reload);

	// Capture phase: counts the edit before autoSave records seq.
	for (const box of [els.rows, ...document.querySelectorAll('.generalRow')]) {
		for (const type of ['input', 'change']) {
			box.addEventListener(type, () => {
				if (ready && !rendering) {
					editSeq++;
					dirty = true;
				}
			}, true);
		}
	}

	const isRowText = el => el.classList?.contains('tag') || el.classList?.contains('hex');
	els.rows.addEventListener('input', e => {
		if (ready && !rendering && isRowText(e.target)) {
			uncommitted.add(e.target);
		}
	}, true);
	for (const type of ['change', 'focusout']) {
		els.rows.addEventListener(type, e => uncommitted.delete(e.target), true);
	}

	API.storage?.onChanged?.addListener((changes, area) => {
		const v = changes[STORAGE_KEY]?.newValue;
		if (!v || !ready || API.storage[area] !== store) {
			return;
		}

		const live = inFlight && sentGen === gen; // A write from before a Reload is not ours any more.
		if (eq(v, base) || (live && eq(v, sentNext))) {
			return; // Our own echo (only while that write is in flight).
		}

		if (!dirty && !live && !conflict && !draggedRow) { // A drag in progress is an unsaved edit.
			base = v;
			show(normalizeCfg(v));
			return;
		}

		showConflict(); // Unsaved edits or a save in flight: keep the draft, write nothing.
	});

	function onRulesChanged() {
		updateRowNumbers();
		runDebugTest();
		autoSave();
	}

	// ---- Event delegation for best performance ----
	els.rows.addEventListener('change', e => {
		const tr = e.target.closest('tr');
		if (!tr) {
			return;
		}

		if (e.target.classList.contains('color')) {
			const hex = e.target.value ? toHex(e.target.value) : toHex(tr.querySelector('.hex').value);
			setRowColor(tr, hex);
		}

		if (e.target.classList.contains('hex')) {
			setRowColor(tr, e.target.value);
		}

		onRulesChanged();
	});

	els.rows.addEventListener('click', e => {
		const tr = e.target.closest('tr');
		if (!tr) {
			return;
		}

		if (e.target.classList.contains('del')) {
			tr.remove();
			onRulesChanged();
			return;
		}

		// Keyboard-friendly reorder (#77): the same save path as a drop.
		const move = e.target.closest('.moveUp, .moveDown');
		if (move) {
			const up = move.classList.contains('moveUp');
			const sibling = up ? tr.previousElementSibling : tr.nextElementSibling;
			if (!sibling) {
				return;
			}

			if (up) {
				sibling.before(tr);
			} else {
				sibling.after(tr);
			}

			onRulesChanged();
			// Moving the row blurs the button; keep focus on it, or on its
			// enabled twin if it just became disabled at an end.
			const twin = tr.querySelector(up ? '.moveDown' : '.moveUp');
			(move.disabled ? twin : move).focus();
		}
	});

	// Normalize hex on blur (covers paste + partial input)
	els.rows.addEventListener('blur', e => {
		if (rendering) {
			return; // Removing a focused row during a render blurs it.
		}

		const tr = e.target.closest('tr');
		if (!tr) {
			return;
		}

		if (e.target.classList.contains('hex')) {
			setRowColor(tr, e.target.value);
		}

		if (e.target.classList.contains('tag') || e.target.classList.contains('hex')) {
			onRulesChanged();
		}
	}, true);

	// ---- Buttons ----
	els.addRow.addEventListener('click', () => {
		const tr = createRow({
			tag: '', match: 'startsWith', color: PALETTE[0][1], hide: false, overlay: true,
		});
		els.rows.append(tr);
		onRulesChanged();
		tr.querySelector('.tag').focus();
	});

	// ---- General section auto-save ----
	els.maxChatTurns.addEventListener('input', () => autoSave());
	els.hideNavBar.addEventListener('change', () => autoSave());
	els.dimUntagged.addEventListener('change', () => autoSave());
	els.showBadge.addEventListener('change', () => autoSave());
	els.lazyRenderTurns.addEventListener('change', () => autoSave());
	els.showDeleteUntagged.addEventListener('change', () => autoSave());
	els.showQuickTag.addEventListener('change', () => autoSave());

	// ---- Import / Export ----
	els.exportCfg.addEventListener('click', async () => {
		const cfg = collectConfig();
		try {
			await navigator.clipboard.writeText(JSON.stringify(cfg, null, 2));
			toast('Copied ✓');
		} catch {
			const ta = document.createElement('textarea');
			ta.value = JSON.stringify(cfg, null, 2);
			document.body.append(ta);
			ta.select();
			document.execCommand('copy');
			ta.remove();
			toast('Copied ✓');
		}
	});

	els.importCfg.addEventListener('click', () => {
		els.importPanel.style.display = els.importPanel.style.display === 'none' ? '' : 'none';
		els.importText.value = '';
		if (els.importPanel.style.display !== 'none') els.importText.focus();
	});

	els.importCancel.addEventListener('click', () => {
		els.importPanel.style.display = 'none';
		els.importText.value = '';
	});

	els.importApply.addEventListener('click', () => {
		const raw = els.importText.value.trim();
		let parsed;
		try { parsed = JSON.parse(raw); } catch { toast('Invalid config'); return; }
		if (!parsed || !Array.isArray(parsed.rules)) { toast('Invalid config'); return; }

		const cfg = normalizeCfg(parsed);
		if (parsed.rules.length > 0 && cfg.rules.length === 0) { toast('Invalid config'); return; }

		render(cfg);
		els.importPanel.style.display = 'none';
		els.importText.value = '';
		autoSave('Imported ✓'); // Written against the current base.
	});

	// ---- Drag-and-drop reorder ----

	els.rows.addEventListener('dragstart', e => {
		const handle = e.target.closest('.dragHandle');
		if (!handle) { e.preventDefault(); return; }
		draggedRow = handle.closest('tr');
		if (!draggedRow) { e.preventDefault(); return; }
		draggedRow.classList.add('dragging');
		e.dataTransfer.effectAllowed = 'move';
		e.dataTransfer.setData('text/plain', '');
	});

	els.rows.addEventListener('dragover', e => {
		e.preventDefault();
		e.dataTransfer.dropEffect = 'move';
		const targetRow = e.target.closest('tr');
		if (!targetRow || targetRow === draggedRow) return;
		for (const tr of els.rows.querySelectorAll('.drag-over')) tr.classList.remove('drag-over');
		targetRow.classList.add('drag-over');
	});

	els.rows.addEventListener('dragleave', e => {
		const targetRow = e.target.closest('tr');
		if (targetRow) targetRow.classList.remove('drag-over');
	});

	els.rows.addEventListener('drop', e => {
		e.preventDefault();
		const targetRow = e.target.closest('tr');
		if (!targetRow || !draggedRow || targetRow === draggedRow) return;
		if (draggedRow.parentNode !== els.rows) return; // Re-rendered (e.g. Reload) mid-drag: the row is gone.
		const rect = targetRow.getBoundingClientRect();
		const midY = rect.top + rect.height / 2;
		if (e.clientY < midY) {
			els.rows.insertBefore(draggedRow, targetRow);
		} else {
			els.rows.insertBefore(draggedRow, targetRow.nextElementSibling);
		}
		autoSave();
	});

	els.rows.addEventListener('dragend', () => {
		if (draggedRow) { draggedRow.classList.remove('dragging'); draggedRow = null; }
		for (const tr of els.rows.querySelectorAll('.drag-over')) tr.classList.remove('drag-over');
		onRulesChanged();
	});

	// Build the small swatch span used by the rule tester. `hex` is already
	// normalized to /^#[0-9a-f]{6}$/ by toHex(), so .style.background is safe.
	// Sizing/alignment live in options.css under .debugResult .swatch.
	function buildSwatch(hex) {
		const sw = document.createElement('span');
		sw.className = 'swatch';
		sw.style.background = hex;
		return sw;
	}

	// Build one result row. `tag` is user-controlled — only ever assigned via
	// textContent (never innerHTML), so XSS payloads render as literal text.
	// `marker` is the leading glyph (✓ or ✗) — passed in rather than mutated
	// after the fact, so the caller never has to reach into .firstChild.
	function buildResultRow(className, marker, idx, hex, tag, matchKind, suffix) {
		const div = document.createElement('div');
		div.className = className;
		div.append(document.createTextNode(`${marker} #${idx + 1} `));
		div.append(buildSwatch(hex));
		div.append(document.createTextNode(' '));
		const code = document.createElement('code');
		code.textContent = tag;
		div.append(code);
		div.append(document.createTextNode(` (${matchKind})`));
		if (suffix) {
			div.append(suffix);
		}
		return div;
	}

	// ---- Rule tester ----
	function runDebugTest() {
		const title = els.debugTitle.value.trim();
		if (!title) {
			els.debugResult.textContent = 'Type a title above to see which rule matches.';
			return;
		}

		const trs = els.rows.querySelectorAll('tr');
		let winnerIdx = -1;
		const nodes = [];

		for (let i = 0; i < trs.length; i++) {
			const tag = String(trs[i].querySelector('.tag').value || '').trim();
			if (!tag) continue;
			const match = safeMatch(trs[i].querySelector('.match').value);
			const hit = match === 'startsWith' ? title.startsWith(tag) : title.includes(tag);
			const hex = toHex(trs[i].querySelector('.hex').value);

			if (hit && winnerIdx === -1) {
				winnerIdx = i;
				const winner = document.createElement('span');
				winner.append(document.createTextNode(' — '));
				const b = document.createElement('b');
				b.textContent = 'WINNER';
				winner.append(b);
				nodes.push(buildResultRow('matchHit', '✓', i, hex, tag, match, winner));
			} else if (hit) {
				const suffix = document.createTextNode(` — matches but skipped (rule #${winnerIdx + 1} won)`);
				nodes.push(buildResultRow('matchSkipped', '✓', i, hex, tag, match, suffix));
			} else {
				nodes.push(buildResultRow('matchMiss', '✗', i, hex, tag, match, null));
			}
		}

		if (winnerIdx === -1) {
			const noneDiv = document.createElement('div');
			noneDiv.className = 'matchNone';
			// textContent guarantees `title` is rendered as literal text.
			noneDiv.textContent = `✗ No rule matches "${title}"`;
			nodes.push(noneDiv);
		}

		els.debugResult.replaceChildren(...nodes);
	}

	els.debugTitle.addEventListener('input', runDebugTest);

	// ---- Load + migrate ----
	async function init() {
		const data = await get(STORAGE_KEY);
		const raw = data?.[STORAGE_KEY] ?? null;
		const cfg = raw && Array.isArray(raw.rules) ? normalizeCfg(raw) : DEFAULT_CFG();
		base = raw;
		show(cfg);
		ready = true;
		if (!eq(cfg, raw)) {
			sendWrite({base: raw, next: cfg, seq: editSeq}); // Seed / migration, compare-and-set safe.
		}
	}

	init();
})();
