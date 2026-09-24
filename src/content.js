// Content.js
// ChatGPT Tag Highlighter — performance-first sidebar highlighter + hider + turn pruner + compact overlay.
// Notes:
// - Reads config from storage key: tagHighlighterConfigV1
// - Options page stores ONLY hex colors (#RRGGBB)
// - This script still accepts legacy color names and normalizes them for rendering

(() => {
	'use strict';

	// ---- Config ----
	const STORAGE_KEY = 'tagHighlighterConfigV1';
	// Persisted UI state (multi-select filter selection). Lives in storage.local
	// so frequent pill toggles never compete with sync rate limits, and so that
	// options.js full-config writes can never clobber it.
	const UI_STATE_KEY = 'tagHighlighterUiStateV1';
	const STYLE_ID = 'cth-style';
	const OVERLAY_ID = 'cth-overlay';
	const FILTER_BAR_ID = 'cth-filter-bar';
	const DEBUG = false;

	const log = (...a) => DEBUG && console.log('[CTH]', ...a);
	const warn = (...a) => DEBUG && console.warn('[CTH]', ...a);

	// ---- Extension API detection (avoid page-level window.chrome) ----
	const API
    = (typeof browser !== 'undefined' && browser?.runtime?.id && browser?.storage)
    	? browser
    	: ((typeof chrome !== 'undefined' && chrome?.runtime?.id && chrome?.storage) ? chrome : null);

	if (!API) {
		return;
	}

	const storeSync = API.storage?.sync ?? null;
	const storeLocal = API.storage?.local ?? null;

	if (!storeSync && !storeLocal) {
		return;
	}

	// ---- Promise wrapper for storage.get/set (works for Chrome + Firefox) ----
	function storageGet(store, key) {
		return new Promise(resolve => {
			try {
				const r = store.get(key);
				if (r && typeof r.then === 'function') {
					r.catch(() => resolve({})).then(resolve);
				} else {
					store.get(key, resolve);
				}
			} catch {
				try {
					store.get(key, resolve);
				} catch {
					resolve({});
				}
			}
		});
	}

	function storageSet(store, object) {
		return new Promise(resolve => {
			try {
				const r = store.set(object);
				if (r && typeof r.then === 'function') {
					r.catch(() => resolve()).then(() => resolve());
				} else {
					store.set(object, () => resolve());
				}
			} catch {
				try {
					store.set(object, () => resolve());
				} catch {
					resolve();
				}
			}
		});
	}

	// ---- Colors: legacy -> hex, always normalize for rendering ----
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

	const isHex6 = s => /^#[\da-fA-F]{6}$/.test(String(s || '').trim());
	const isHex3 = s => /^#[\da-fA-F]{3}$/.test(String(s || '').trim());
	const normKey = s => String(s || '').toLowerCase().replaceAll(/[^a-z\d]/g, '');
	const expandHex3 = h => {
		const x = h.slice(1);
		return (`#${x[0]}${x[0]}${x[1]}${x[1]}${x[2]}${x[2]}`).toLowerCase();
	};

	function toHex(value, fallback = '#a7a7a7') {
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
		return LEGACY[k] || fallback;
	}

	function hexToRgba(hex, a) {
		const h = toHex(hex);
		const r = Number.parseInt(h.slice(1, 3), 16) || 0;
		const g = Number.parseInt(h.slice(3, 5), 16) || 0;
		const b = Number.parseInt(h.slice(5, 7), 16) || 0;
		return `rgba(${r},${g},${b},${a})`;
	}

	// ---- Inject CSS once ----
	function injectStyleOnce() {
		if (document.getElementById(STYLE_ID)) {
			return;
		}

		const style = document.createElement('style');
		style.id = STYLE_ID;

		// ChatGPT's native scroll-to-bottom button duplicates the overlay's
		// chevron, so hide it — but ONLY while the overlay is actually shown
		// (html.cth-overlay-active). Otherwise the user would lose the only
		// scroll-to-bottom control. Use exact-match aria-label / data-testid
		// (not substring) to avoid hiding unrelated buttons. Current ChatGPT
		// (Sep 2026) renders an unlabelled aria-hidden button inside a wrapper
		// whose class carries the `data-scroll-from-end` scroll-root variant.
		// Keep the legacy utility-class selector as a last-resort fallback.
		const hideScrollBtnCss = `
html.cth-overlay-active main button[data-testid="scroll-to-bottom-button"],
html.cth-overlay-active main button[aria-label="Scroll to bottom"],
html.cth-overlay-active main button[aria-label="Scroll to the bottom"],
html.cth-overlay-active main [class*="data-scroll-from-end"] > button,
html.cth-overlay-active button.cursor-pointer.absolute.z-30.rounded-full.bg-clip-padding.border.text-token-text-secondary.border-token-border-default.end-1\\/2.translate-x-1\\/2.print\\:hidden {
  display: none !important;
}
`;

		// Right-side turn navigation bar (minimap) — hidden when config says so
		const hideNavBarCss = `
html.cth-hide-navbar div.fixed.end-4.top-1\\/2.-translate-y-1\\/2,
html.cth-hide-navbar div.fixed.end-4.top-1\\/2.-translate-y-1\\/2 > div.flex.w-9.flex-col {
  display: none !important;
}
`;

		// Sidebar highlight + hide styles (bigger highlighted area)
		const sidebarCss = `
/* Hide chats matched by hide=true rules (Alt+H sets cth-reveal-hidden) */
html:not(.cth-reveal-hidden) #history a[data-cth-hidden="1"] { display: none !important; }

/* Base highlighted row */
#history a[data-cth="1"]{
  position: relative !important;
  background: var(--cth-bg, transparent) !important;
  border-radius: 12px !important;
}

/* Left stripe */
#history a[data-cth="1"]::before{
  content:"";
  position:absolute;
  left:0; top:6px; bottom:6px;
  width:4px;
  background: var(--cth-color, #a7a7a7);
  border-radius: 999px;
  pointer-events:none;
}

/* Selected row gets stronger background + thicker stripe.
   Live ChatGPT marks the selected chat with an empty data-active attribute. */
#history a[data-cth="1"][data-active]:not([data-active="false"]),
#history a[data-cth="1"][aria-current="page"]{
  background: var(--cth-bg-strong, var(--cth-bg, transparent)) !important;
}
#history a[data-cth="1"][data-active]:not([data-active="false"])::before,
#history a[data-cth="1"][aria-current="page"]::before{
  width:6px;
}
`;

		// Overlay styles (match your screenshot: dark pill + top color line + arrow on right)
		const overlayCss = `
#${OVERLAY_ID}{
  position: fixed;
  /* Sit above page content but BELOW ChatGPT's popovers/menus
     (model picker, thinking window, etc.) so they aren't occluded. */
  z-index: 30;
  left: 0; top: 0;
  display: none;
  box-sizing: border-box;

  border-radius: 18px;
  overflow: hidden;

  background: rgba(0,0,0,0.72);
  border: 1px solid rgba(255,255,255,0.10);
  box-shadow: 0 10px 30px rgba(0,0,0,0.40);

  user-select: none;
  -webkit-user-select: none;
  cursor: pointer;

  transform: translateZ(0);
}

#${OVERLAY_ID} .cth-topline{
  height: 4px;
  background: var(--cth-color, #a7a7a7);
}

#${OVERLAY_ID} .cth-body{
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
}

#${OVERLAY_ID} .cth-title{
  flex: 1;
  min-width: 0;
  font: 600 14px/1.2 system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  color: rgba(255,255,255,0.92);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

#${OVERLAY_ID} .cth-arrow{
  width: 28px;
  height: 28px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(255,255,255,0.14);
  background: rgba(255,255,255,0.06);
  color: rgba(255,255,255,0.90);
  flex: 0 0 auto;
  cursor: pointer;
  pointer-events: auto;
}

#${OVERLAY_ID} .cth-arrow * {
  pointer-events: none;
}

#${OVERLAY_ID}:hover{
  border-color: rgba(255,255,255,0.18);
}
#${OVERLAY_ID}:hover .cth-arrow{
  background: rgba(255,255,255,0.10);
}
`;

		const themeCss = `
/* Light mode overlay */
html.cth-light #${OVERLAY_ID} {
  background: rgba(255,255,255,0.85);
  border-color: rgba(0,0,0,0.10);
  box-shadow: 0 10px 30px rgba(0,0,0,0.12);
}
html.cth-light #${OVERLAY_ID} .cth-title {
  color: rgba(0,0,0,0.88);
}
html.cth-light #${OVERLAY_ID} .cth-arrow {
  border-color: rgba(0,0,0,0.10);
  background: rgba(0,0,0,0.04);
  color: rgba(0,0,0,0.70);
}
html.cth-light #${OVERLAY_ID}:hover {
  border-color: rgba(0,0,0,0.18);
}
html.cth-light #${OVERLAY_ID}:hover .cth-arrow {
  background: rgba(0,0,0,0.08);
}

/* Light mode sidebar highlights */
html.cth-light #history a[data-cth="1"] {
  background: var(--cth-bg-light, var(--cth-bg, transparent)) !important;
}
html.cth-light #history a[data-cth="1"][data-active]:not([data-active="false"]),
html.cth-light #history a[data-cth="1"][aria-current="page"] {
  background: var(--cth-bg-strong-light, var(--cth-bg-strong, transparent)) !important;
}
`;

		const filterBarCss = `
#${FILTER_BAR_ID} {
  display: none;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}

html.cth-light #${FILTER_BAR_ID} {
  border-bottom-color: rgba(0,0,0,0.08);
}

#${FILTER_BAR_ID}.cth-visible {
  display: flex;
}

.cth-pill {
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(255,255,255,0.06);
  color: rgba(255,255,255,0.80);
  user-select: none;
  -webkit-user-select: none;
  transition: background 0.15s, border-color 0.15s;
}

html.cth-light .cth-pill {
  border-color: rgba(0,0,0,0.10);
  background: rgba(0,0,0,0.04);
  color: rgba(0,0,0,0.70);
}

.cth-pill:hover {
  background: rgba(255,255,255,0.10);
}

html.cth-light .cth-pill:hover {
  background: rgba(0,0,0,0.08);
}

.cth-pill.active {
  border-color: var(--pill-color, rgba(255,255,255,0.30));
  background: var(--pill-bg, rgba(255,255,255,0.14));
  color: #fff;
}

html.cth-light .cth-pill.active {
  color: #000;
}
`;

		const dimCss = `
html.cth-dim-untagged #history a[data-sidebar-item="true"]:not([data-cth="1"]) {
  opacity: 0.45;
}
`;

		// Long chats: let the browser skip rendering off-screen older turns.
		// The measured height is the placeholder, so the scrollbar stays put.
		const lazyCss = `
html.cth-lazy-turns [data-cth-lazy="1"] {
  content-visibility: auto;
  contain-intrinsic-block-size: auto var(--cth-turn-h, 300px);
}
`;

		style.textContent = `${hideScrollBtnCss}\n${hideNavBarCss}\n${sidebarCss}\n${overlayCss}\n${themeCss}\n${filterBarCss}\n${dimCss}\n${lazyCss}`;
		document.documentElement.append(style);
		log('Style injected');
	}

	// ---- Theme detection ----
	function detectTheme() {
		return document.documentElement.classList.contains('light') ? 'light' : 'dark';
	}

	function applyThemeClass() {
		const isLight = detectTheme() === 'light';
		document.documentElement.classList.toggle('cth-light', isLight);
	}

	const themeObserver = new MutationObserver(() => {
		applyThemeClass();
	});
	themeObserver.observe(document.documentElement, {
		attributes: true,
		attributeFilter: ['class'],
	});

	// ---- Overlay (one element) ----
	function ensureOverlay() {
		let element = document.getElementById(OVERLAY_ID);
		if (element) {
			return element;
		}

		element = document.createElement('div');
		element.id = OVERLAY_ID;
		element.innerHTML = `
      <div class="cth-topline"></div>
      <div class="cth-body">
        <div class="cth-title"></div>
        <div class="cth-arrow" aria-hidden="true">
          <!-- Inline SVG chevron-down (no network, no extra files) -->
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
               xmlns="http://www.w3.org/2000/svg" style="display:block">
            <path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2.4"
                  stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
      </div>
    `;
		document.body.append(element);

		// Click overlay (or arrow) => scroll to bottom.
		// Bind both on the container and the arrow so the chevron is reliably
		// clickable even when other handlers swallow bubbled events.
		const onScrollClick = e => {
			e.preventDefault();
			e.stopPropagation();
			log('Overlay click -> scrollToBottom');
			scrollToBottom();
		};

		// Pressing the overlay must not blur the composer (keeps typing flow
		// and avoids a focus change interrupting the scroll).
		element.addEventListener('mousedown', e => e.preventDefault());
		element.addEventListener('click', onScrollClick);
		const arrow = element.querySelector('.cth-arrow');
		if (arrow) {
			arrow.addEventListener('click', onScrollClick);
		}

		log('Overlay created');
		return element;
	}

	// ---- Find active conversation title in sidebar ----
	function getActiveChatAnchor(historyRoot) {
		// ChatGPT marks the selected chat with data-active (an empty string on
		// current builds); aria-current covers others. A literal "false" value
		// is not a selection.
		return (
			historyRoot?.querySelector('a[data-sidebar-item="true"][data-active]:not([data-active="false"])')
			|| historyRoot?.querySelector('a[data-sidebar-item="true"][aria-current="page"]')
			|| null
		);
	}

	function getChatTitleText(a) {
		// Keep selector cheap and resilient.
		// Typical: a > ... > .truncate > span[dir="auto"]
		const span = a.querySelector('.truncate span[dir="auto"]');
		if (span && span.textContent) {
			return span.textContent.trim();
		}

		const t = a.querySelector('.truncate');
		return (t?.textContent || '').trim();
	}

	// ---- Rules ----
	function compileConfig(rawCfg) {
		const cfg = rawCfg && typeof rawCfg === 'object' ? rawCfg : null;
		const rulesIn = Array.isArray(cfg?.rules) ? cfg.rules : [];
		const rules = [];

		for (const element of rulesIn) {
			const r = element || {};
			const tag = String(r.tag || '').trim();
			if (!tag) {
				continue;
			}

			const match = String(r.match || '').toLowerCase() === 'includes' ? 'includes' : 'startsWith';
			const color = toHex(r.color, '#a7a7a7');
			const hide = r.hide === true;
			const overlay = r.overlay !== false;

			rules.push({
				tag, match, color, hide, overlay,
			});
		}

		const maxChatTurns = Number.isFinite(Number(cfg?.maxChatTurns))
			? Math.max(0, Math.floor(Number(cfg.maxChatTurns)))
			: 0;

		const hideNavBar = cfg?.hideNavBar !== false; // default true
		const dimUntagged = cfg?.dimUntagged === true;
		const showBadge = cfg?.showBadge !== false; // default true
		const lazyRenderTurns = cfg?.lazyRenderTurns !== false; // default true

		// Toggle CSS class for nav bar visibility
		document.documentElement.classList.toggle('cth-hide-navbar', hideNavBar);
		document.documentElement.classList.toggle('cth-dim-untagged', dimUntagged);

		document.documentElement.classList.toggle('cth-lazy-turns', lazyRenderTurns);

		return {rules, maxChatTurns, hideNavBar, dimUntagged, showBadge, lazyRenderTurns};
	}

	function matchRule(title, rules) {
		// Fast path: small rule count, linear scan, order matters.
		for (const r of rules) {
			if (r.match === 'startsWith') {
				if (title.startsWith(r.tag)) {
					return r;
				}
			} else if (title.includes(r.tag)) {
				return r;
			}
		}

		return null;
	}

	// ---- Filter bar ----
	let activeFilters = new Set();

	// ---- Persistence of multi-select filter selection ----
	// `bootReady` gates the live storage.onChanged handler so we don't apply UI
	// state changes that arrive before main() has finished loading config.
	// Any UI state change observed before boot is stashed here and replayed once.
	let bootReady = false;
	let pendingUiState; // undefined = nothing stashed
	let saveFiltersTimer = null;
	const SAVE_DEBOUNCE_MS = 400;

	function getVisibleRules() {
		return compiled ? compiled.rules.filter(r => !r.hide) : [];
	}

	// Returns true iff the new Set differs in size or contents.
	function setActiveFiltersTo(nextSet) {
		if (nextSet.size === activeFilters.size && [...nextSet].every(t => activeFilters.has(t))) {
			return false;
		}
		activeFilters = nextSet;
		return true;
	}

	// Builds a pruned-and-clamped Set from input tags:
	//   - drop any tag not in the current visible-rule set (stale-tag cleanup)
	//   - if fewer than 2 visible rules exist, the filter bar is hidden, so we
	//     force-clear (otherwise users could be stuck with an active filter and
	//     no UI to clear it).
	function buildPrunedFilterSet(inputTags) {
		const visible = getVisibleRules();
		if (visible.length < 2) return new Set();
		const visSet = new Set(visible.map(r => r.tag));
		return new Set((inputTags || []).filter(t => visSet.has(t)));
	}

	function scheduleSaveActiveFilters() {
		if (saveFiltersTimer) clearTimeout(saveFiltersTimer);
		saveFiltersTimer = setTimeout(flushSaveActiveFilters, SAVE_DEBOUNCE_MS);
	}

	function flushSaveActiveFilters() {
		if (saveFiltersTimer) {
			clearTimeout(saveFiltersTimer);
			saveFiltersTimer = null;
		}

		if (!storeLocal) return;

		const tags = [...activeFilters];
		try {
			storageSet(storeLocal, {[UI_STATE_KEY]: {activeFilters: tags}});
		} catch {}
	}

	// Re-prune existing activeFilters against the current rule set. Persists
	// the cleaned-up value if anything was dropped. Used after rule edits.
	function pruneActiveFiltersAndPersistIfChanged() {
		const next = buildPrunedFilterSet([...activeFilters]);
		if (setActiveFiltersTo(next)) {
			scheduleSaveActiveFilters();
		}
	}

	// Apply a UI-state change (from boot replay or live storage event).
	function applyPersistedUiState(newValue) {
		const tags = (newValue && Array.isArray(newValue.activeFilters)) ? newValue.activeFilters : [];
		const next = buildPrunedFilterSet(tags);
		if (setActiveFiltersTo(next)) {
			renderFilterBar();
			applyFilter();
		}
	}

	// Flush any pending debounced save when the page is being unloaded so a
	// click + immediate refresh can't lose the selection.
	const flushOnHide = () => {
		if (saveFiltersTimer) flushSaveActiveFilters();
	};
	window.addEventListener('pagehide', flushOnHide, {capture: true});
	document.addEventListener('visibilitychange', () => {
		if (document.visibilityState === 'hidden') flushOnHide();
	}, {capture: true});

	function ensureFilterBar() {
		let bar = document.getElementById(FILTER_BAR_ID);
		if (bar) return bar;
		bar = document.createElement('div');
		bar.id = FILTER_BAR_ID;
		bar.setAttribute('role', 'group');
		bar.setAttribute('aria-label', 'Filter chats by tag');
		// Pills are spans, so make Enter/Space activate them like buttons.
		bar.addEventListener('keydown', e => {
			if ((e.key === 'Enter' || e.key === ' ') && e.target.classList?.contains('cth-pill')) {
				e.preventDefault();
				e.stopPropagation();
				e.target.click();
			}
		});
		return bar;
	}

	function renderFilterBar() {
		const visibleRules = compiled ? compiled.rules.filter(r => !r.hide) : [];
		if (visibleRules.length < 2) {
			const bar = document.getElementById(FILTER_BAR_ID);
			if (bar) bar.classList.remove('cth-visible');
			return;
		}

		const bar = ensureFilterBar();

		if (historyRoot && bar.parentElement !== historyRoot) {
			historyRoot.prepend(bar);
		}

		// Re-rendering replaces the pills; keep keyboard focus on the same one.
		const focusedIndex = [...bar.children].indexOf(document.activeElement);
		bar.innerHTML = '';

		const allPill = document.createElement('span');
		allPill.className = 'cth-pill' + (activeFilters.size === 0 ? ' active' : '');
		allPill.textContent = 'All';
		allPill.tabIndex = 0;
		allPill.setAttribute('role', 'button');
		allPill.setAttribute('aria-pressed', String(activeFilters.size === 0));
		allPill.addEventListener('click', () => {
			activeFilters.clear();
			renderFilterBar();
			applyFilter();
			scheduleSaveActiveFilters();
		});
		bar.append(allPill);

		for (const r of visibleRules) {
			const pill = document.createElement('span');
			pill.className = 'cth-pill' + (activeFilters.has(r.tag) ? ' active' : '');
			pill.textContent = r.tag;
			pill.tabIndex = 0;
			pill.setAttribute('role', 'button');
			pill.setAttribute('aria-pressed', String(activeFilters.has(r.tag)));
			pill.style.setProperty('--pill-color', r.color);
			pill.style.setProperty('--pill-bg', hexToRgba(r.color, 0.18));
			if (activeFilters.has(r.tag)) {
				pill.style.borderColor = r.color;
				pill.style.background = hexToRgba(r.color, 0.18);
			}
			pill.addEventListener('click', () => {
				if (activeFilters.has(r.tag)) {
					activeFilters.delete(r.tag);
				} else {
					activeFilters.add(r.tag);
				}
				renderFilterBar();
				applyFilter();
				scheduleSaveActiveFilters();
			});
			bar.append(pill);
		}

		if (focusedIndex >= 0) {
			bar.children[focusedIndex]?.focus();
		}

		bar.classList.add('cth-visible');
	}

	function applyFilter() {
		if (!historyRoot) return;

		const anchors = historyRoot.querySelectorAll('a[data-sidebar-item="true"]');
		for (const a of anchors) {
			if (activeFilters.size === 0) {
				// Rule-hidden chats are hidden by CSS so Alt+H can reveal them.
				a.style.removeProperty('display');
			} else {
				const title = getChatTitleText(a);
				const r = matchRule(title, compiled.rules);
				if (r && activeFilters.has(r.tag) && !r.hide) {
					a.style.removeProperty('display');
				} else {
					a.style.display = 'none';
				}
			}
		}
	}

	// ---- Sidebar processing (batched) ----
	let historyRoot = null;
	let compiled = null;

	let itemCache = new WeakMap();
	let sidebarRAF = 0;

	function scheduleSidebarScan() {
		if (sidebarRAF) {
			return;
		}

		sidebarRAF = requestAnimationFrame(() => {
			sidebarRAF = 0;
			scanSidebarNow();
		});
	}

	function scanSidebarNow() {
		if (!historyRoot || !compiled?.rules?.length) {
			return;
		}

		const anchors = historyRoot.querySelectorAll('a[data-sidebar-item="true"]');
		for (const a of anchors) {
			const title = getChatTitleText(a);
			const last = itemCache.get(a);

			// Skip unchanged items
			if (last === title) {
				continue;
			}

			itemCache.set(a, title);

			applyRuleToAnchor(a, title);
		}

		if (activeFilters.size > 0) {
			applyFilter();
		}

		// Update overlay content whenever sidebar is scanned (cheap)
		scheduleOverlayUpdate();
		updateBadgeCount();
	}

	function updateBadgeCount() {
		if (!compiled?.showBadge) {
			try { API.runtime.sendMessage({ type: 'badgeCount', count: 0 }); } catch {}
			return;
		}

		if (!historyRoot) return;

		const tagged = historyRoot.querySelectorAll(
			'a[data-sidebar-item="true"][data-cth="1"]:not([data-cth-hidden="1"])'
		);
		const count = tagged.length;

		try {
			API.runtime.sendMessage({ type: 'badgeCount', count });
		} catch {
			// Extension context may be invalidated
		}
	}

	function applyRuleToAnchor(a, title) {
		const r = matchRule(title, compiled.rules);

		if (!r) {
			delete a.dataset.cth;
			delete a.dataset.cthHidden;
			a.style.removeProperty('--cth-color');
			a.style.removeProperty('--cth-bg');
			a.style.removeProperty('--cth-bg-strong');
			return;
		}

		a.dataset.cth = '1';
		a.style.setProperty('--cth-color', r.color);
		a.style.setProperty('--cth-bg', hexToRgba(r.color, 0.12));
		a.style.setProperty('--cth-bg-strong', hexToRgba(r.color, 0.18));
		a.style.setProperty('--cth-bg-light', hexToRgba(r.color, 0.10));
		a.style.setProperty('--cth-bg-strong-light', hexToRgba(r.color, 0.14));

		if (r.hide) {
			a.dataset.cthHidden = '1';
		} else {
			delete a.dataset.cthHidden;
		}
	}

	// ---- Overlay update + positioning (batched) ----
	const overlay = ensureOverlay();
	let overlayTitle = '';
	let overlayColor = '#a7a7a7';

	let overlayUpdateRAF = 0;
	function scheduleOverlayUpdate() {
		if (overlayUpdateRAF) {
			return;
		}

		overlayUpdateRAF = requestAnimationFrame(() => {
			overlayUpdateRAF = 0;
			updateOverlayNow();
			scheduleOverlayLayout();
		});
	}

	// overlayWanted: the active chat matches an overlay rule.
	// Whether the overlay is actually shown also depends on finding a
	// measurable composer box (layoutOverlayNow), so the two are tracked
	// separately and the overlay recovers when the composer re-mounts.
	let overlayWanted = false;

	function setOverlayShown(shown) {
		overlay.style.display = shown ? 'block' : 'none';
		// Native scroll-to-bottom is only hidden while the overlay replaces it.
		document.documentElement.classList.toggle('cth-overlay-active', shown);
	}

	function hideOverlay() {
		if (!overlayWanted && overlay.style.display === 'none') {
			return;
		}

		overlayWanted = false;
		overlayTitle = '';
		overlayColor = '#a7a7a7';
		setOverlayShown(false);
	}

	function updateOverlayNow() {
		if (!historyRoot || !compiled?.rules?.length) {
			hideOverlay();
			return;
		}

		const active = getActiveChatAnchor(historyRoot);
		if (!active) {
			hideOverlay();
			return;
		}

		const title = getChatTitleText(active);
		const r = matchRule(title, compiled.rules);

		if (!r || r.overlay === false) {
			hideOverlay();
			return;
		}

		overlayWanted = true;

		const nextTitle = title || '';
		const nextColor = r.color;

		if (nextTitle === overlayTitle && nextColor === overlayColor) {
			return;
		}

		overlayTitle = nextTitle;
		overlayColor = nextColor;

		overlay.style.setProperty('--cth-color', overlayColor);
		const titleElement = overlay.querySelector('.cth-title');
		if (titleElement) {
			titleElement.textContent = overlayTitle;
		}
	}

	function findComposerBox() {
		// Most stable anchor: #prompt-textarea, then its composer container.
		// Current ChatGPT: form[data-type="unified-composer"].
		// Older builds: div.bg-token-bg-primary.
		const pt = document.querySelector('#prompt-textarea');
		if (!pt) {
			return null;
		}

		return pt.closest('form[data-type="unified-composer"]')
			|| pt.closest('div.bg-token-bg-primary')
			|| pt.closest('form')
			|| null;
	}

	let overlayLayoutRAF = 0;
	function scheduleOverlayLayout() {
		if (overlayLayoutRAF) {
			return;
		}

		overlayLayoutRAF = requestAnimationFrame(() => {
			overlayLayoutRAF = 0;
			layoutOverlayNow();
		});
	}

	function layoutOverlayNow() {
		if (!overlayWanted) {
			setOverlayShown(false);
			return;
		}

		const box = findComposerBox();
		const r = box?.getBoundingClientRect();
		if (!r || r.width === 0 || r.height === 0) {
			setOverlayShown(false);
			return;
		}

		setOverlayShown(true);

		// Set width/left first (so height is correct after wrap)
		overlay.style.left = `${Math.round(r.left)}px`;
		overlay.style.width = `${Math.round(r.width)}px`;

		// Measure overlay height AFTER width is applied
		const h = overlay.getBoundingClientRect().height;

		// 0px gap: overlay bottom == composer box top
		overlay.style.top = `${Math.round(r.top - h)}px`;
	}

	// Keep overlay aligned on scroll/resize (batched)
	window.addEventListener('scroll', scheduleOverlayLayout, {passive: true});
	window.addEventListener('resize', scheduleOverlayLayout, {passive: true});

	// ---- Detect SPA navigation (New Chat, switching chats) ----
	let lastUrl = location.href;
	function checkUrlChange() {
		if (location.href !== lastUrl) {
			lastUrl = location.href;
			log('SPA navigation detected', lastUrl);
			scheduleSidebarScan();
			scheduleOverlayUpdate();
		}
	}

	// Patch pushState/replaceState so we catch programmatic navigations
	for (const method of ['pushState', 'replaceState']) {
		const orig = history[method];
		history[method] = function (...args) {
			const result = orig.apply(this, args);
			checkUrlChange();
			return result;
		};
	}

	window.addEventListener('popstate', checkUrlChange);

	// ---- Scroll-to-bottom action ----
	let scrollContainer = null;

	// Conversation turns keep data-testid="conversation-turn-N" across builds,
	// but the element changed (older builds: <article>, current: <section>).
	// Match on the attribute only, and ignore look-alikes such as
	// "copy-turn-action-button".
	const TURN_TESTID_RE = /^conversation-turn-\d+$/;

	function getTurnElements() {
		return [...document.querySelectorAll('[data-testid^="conversation-turn-"]')]
			.filter(element => TURN_TESTID_RE.test(element.dataset.testid || ''));
	}

	function isScrollable(node) {
		const oy = getComputedStyle(node).overflowY;
		return (oy === 'auto' || oy === 'scroll') && node.scrollHeight > node.clientHeight + 20;
	}

	function getScrollContainer() {
		if (scrollContainer && document.contains(scrollContainer)) {
			return scrollContainer;
		}

		// Heuristic 1: start from a conversation turn and walk up (past <main>
		// if needed — current builds scroll an ancestor above it).
		const turn = getTurnElements()[0];
		let node = turn ? turn.parentElement : null;

		while (node && node !== document.body) {
			if (isScrollable(node)) {
				scrollContainer = node;
				return node;
			}

			node = node.parentElement;
		}

		// Heuristic 2: <main> itself, but only when it actually scrolls.
		const main = document.querySelector('main');
		if (main && isScrollable(main)) {
			scrollContainer = main;
			return main;
		}

		// Heuristic 3: any element flagged as overflow-y-auto containing a turn.
		const candidates = document.querySelectorAll('[class*="overflow-y-auto"], [class*="overflow-auto"]');
		for (const c of candidates) {
			if (isScrollable(c) && turn && c.contains(turn)) {
				scrollContainer = c;
				return c;
			}
		}

		scrollContainer = null;
		return null;
	}

	// Smooth scrolls can be aborted by the page (live ChatGPT sometimes stops
	// them a few px in). Watch the scroll for a short while and jump the rest
	// of the way if it stalls — unless the user scrolled or typed meanwhile.
	let scrollWatch = null;

	function stopScrollWatch() {
		if (!scrollWatch) {
			return;
		}

		cancelAnimationFrame(scrollWatch.raf);
		for (const type of ['wheel', 'touchmove', 'keydown', 'pointerdown']) {
			scrollWatch.target.removeEventListener(type, scrollWatch.onUser, true);
		}

		scrollWatch = null;
	}

	function scrollToBottom() {
		stopScrollWatch();
		const sc = getScrollContainer() || document.scrollingElement || document.documentElement;
		const atBottom = () => sc.scrollTop + sc.clientHeight >= sc.scrollHeight - 2;
		sc.scrollTo({top: sc.scrollHeight, behavior: 'smooth'});

		const watch = {target: window, raf: 0, last: sc.scrollTop, still: 0, deadline: performance.now() + 1500};
		watch.onUser = () => stopScrollWatch();
		for (const type of ['wheel', 'touchmove', 'keydown', 'pointerdown']) {
			window.addEventListener(type, watch.onUser, {capture: true, passive: true});
		}

		const tick = now => {
			if (scrollWatch !== watch) {
				return;
			}

			if (atBottom()) {
				stopScrollWatch();
				return;
			}

			const moved = Math.abs(sc.scrollTop - watch.last) > 0.5;
			watch.last = sc.scrollTop;
			watch.still = moved ? 0 : watch.still + 1;
			// Stalled for a few frames, or out of time: finish instantly.
			if (watch.still >= 4 || now > watch.deadline) {
				stopScrollWatch();
				sc.scrollTop = sc.scrollHeight;
				return;
			}

			watch.raf = requestAnimationFrame(tick);
		};

		scrollWatch = watch;
		watch.raf = requestAnimationFrame(tick);
	}

	// ---- Long conversations: pruning (maxChatTurns) + lazy rendering ----
	// Lazy rendering marks older turns with content-visibility:auto so the
	// browser skips style/layout/paint for off-screen messages. Nothing is
	// removed, so scrolling, Find and selection keep working. Each turn's
	// measured height is its placeholder size, so the scrollbar doesn't jump.
	const LAZY_MIN_TURNS = 20;
	const LAZY_KEEP_RECENT = 4;
	let turnWorkRAF = 0;

	function turnWorkNeeded() {
		return Boolean(compiled?.maxChatTurns) || compiled?.lazyRenderTurns === true;
	}

	function scheduleTurnWork() {
		if (turnWorkRAF || !turnWorkNeeded()) {
			return;
		}

		turnWorkRAF = requestAnimationFrame(() => {
			turnWorkRAF = 0;
			pruneTurnsNow();
			updateLazyTurnsNow();
		});
	}

	function clearLazyTurns() {
		for (const t of document.querySelectorAll('[data-cth-lazy="1"]')) {
			delete t.dataset.cthLazy;
			t.style.removeProperty('--cth-turn-h');
		}
	}

	function updateLazyTurnsNow() {
		if (compiled?.lazyRenderTurns !== true) {
			return;
		}

		const turns = getTurnElements();
		const cutoff = turns.length >= LAZY_MIN_TURNS ? turns.length - LAZY_KEEP_RECENT : 0;

		// Recent turns (or short chats) always render normally.
		for (let i = cutoff; i < turns.length; i++) {
			if (turns[i].dataset.cthLazy === '1') {
				delete turns[i].dataset.cthLazy;
				turns[i].style.removeProperty('--cth-turn-h');
			}
		}

		// Read all heights first, then write, to avoid layout thrashing.
		const pending = [];
		for (let i = 0; i < cutoff; i++) {
			if (turns[i].dataset.cthLazy !== '1') {
				pending.push(turns[i]);
			}
		}

		const heights = pending.map(t => Math.round(t.getBoundingClientRect().height));
		for (const [i, t] of pending.entries()) {
			if (heights[i] > 0) {
				t.style.setProperty('--cth-turn-h', `${heights[i]}px`);
			}

			t.dataset.cthLazy = '1';
		}
	}

	function syncTurnObserver() {
		turnObserver.disconnect();
		if (compiled?.lazyRenderTurns !== true) {
			clearLazyTurns();
		}

		if (turnWorkNeeded()) {
			turnObserver.observe(document.documentElement, {childList: true, subtree: true});
			scheduleTurnWork();
		}
	}

	function pruneTurnsNow() {
		const keep = compiled?.maxChatTurns | 0;
		if (!keep) {
			return;
		}

		const turns = getTurnElements();
		const extra = turns.length - keep;
		if (extra <= 0) {
			return;
		}

		// Remove oldest turns first
		for (let i = 0; i < extra; i++) {
			turns[i]?.remove();
		}

		log(`Pruned turns: kept=${keep}, removed=${extra}`);
	}

	// Observe DOM for new turns (fast: one observer + rAF batch)
	const turnObserver = new MutationObserver(() => scheduleTurnWork());

	// ---- History observer ----
	let historyObserver = null;

	function attachHistoryObserver() {
		if (!historyRoot) {
			return;
		}

		if (historyObserver) {
			historyObserver.disconnect();
		}

		historyObserver = new MutationObserver(() => {
			scheduleSidebarScan();
			scheduleOverlayUpdate();
		});

		historyObserver.observe(historyRoot, {
			childList: true,
			subtree: true,
			// In-place title renames change a text node, not the child list.
			characterData: true,
			attributes: true,
			attributeFilter: ['data-active', 'aria-current', 'class'],
		});
	}

	// ---- Sidebar root binding ----
	// (Re)binds #history. ChatGPT can mount it late, replace it on SPA
	// navigation, or unmount it (collapsed sidebar). Safe to call repeatedly.
	function bindHistoryRoot() {
		const hr = document.querySelector('#history');
		if (hr && hr !== historyRoot) {
			historyRoot = hr;
			attachHistoryObserver();
			scheduleSidebarScan();
			scheduleOverlayUpdate();
			renderFilterBar();
		} else if (!hr && historyRoot && !historyRoot.isConnected) {
			// Drop the stale root so the overlay doesn't describe a detached list.
			historyObserver?.disconnect();
			historyRoot = null;
			scheduleOverlayUpdate();
		}
	}

	let rootObserver = null;
	function startRootObserver() {
		if (rootObserver) {
			return;
		}

		rootObserver = new MutationObserver(() => {
			bindHistoryRoot();
			scheduleOverlayLayout();
		});
		rootObserver.observe(document.documentElement, {childList: true, subtree: true});
	}

	// ---- Boot ----
	async function main() {
		log('content.js loaded', {href: location.href, ua: navigator.userAgent});

		injectStyleOnce();
		applyThemeClass();
		ensureOverlay();

		// Load config (try sync first; fallback to local)
		const fromSync = storeSync ? await storageGet(storeSync, STORAGE_KEY) : {};
		const fromLocal = (!fromSync?.[STORAGE_KEY] && storeLocal) ? await storageGet(storeLocal, STORAGE_KEY) : {};

		const cfg = (fromSync?.[STORAGE_KEY] || fromLocal?.[STORAGE_KEY]) || null;

		const keys = Object.keys(fromSync || {}).concat(Object.keys(fromLocal || {}));
		log('storage.get() returned keys:', keys);

		if (!cfg) {
			log('No settings found. Early return by design.');
			bootReady = true;
			return;
		}

		compiled = compileConfig(cfg);
		log('Config loaded', compiled);

		if (compiled.rules.length === 0) {
			log('No rules in config. Early return by design.');
			bootReady = true;
			return;
		}

		// ---- Hydrate persisted filter selection (UI state) ----
		// Read from storage.local; prune stale tags; clamp to empty when filter
		// bar would be hidden. If pruning dropped tags, write back the clean set.
		if (storeLocal) {
			try {
				const uiData = await storageGet(storeLocal, UI_STATE_KEY);
				const persisted = uiData?.[UI_STATE_KEY];
				const persistedTags = Array.isArray(persisted?.activeFilters) ? persisted.activeFilters : [];
				const pruned = buildPrunedFilterSet(persistedTags);
				activeFilters = pruned;
				if (pruned.size !== persistedTags.length) {
					scheduleSaveActiveFilters();
				}
			} catch (e) {
				warn('Failed to load persisted filter state', e);
			}
		}

		bootReady = true;
		// Replay the most-recent UI state event that arrived during boot.
		if (pendingUiState !== undefined) {
			const stashed = pendingUiState;
			pendingUiState = undefined;
			applyPersistedUiState(stashed);
		}

		// Find the sidebar chat list; it may also mount later (root observer).
		bindHistoryRoot();
		if (!historyRoot) {
			warn('Sidebar history root not found (#history).');
		}

		// Overlay alignment now
		scheduleOverlayLayout();

		// Long-conversation work (pruning + lazy rendering)
		syncTurnObserver();

		// If SPA navigation recreates #history, rebind cheaply.
		startRootObserver();
	}

	// ---- Live-reload config when options page saves changes ----
	function listenForConfigChanges() {
		const handler = (changes, areaName) => {
			if (changes[STORAGE_KEY]) {
				const newCfg = changes[STORAGE_KEY].newValue;
				if (newCfg) {
					log('storage.onChanged fired — reloading config', {areaName});
					compiled = compileConfig(newCfg);
					itemCache = new WeakMap();
					// Preserve the user's filter selection across rule edits.
					// Prune stale tags and clamp to empty if fewer than 2 visible rules remain.
					pruneActiveFiltersAndPersistIfChanged();
					renderFilterBar();

					// Settings can arrive after boot (first install): bind now.
					bindHistoryRoot();
					startRootObserver();

					if (historyRoot) {
						scheduleSidebarScan();
						scheduleOverlayUpdate();
						updateBadgeCount();
					}

					scheduleOverlayLayout();

					syncTurnObserver();
				}
			}

			if (changes[UI_STATE_KEY]) {
				const newVal = changes[UI_STATE_KEY].newValue || null;
				if (!bootReady) {
					// Boot hasn't loaded compiled config yet; stash latest and replay later.
					pendingUiState = newVal;
					return;
				}

				applyPersistedUiState(newVal);
			}
		};

		API.storage.onChanged.addListener(handler);
	}

	// ---- Keyboard shortcuts ----
	// Match the physical key: on macOS, Option+H yields e.key "˙", not "h".
	const isAltKey = (e, letter) => e.altKey
		&& (e.code === `Key${letter.toUpperCase()}` || String(e.key || '').toLowerCase() === letter);

	document.addEventListener('keydown', e => {
		// Alt+H: Toggle visibility of chats hidden by hide=true rules.
		// Active tag filters still apply on top of this.
		if (isAltKey(e, 'h')) {
			e.preventDefault();
			document.documentElement.classList.toggle('cth-reveal-hidden');
			return;
		}

		// Alt+F: Focus filter bar
		if (isAltKey(e, 'f')) {
			e.preventDefault();
			const bar = document.getElementById(FILTER_BAR_ID);
			if (bar && bar.classList.contains('cth-visible')) {
				const firstPill = bar.querySelector('.cth-pill');
				if (firstPill) firstPill.focus();
			}
		}
	});

	main();
	listenForConfigChanges();
})();
