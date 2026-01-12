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
	const STYLE_ID = 'cth-style';
	const OVERLAY_ID = 'cth-overlay';
	const DEBUG = true; // Flip to false when stable

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

		// The scroll-to-bottom floating button you asked to hide
		// (Selector uses multiple stable utility classes; keep minimal)
		const hideScrollBtnCss = `
button.cursor-pointer.absolute.z-30.rounded-full.bg-clip-padding.border.text-token-text-secondary.border-token-border-default.end-1\\/2.translate-x-1\\/2.print\\:hidden {
  display: none !important;
}
`;

		// Sidebar highlight + hide styles (bigger highlighted area)
		const sidebarCss = `
/* Hide chats matched by hide=true rules */
#history a[data-cth-hidden="1"] { display: none !important; }

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

/* Selected row gets stronger background + thicker stripe */
#history a[data-cth="1"][data-active],
#history a[data-cth="1"][aria-current="page"]{
  background: var(--cth-bg-strong, var(--cth-bg, transparent)) !important;
}
#history a[data-cth="1"][data-active]::before,
#history a[data-cth="1"][aria-current="page"]::before{
  width:6px;
}
`;

		// Overlay styles (match your screenshot: dark pill + top color line + arrow on right)
		const overlayCss = `
#${OVERLAY_ID}{
  position: fixed;
  z-index: 2147483647;
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
}

#${OVERLAY_ID}:hover{
  border-color: rgba(255,255,255,0.18);
}
#${OVERLAY_ID}:hover .cth-arrow{
  background: rgba(255,255,255,0.10);
}
`;

		style.textContent = `${hideScrollBtnCss}\n${sidebarCss}\n${overlayCss}`;
		document.documentElement.append(style);
		log('Style injected');
	}

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

		// Click overlay => scroll to bottom
		element.addEventListener('click', () => scrollToBottom(), {passive: true});

		log('Overlay created');
		return element;
	}

	// ---- Find active conversation title in sidebar ----
	function getActiveChatAnchor(historyRoot) {
		// ChatGPT uses data-active in many builds; aria-current covers others.
		return (
			historyRoot?.querySelector('a[data-sidebar-item="true"][data-active]')
			|| historyRoot?.querySelector('a[data-sidebar-item="true"][aria-current="page"]')
			|| historyRoot?.querySelector('a[data-sidebar-item="true"][data-active="true"]')
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

			rules.push({
				tag, match, color, hide,
			});
		}

		const maxChatTurns = Number.isFinite(Number(cfg?.maxChatTurns))
			? Math.max(0, Math.floor(Number(cfg.maxChatTurns)))
			: 0;

		return {rules, maxChatTurns};
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

	// ---- Sidebar processing (batched) ----
	let historyRoot = null;
	let compiled = null;

	const itemCache = new WeakMap(); // A -> lastTitle
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

		// Update overlay content whenever sidebar is scanned (cheap)
		scheduleOverlayUpdate();
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

	function updateOverlayNow() {
		if (!historyRoot || !compiled?.rules?.length) {
			return;
		}

		const active = getActiveChatAnchor(historyRoot);
		if (!active) {
			return;
		}

		const title = getChatTitleText(active);
		const r = matchRule(title, compiled.rules);

		const nextTitle = title || '';
		const nextColor = r?.color || '#a7a7a7';

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

		overlay.style.display = overlayTitle ? 'block' : 'none';
	}

	function findComposerBox() {
		// Most stable anchor: #prompt-textarea then closest background box
		const pt = document.querySelector('#prompt-textarea');
		if (!pt) {
			return null;
		}

		return pt.closest('div.bg-token-bg-primary') || null;
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
		if (overlay.style.display === 'none') {
			return;
		}

		const box = findComposerBox();
		if (!box) {
			overlay.style.display = 'none';
			return;
		}

		const r = box.getBoundingClientRect();

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

	// ---- Scroll-to-bottom action ----
	let scrollContainer = null;

	function getScrollContainer() {
		if (scrollContainer && document.contains(scrollContainer)) {
			return scrollContainer;
		}

		// Heuristic: find a conversation turn, then walk up to a scrollable parent.
		const turn = document.querySelector('article[data-testid^="conversation-turn-"]');
		let node = turn ? turn.parentElement : null;

		while (node && node !== document.body) {
			const s = getComputedStyle(node);
			const oy = s.overflowY;
			if ((oy === 'auto' || oy === 'scroll') && node.scrollHeight > node.clientHeight + 20) {
				scrollContainer = node;
				return node;
			}

			node = node.parentElement;
		}

		scrollContainer = null;
		return null;
	}

	function scrollToBottom() {
		const sc = getScrollContainer();
		if (sc) {
			sc.scrollTo({top: sc.scrollHeight, behavior: 'smooth'});
			return;
		}

		// Fallback
		window.scrollTo({top: document.documentElement.scrollHeight, behavior: 'smooth'});
	}

	// ---- Chat turn pruning (maxChatTurns) ----
	let pruneRAF = 0;

	function schedulePrune() {
		if (!compiled?.maxChatTurns) {
			return;
		}

		if (pruneRAF) {
			return;
		}

		pruneRAF = requestAnimationFrame(() => {
			pruneRAF = 0;
			pruneTurnsNow();
		});
	}

	function pruneTurnsNow() {
		const keep = compiled?.maxChatTurns | 0;
		if (!keep) {
			return;
		}

		const turns = document.querySelectorAll('article[data-testid^="conversation-turn-"]');
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
	const turnObserver = new MutationObserver(() => schedulePrune());

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
			attributes: true,
			attributeFilter: ['data-active', 'aria-current', 'class'],
		});
	}

	// ---- Boot ----
	async function main() {
		log('content.js loaded', {href: location.href, ua: navigator.userAgent});

		injectStyleOnce();
		ensureOverlay();

		// Load config (try sync first; fallback to local)
		const fromSync = storeSync ? await storageGet(storeSync, STORAGE_KEY) : {};
		const fromLocal = (!fromSync?.[STORAGE_KEY] && storeLocal) ? await storageGet(storeLocal, STORAGE_KEY) : {};

		const cfg = (fromSync?.[STORAGE_KEY] || fromLocal?.[STORAGE_KEY]) || null;

		const keys = Object.keys(fromSync || {}).concat(Object.keys(fromLocal || {}));
		log('storage.get() returned keys:', keys);

		if (!cfg) {
			log('No settings found. Early return by design.');
			return;
		}

		compiled = compileConfig(cfg);
		log('Config loaded', compiled);

		if (compiled.rules.length === 0) {
			log('No rules in config. Early return by design.');
			return;
		}

		// Find history root (ChatGPT sidebar chat list)
		historyRoot = document.querySelector('#history');
		if (!historyRoot) {
			// Fallback: sometimes history is lazily mounted
			historyRoot = document.querySelector('#history') || null;
		}

		if (historyRoot) {
			attachHistoryObserver();
			scheduleSidebarScan();
			scheduleOverlayUpdate();
		} else {
			warn('Sidebar history root not found (#history).');
		}

		// Overlay alignment now
		scheduleOverlayLayout();

		// Pruning setup
		if (compiled.maxChatTurns > 0) {
			turnObserver.observe(document.documentElement, {childList: true, subtree: true});
			schedulePrune();
		}

		// If SPA navigation happens, #history can be recreated — rebind cheaply
		const rootObserver = new MutationObserver(() => {
			const hr = document.querySelector('#history');
			if (hr && hr !== historyRoot) {
				historyRoot = hr;
				attachHistoryObserver();
				scheduleSidebarScan();
				scheduleOverlayUpdate();
			}

			scheduleOverlayLayout();
		});
		rootObserver.observe(document.documentElement, {childList: true, subtree: true});
	}

	main();
})();
