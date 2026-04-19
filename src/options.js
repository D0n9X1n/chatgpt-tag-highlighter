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
		reset: $('reset'),
		save: $('save'),
		maxChatTurns: $('maxChatTurns'),
		hideNavBar: $('hideNavBar'),
		dimUntagged: $('dimUntagged'),
		showBadge: $('showBadge'),
		toast: $('toast'),
		exportCfg: $('exportCfg'),
		importCfg: $('importCfg'),
		importPanel: $('importPanel'),
		importText: $('importText'),
		importApply: $('importApply'),
		importCancel: $('importCancel'),
		debugTitle: $('debugTitle'),
		debugResult: $('debugResult'),
		saveHint: $('saveHint'),
	};

	// ---- Dirty state tracking ----
	function markDirty() {
		els.saveHint.style.display = '';
	}

	function markClean() {
		els.saveHint.style.display = 'none';
	}

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

	const set = object =>
		new Promise(resolve => {
			try {
				const r = store.set(object);
				if (r?.then) {
					r.then(resolve);
				} else {
					store.set(object, resolve);
				}
			} catch {
				store.set(object, resolve);
			}
		});

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

	// ---- Toast ----
	let toastTimer = 0;
	function toast(message) {
		els.toast.textContent = message;
		els.toast.classList.add('show');
		clearTimeout(toastTimer);
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
			o.textContent = `${element[0]} (${element[1]})`;
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

		const rules = Array.isArray(cfg.rules) ? cfg.rules : [];
		for (const rule of rules) {
			els.rows.append(createRow(rule));
		}

		updateRowNumbers();
	}

	function updateRowNumbers() {
		const trs = els.rows.querySelectorAll('tr');
		for (let i = 0; i < trs.length; i++) {
			const cell = trs[i].querySelector('.rowNum');
			if (cell) cell.textContent = String(i + 1);
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
				color: toHex(tr.querySelector('.hex').value, '#999999'), // ONLY hex persisted
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
		};
	}

	// ---- Event delegation for best performance ----
	els.rows.addEventListener('change', e => {
		const tr = e.target.closest('tr');
		if (!tr) {
			return;
		}

		markDirty();

		if (e.target.classList.contains('color')) {
			// Preset selected -> update hex + preview
			const hex = e.target.value ? toHex(e.target.value) : toHex(tr.querySelector('.hex').value);
			setRowColor(tr, hex);
			return;
		}

		if (e.target.classList.contains('hex')) {
			// Normalize on change for instant feedback
			setRowColor(tr, e.target.value);
		}
	});

	els.rows.addEventListener('click', e => {
		const tr = e.target.closest('tr');
		if (!tr) {
			return;
		}

		if (e.target.classList.contains('del')) {
			tr.remove();
			updateRowNumbers();
			markDirty();
			return;
		}


	});

	// Normalize hex on blur (covers paste + partial input)
	els.rows.addEventListener('blur', e => {
		if (!e.target.classList.contains('hex')) {
			return;
		}

		const tr = e.target.closest('tr');
		if (!tr) {
			return;
		}

		setRowColor(tr, e.target.value);
	}, true);

	// ---- Buttons ----
	els.addRow.addEventListener('click', () => {
		const tr = createRow({
			tag: '', match: 'startsWith', color: PALETTE[0][1], hide: false, overlay: true,
		});
		els.rows.append(tr);
		updateRowNumbers();
		markDirty();
		tr.querySelector('.tag').focus();
	});

	els.reset.addEventListener('click', async () => {
		const cfg = DEFAULT_CFG();
		await set({[STORAGE_KEY]: cfg});
		render(cfg);
		markClean();
		toast('Reset ✓');
	});

	els.save.addEventListener('click', async () => {
		const cfg = collectConfig();
		if (cfg.rules.length === 0) {
			toast('No rules to save');
			return;
		}

		for (let i = 0; i < cfg.rules.length; i++) {
			cfg.rules[i].color = toHex(cfg.rules[i].color);
		}

		await set({[STORAGE_KEY]: cfg});
		render(cfg);
		markClean();
		toast('Saved ✓');
	});

	// Ctrl/Cmd+S => Save
	globalThis.addEventListener('keydown', e => {
		if ((e.ctrlKey || e.metaKey) && String(e.key || '').toLowerCase() === 's') {
			e.preventDefault();
			els.save.click();
		}
	});

	// ---- General section dirty tracking ----
	els.maxChatTurns.addEventListener('input', markDirty);
	els.hideNavBar.addEventListener('change', markDirty);
	els.dimUntagged.addEventListener('change', markDirty);
	els.showBadge.addEventListener('change', markDirty);

	// Tag input typing also marks dirty
	els.rows.addEventListener('input', e => {
		if (e.target.classList.contains('tag') || e.target.classList.contains('hex')) {
			markDirty();
		}
	});

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

	els.importApply.addEventListener('click', async () => {
		const raw = els.importText.value.trim();
		let parsed;
		try { parsed = JSON.parse(raw); } catch { toast('Invalid config'); return; }
		if (!parsed || !Array.isArray(parsed.rules)) { toast('Invalid config'); return; }

		const cfg = {
			rules: [],
			maxChatTurns: safeInt(parsed.maxChatTurns, 0),
			hideNavBar: parsed.hideNavBar !== false,
			dimUntagged: parsed.dimUntagged === true,
			showBadge: parsed.showBadge !== false,
		};
		for (const r of parsed.rules) {
			const tag = String(r?.tag || '').trim();
			if (!tag) continue;
			cfg.rules.push({
				tag,
				match: safeMatch(r?.match),
				color: toHex(r?.color, '#999999'),
				hide: r?.hide === true,
				overlay: r?.overlay !== false,
			});
		}
		if (cfg.rules.length === 0) { toast('Invalid config'); return; }

		await set({ [STORAGE_KEY]: cfg });
		render(cfg);
		els.importPanel.style.display = 'none';
		els.importText.value = '';
		markClean();
		toast('Imported ✓');
	});

	// ---- Drag-and-drop reorder ----
	let draggedRow = null;

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
		const rect = targetRow.getBoundingClientRect();
		const midY = rect.top + rect.height / 2;
		if (e.clientY < midY) {
			els.rows.insertBefore(draggedRow, targetRow);
		} else {
			els.rows.insertBefore(draggedRow, targetRow.nextElementSibling);
		}
		markDirty();
	});

	els.rows.addEventListener('dragend', () => {
		if (draggedRow) { draggedRow.classList.remove('dragging'); draggedRow = null; }
		for (const tr of els.rows.querySelectorAll('.drag-over')) tr.classList.remove('drag-over');
		updateRowNumbers();
	});

	// ---- Rule tester ----
	function runDebugTest() {
		const title = els.debugTitle.value.trim();
		if (!title) {
			els.debugResult.innerHTML = 'Type a title above to see which rule matches.';
			return;
		}

		const trs = els.rows.querySelectorAll('tr');
		let winnerIdx = -1;
		const lines = [];

		for (let i = 0; i < trs.length; i++) {
			const tag = String(trs[i].querySelector('.tag').value || '').trim();
			if (!tag) continue;
			const match = safeMatch(trs[i].querySelector('.match').value);
			const hit = match === 'startsWith' ? title.startsWith(tag) : title.includes(tag);
			const hex = toHex(trs[i].querySelector('.hex').value);
			const swatch = `<span class="swatch" style="background:${hex};width:12px;height:12px;display:inline-block;border-radius:3px;vertical-align:middle;margin:0 4px"></span>`;

			if (hit && winnerIdx === -1) {
				winnerIdx = i;
				lines.push(`<div class="matchHit">✓ #${i + 1} ${swatch} <code>${tag}</code> (${match}) — <b>WINNER</b></div>`);
			} else if (hit) {
				lines.push(`<div class="matchSkipped">✓ #${i + 1} ${swatch} <code>${tag}</code> (${match}) — matches but skipped (rule #${winnerIdx + 1} won)</div>`);
			} else {
				lines.push(`<div class="matchMiss">✗ #${i + 1} ${swatch} <code>${tag}</code> (${match})</div>`);
			}
		}

		if (winnerIdx === -1) {
			lines.push(`<div class="matchNone">✗ No rule matches "${title}"</div>`);
		}

		els.debugResult.innerHTML = lines.join('');
	}

	els.debugTitle.addEventListener('input', runDebugTest);

	// ---- Load + migrate ----
	async function init() {
		const data = await get(STORAGE_KEY);
		let cfg = data?.[STORAGE_KEY];

		if (!cfg || !Array.isArray(cfg.rules) || cfg.rules.length === 0) {
			cfg = DEFAULT_CFG();
			await set({[STORAGE_KEY]: cfg});
			render(cfg);
			return;
		}

		// Migrate: force all colors to hex and persist back
		const migrated = {
			rules: [],
			maxChatTurns: safeInt(cfg.maxChatTurns, 0),
			hideNavBar: cfg.hideNavBar !== false,
			dimUntagged: cfg.dimUntagged === true,
			showBadge: cfg.showBadge !== false,
		};

		for (let i = 0; i < cfg.rules.length; i++) {
			const r = cfg.rules[i] || {};
			const tag = String(r.tag || '').trim();
			if (!tag) {
				continue;
			}

			migrated.rules.push({
				tag,
				match: safeMatch(r.match),
				color: toHex(r.color, '#999999'),
				hide: r.hide === true,
				overlay: r.overlay !== false,
			});
		}

		await set({[STORAGE_KEY]: migrated});
		render(migrated);
	}

	init();
})();
