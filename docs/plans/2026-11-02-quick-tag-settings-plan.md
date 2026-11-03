# Quick tag + floating settings — Implementation Plan (v1.3.0)

**Goal:** tag a sidebar chat in one click (with Undo), open settings in a floating window, and make `background.js` the only config writer so no edit is lost.
**Architecture:** `background.js` applies every config write on one promise chain: `writeConfig {base, next}` is a compare-and-set (writes only if storage still equals `base`, else returns `conflict` and writes nothing), and `addRule {tag}` appends to the freshest value for content.js; it also gets `openSettings`. `options.js` keeps one save in flight, re-renders on outside changes only when it has no unsaved edits, and otherwise keeps the draft and shows a visible conflict banner with **Reload**. `content.js` gets one body-level tag button, menu and toast, `renameChat` on the existing `pageFetch`/`getAccessToken` path, per-chat serialization, title overrides, and a settings gear.
**Tech stack:** vanilla MV3 JS in IIFEs (no deps); pytest + Playwright against packaged `dist/chrome`; `tests/unit_test.html`.

Spec `docs/specs/2026-11-02-quick-tag-settings-design.md`; UI `docs/specs/2026-11-02-quick-tag-settings-ui-brief.md`. **Conventions:** `BUILD` = `./publish.sh --version 0.0.99 && for f in src/*.js; do node --check "$f"; done`; `RUN 'K'` = `BUILD && CI=true pytest tests/test_extension.py -k 'K' -v`. Each task: add the tests → `RUN` shows the stated FAIL → implement → `RUN` PASSES → commit the listed files with the given message plus `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Tests are written as **name — setup → exact assertions**; helpers and all non-trivial logic are given as code, packed densely (spaces here, tabs in source).

## Bottom-up map of existing code

| component | job | evidence (file:line) |
|---|---|---|
| background seed/migrate + `onMessage` | defaults and missing fields written directly; listener handles only `badgeCount` | background.js:124-177, 180-195 |
| options save | whole-config `set` per change; direct writes in import and init; palette only here | options.js:259-326, 456, 595, 627; 49-60 |
| `compileConfig`/`matchRule` | normalize rules; toggles html classes (side effects) | content.js:649-703 |
| filter bar | pills need ≥2 visible rules; Delete; bar hidden otherwise; root-observer `needsBar`; Alt+F | content.js:808-845, 1983-1985, 2125-2132 |
| private API | `CHAT_ID_RE`, `pageFetch`, `readJson`, `getAccessToken` ("Nothing was deleted"), PATCH + error mapping | content.js:912-948, 1320-1340 |
| sidebar + titles | `el()`; `CHAT_LINK_SELECTOR`; legacy `getChatTargets` → `{row:a,item:a}`; title reads at 894, 1429, 1585 | content.js:1020-1034, 608-646 |
| scan / observer / reload | rAF scan + `itemCache`; observer watches `characterData`; `onChanged` recompiles; zero-rule early return | content.js:1406-1471, 1936-1948, 2066-2108, 2017 |
| composer, CSS, manifests | `findComposerBox`, overlay; CSS joined at 534; Firefox has no `action` | content.js:1533, 1612-1626, 534; manifest.chrome.json:9-13 |
| test seams | background stub page, options stub, `_mock_chat_api`, legacy + app-shell fixtures, unit copies | test_extension.py:828-869, 161-182, 1422-1476, 924-994, 1818-1872 |

## Test Strategy

Seams (all already used by this suite): **(a)** real `background.js` in a blank page with stubbed `browser`; **(b)** real `options.js` on `options.html` with the same stub (optionally the real `background.js` in that page) and the Playwright clock; **(c)** real extension pages + `chrome.runtime.sendMessage`; **(d)** packaged `content.js` on the app-shell and legacy fixtures, with every ChatGPT route mocked; **(e)** `unit_test.html` copies + a static test that they match the source; **(f)** static checks; **(g)** designer screenshots.

| requirement | tests | task |
|---|---|---|
| R1 button only on valid rows; default on / option off; hidden for native ⋯; own menu keeps it (`aria-expanded`) | `test_quick_tag_button_only_on_valid_chat_rows`, `test_quick_tag_default_on_and_option_off`, `test_quick_tag_hides_for_native_row_menu`, `test_quick_tag_menu_keyboard`, `test_show_quick_tag_option_persists` | T6, T3 |
| R1 order, swatch, checked, Remove, empty state, keys, Alt+T focused vs active | `test_quick_tag_menu_lists_prefix_rules_in_order`, `test_quick_tag_menu_keyboard`, `test_alt_t_focused_row_vs_active_chat` | T6 |
| R1 longest prefix + spaces, remove, no-op; Bearer + exact id; errors | `test_pick_replaces_longest_prefix_and_spaces`, `test_pick_tag_patches_exact_chat_with_bearer`, `test_rename_errors_change_nothing[6]`; unit `computeTaggedTitle` | T7, T10 |
| identity: before PATCH, while the token is pending, after PATCH (title / recycled href); text node kept; override cases; one rename per chat | `test_title_changed_before_pick_aborts`, `test_recycled_anchor_other_id_aborts`, `test_title_change_while_token_pending_aborts`, `test_post_request_change_aborts_dom_write[title,href]`, `test_rename_keeps_title_text_node`, `test_override_survives_remount_and_yields_to_third_title`, `test_overlapping_rename_same_chat_refused` | T7 |
| toast above visible overlay, 6 s, hover pause | `test_toast_above_overlay_auto_hides_and_pauses` | T7 |
| R2 trim, startsWith, colour, Escape, Tab; bounds; duplicates; exhausted palette; rename fails after creation; bound kept across awaits | `test_new_tag_trims_creates_rule_and_renames`, `test_new_tag_length_bounds[3]`, `test_new_tag_reuses_existing[2]`, `test_new_tag_rename_failure_keeps_rule`, `test_new_tag_keeps_original_chat_across_await`, `test_apply_tag_never_reads_menu_state`; `test_add_rule_*` | T8, T1 |
| R3 Undo success / failure / refused; legacy layout pick + Undo | `test_undo_restores_title`, `test_undo_failure_keeps_tag`, `test_undo_refused_after_intervening_rename`, `test_legacy_quick_tag_pick_and_undo` | T9 |
| R4 gear thresholds, order, label, Alt+F; R5 one window | `test_settings_gear_thresholds_and_label`, `test_settings_gear_opens_one_settings_page` | T5 |
| R5 popup args, refocus, worker restart, concurrent opens, fallbacks, zero rules, Firefox action | `test_popup_args_and_refocus`, `test_refocus_after_worker_restart`, `test_concurrent_opens_create_one_window`, `test_fallback_when_windows_missing`, `test_fallback_when_create_rejects`, `test_toolbar_click_with_zero_rules`, `test_manifests_have_action_without_popup` | T2 |
| R6 writer: compare-and-set writes, conflict writes nothing, retried write that landed is ok, interleaved addRule then stale write conflicts, addRule serialized, migration | `test_cas_writes_when_base_matches`, `test_cas_conflict_writes_nothing`, `test_retry_after_landed_write_is_ok`, `test_interleaved_add_rule_then_stale_write_conflicts`, `test_queue_serializes_concurrent_add_rules`, `test_migration_adds_show_quick_tag` | T1 |
| R6 options: CAS save, clean re-render, dirty or conflict → banner + draft kept + nothing written, Reload, pending resend, held save vs outside add, retry the same write, edit during a held save stays dirty, outside restore of an earlier value re-renders, our own re-render never saves, a reply from before Reload is ignored, own echo, no direct writes | `test_save_sends_cas_write`, `test_external_change_rerenders_when_clean`, `test_external_change_while_dirty_shows_banner_keeps_draft_and_writes_nothing`, `test_reload_discards_draft_and_shows_stored`, `test_toggle_on_then_off_while_held_ends_false`, `test_held_save_then_external_add_conflicts_visibly`, `test_messaging_failure_keeps_draft_and_retries_same_write`, `test_partial_hex_typed_during_held_save_is_not_lost`, `test_external_restore_of_previous_value_rerenders`, `test_rerender_of_focused_row_does_not_save`, `test_reload_ignores_stale_conflict_reply`, `test_own_echo_not_a_conflict`, `test_show_quick_tag_option_persists`, `test_only_background_writes_config` | T3 |
| R7 400/640 px, match + colour share a row | `test_narrow_layout_no_horizontal_scroll[2]` | T4 |
| unit copies; visual quality | `test_unit_copies_match_source`; T12 critique, no CRITICAL | T10, T12 |

## Component Map

| component | job | interface | reuses | likely change | test seam |
|---|---|---|---|---|---|
| config writer (background.js) | serialize every config write | `writeConfig{base,next}`→`{ok,value}` / `{ok:false,conflict:true,value}`; `addRule{tag}`→`{ok,rule,created}` | `storageGet/Set`, `enqueue` | schema | (a) |
| `canon`/`same` (background.js only) | key-order-insensitive equality for the compare-and-set | values → boolean | — | — | (a) |
| `openSettings` | popup, refocus (id in `storage.session`), fallback; own queue | msg + `action.onClicked` | `onMessage` | browser APIs | (a), (d) |
| options save client | one save in flight, pending resend, retry the same write, clean re-render, conflict banner | `autoSave()`, `send(write)`, `reload()`, `onChanged` handler | `render`, `collectConfig` | — | (b), (c) |
| settings gear | open settings | `createSettingsButton()` | `createDeleteButton` pattern | bar layout | (d) |
| quickTag UI | body-level button, menu, toast | `showQtFor(a)`, `openQtMenu(a)`, `closeQtMenu(refocus)`, `qtToast(msg,opts)` | `el`, `getChatTargets`, `findComposerBox` | ChatGPT rows | (d) |
| `computeTaggedTitle`/`currentPrefixTag` | pure prefix replace/remove | strings | `matchRule` semantics | rules | (e), (d) |
| `renameChat(id,title,stillValid,staleText)` | one PATCH, re-check just before it, error text | `Promise<void>` throws `Error(text)` | `pageFetch`, `getAccessToken`, `readJson` | API | (d) |
| `titleOverrides`, `titleIs`, `qtPending` | stale-text survival, identity, one mutation per chat | Map / fn / Set | scan | DOM churn | (d) |

**Fitness:** each unit has one job and its own test. Only the writer persists config, and that is checked statically. `computeTaggedTitle` and `same` are pure. The UI sits outside React rows, so it causes no observer churn. There is no merge, no op layer and no rule id: a stale save is refused and shown, never silently applied. Deliberate duplicates (there is no bundler), each with a "keep in sync" comment: `sendRuntimeMessage`, `PALETTE_HEX`.

## Design comparison

Top-down and bottom-up agree on the body-level button, renaming through the delete path's API, and background-only writes. The code forces six corrections. (1) content.js has no palette, so colour choice lives in `addRule`. (2) options.js also wrote in init and import; both now go through the compare-and-set `writeConfig`, and init writes only when normalization changes the stored value, which keeps `TestMigration` green. (3) `getAccessToken` error text says "Nothing was deleted", so `renameChat` remaps it. (4) All three title reads switch to `effectiveTitle`. (5) `compileConfig` has DOM side effects, so New tag builds its rule object directly. (6) The zero-rule early return stays; the toolbar icon covers that case.
**Normal flow:** hover c1 → `showQtFor` → click → `openQtMenu` binds `{id,title}` → pick `[BUG]` → `applyTag(bound, tag, rules)` checks `titleIs` → `renameChat` re-checks after the token, then sends PATCH with Bearer → 200 → `commitTitle` re-checks, sets `nodeValue`, records the override → repaint → "Tagged · Undo".
**Failure flow:** PATCH 429 → `renameChat` throws the rate-limit text → `role=alert` toast; the menu closes only if it is still this chat's; no DOM write, no override. On the options page, a rejected `sendMessage` keeps the draft and shows a sticky "Not saved — retrying"; the same `{base, next}` is retried at 1 s, 3 s, then on the next change; an outside change during an unsaved edit shows the conflict banner; nothing is written directly.

## File Structure

Modify only `src/{background,content,options}.js`, `src/options.{html,css}`, `src/manifest.{chrome,firefox}.json`, `tests/test_extension.py`, `tests/unit_test.html`, and docs (`CHANGELOG.md`, `CLAUDE.md`, `wiki/{Usage,Configuration,Privacy,Architecture}{,-zh-CN}.md`). No new source files, so `publish.sh` is unchanged.

## Tasks

Order: T1 first. T2, T3 and T4 are independent of each other (T3 needs T1). T5→T6→T7→T8→T9 touch content.js and run in sequence, in parallel with T2–T4. T10 needs T8 (reuses `_fn`). Then T11, then T12.

### Task 1: Config writer: compare-and-set, addRule, migration
**Files:** Modify `src/background.js`. Test: `tests/test_extension.py` (module helpers after `TestMigration`, plus `TestConfigWriter(_BgPages)`).
- [ ] **Helpers:**
```python
_BG_HARNESS = """([store, delay]) => { window.__store = store; window.__calls = []; const L = [];
  const ev = n => ({addListener: f => L.push([n, f])}), wait = () => new Promise(r => setTimeout(r, delay));
  const rec = n => (...a) => { __calls.push([n, a]); return Promise.resolve({id: 7}); };
  window.browser = {runtime: {onInstalled: ev('i'), onStartup: ev('s'), onMessage: ev('m'), getURL: p => 'ext://' + p, openOptionsPage: rec('openOptionsPage'),
      sendMessage: m => window.down ? Promise.reject(new Error('down')) : send(m)},
    windows: {create: rec('create'), update: rec('update'), get: rec('get'), onRemoved: ev('removed')}, action: {onClicked: ev('clicked'), setBadgeText() {}, setBadgeBackgroundColor() {}},
    storage: {onChanged: ev('changed'), session: {get: async k => ({[k]: (window.__session ||= {})[k]}), set: async o => { Object.assign(window.__session ||= {}, o); }},
      sync: {get: async k => { await wait(); return {[k]: structuredClone(__store[k])}; },
        set: async o => { await wait(); const ch = Object.fromEntries(Object.keys(o).map(k => [k, {oldValue: structuredClone(__store[k]), newValue: structuredClone(o[k])}]));
          Object.assign(__store, structuredClone(o)); __calls.push(['set', o]); fire('changed', ch, 'sync'); }}}};
  window.send = m => new Promise(r => { for (const [n, f] of L) if (n === 'm') f(m, {}, r); });
  window.fire = (n, ...a) => { for (const [k, f] of L) if (k === n) f(...a); };
  window.cfg = () => __store.tagHighlighterConfigV1; window.count = n => __calls.filter(c => c[0] === n).length; }"""
def _rule(tag, color='#fabd2f', match='startsWith', **kw): return {'tag': tag, 'match': match, 'color': color, 'hide': False, 'overlay': True, **kw}
def _full(rules, **kw): return {'rules': rules, 'maxChatTurns': 0, 'hideNavBar': True, 'dimUntagged': False, 'showBadge': True, 'lazyRenderTurns': True, 'showDeleteUntagged': False, 'showQuickTag': True, **kw}
def _tjs(cid): return f"document.querySelector('#row-{cid} [data-thread-title] span[dir=auto]').textContent"
class _BgPages:
    @pytest.fixture(autouse=True)
    def _ctx(self, browser_context):
        self.context, self._bg_pages = browser_context, []; yield
        for p in self._bg_pages: p.close()
    def bg(self, rules=None, delay=0, setup='', **kw):
        store = {STORAGE_KEY: _full([_rule('[A]'), _rule('[B]', '#fb4934')] if rules is None else rules, **kw)}
        page = self.context.new_page(); self._bg_pages.append(page); page.set_content('<html><body></body></html>'); page.evaluate(_BG_HARNESS, [store, delay])
        if setup: page.evaluate(f'() => {{ {setup} }}')  # statement body, never an auto-invoked expression
        page.add_script_tag(content=(Path(EXT_PATH) / 'background.js').read_text()); return page
```
- [ ] **Failing tests** (`W(base, next)` = `send({type:'writeConfig', base, next})`; `A(t)` = `send({type:'addRule', tag: t})`, content.js's message):
  - `test_cas_writes_when_base_matches` — `b = cfg()`; `W(b, {...b, dimUntagged:true})` → `ok` True, `value.dimUntagged` true; stored `dimUntagged` true; `count('set') == 1`. A base with the same content in a different key order also matches.
  - `test_cas_conflict_writes_nothing` — `b = cfg()`; `A('[NEW]')`; `W(b, {...b, dimUntagged:true})` → `ok` False, `conflict` True, `value.rules` tags `['[A]','[B]','[NEW]']`; stored tags the same, `dimUntagged` false; `count('set') == 1` (the addRule only).
  - `test_retry_after_landed_write_is_ok` — `b = cfg(); n = {...b, maxChatTurns: 3}`; `W(b, n)` twice → both `ok`, stored `maxChatTurns == 3`, `count('set') == 1`.
  - `test_interleaved_add_rule_then_stale_write_conflicts` — `delay=20`; `b = cfg()`; `Promise.all([A('[NEW]'), W(b, {...b, dimUntagged:true})])` → the write's reply has `conflict` True; stored tags `['[A]','[B]','[NEW]']`, `dimUntagged` false.
  - Kept: `test_add_rule_trims_and_dedupes` (rules `[A]`, `code` (includes): `A('  [NEW]  ')` → created `[NEW]` `startsWith`; `A('[A]')`, `A('code')`, `A('[NEW]')` → `created is False`; 3 rules), `test_add_rule_length_bounds` (`''`, `'   '`, `'x'*41` → `{'ok': False, 'error': 'Tags are 1–40 characters.'}`; `'x'*40` ok), `test_add_rule_palette_first_unused_then_gray` (colours `#fb4934,#fabd2f` → `#b8bb26`; all ten used → `#a7a7a7`), `test_queue_serializes_concurrent_add_rules` (`delay=15`, five concurrent `A` → 7 rules), `test_migration_adds_show_quick_tag` (`setup='delete __store.tagHighlighterConfigV1.showQuickTag'` → wait for `cfg().showQuickTag === true`).
- [ ] **Fail → pass → commit:** `RUN 'TestConfigWriter or TestMigration'` first FAILS with `Timeout` (nothing answers `writeConfig`/`addRule`), then PASSES. Then commit `src/background.js tests/test_extension.py` with the message `feat(background): compare-and-set config writer and addRule on one chain`.
- [ ] **Implement.** The seed object gets `showQuickTag: true`. Migration adds `const showQuickTag = existing.showQuickTag !== false;`, adds `|| typeof existing.showQuickTag !== 'boolean'` to `needWrite`, and writes the field last (same key order as options.js `collectConfig`). Rename the body to `seedOrMigrateNow`; `const seedOrMigrate = () => enqueue(seedOrMigrateNow);` so migration shares the chain.
```js
const PALETTE_HEX = ['#fb4934', '#b8bb26', '#fabd2f', '#83a598', '#d3869b', '#8ec07c', '#fe8019', '#928374', '#a7a7a7', '#ffffff']; // keep in sync with options.js PALETTE
let chain = Promise.resolve();
function enqueue(job) { const run = chain.then(job); chain = run.catch(() => {}); return run; } // one promise chain for every config write
const canon = v => JSON.stringify(v, (k, x) => (x && typeof x === 'object' && !Array.isArray(x)) ? Object.fromEntries(Object.keys(x).sort().map(key => [key, x[key]])) : x);
const same = (a, b) => canon(a ?? null) === canon(b ?? null); // key order does not matter
const readCfg = async () => (await storageGet(STORAGE_KEY))?.[STORAGE_KEY] ?? null;
function writeConfig(base, next) { // compare-and-set: never applies a write made against an outdated value
  return enqueue(async () => {
    if (!next || !Array.isArray(next.rules)) throw new Error('Invalid config');
    const current = await readCfg();
    if (same(current, base)) { await storageSet({[STORAGE_KEY]: next}); return {value: next}; }
    if (same(current, next)) return {value: current}; // a retried write that already landed
    return {conflict: true, value: current};           // changed elsewhere: write nothing
  }); }
const validTag = t => { const s = String(t ?? '').trim(); return s.length >= 1 && s.length <= 40 ? s : null; };
function addRule(rawTag) { // content.js New tag: appended to the freshest value
  const tag = validTag(rawTag); if (!tag) return Promise.reject(new Error('Tags are 1–40 characters.'));
  return enqueue(async () => {
    const cfg = (await readCfg()) || {}, rules = Array.isArray(cfg.rules) ? cfg.rules : [];
    const existing = rules.find(r => String(r.tag).trim() === tag); if (existing) return {rule: existing, created: false}; // any match type
    const used = new Set(rules.map(r => String(r.color).toLowerCase()));
    const rule = {tag, match: 'startsWith', color: PALETTE_HEX.find(h => !used.has(h)) || '#a7a7a7', hide: false, overlay: true};
    await storageSet({[STORAGE_KEY]: {...cfg, rules: [...rules, rule]}}); return {rule, created: true};
  }); }
```
Replace the listener at 180 with `(msg, sender, sendResponse) => {` + the unchanged `badgeCount` branch, then: `const job = msg?.type === 'writeConfig' ? writeConfig(msg.base ?? null, msg.next) : msg?.type === 'addRule' ? addRule(msg.tag) : null; if (!job) return false; job.then(r => sendResponse({ok: !r.conflict, ...r}), e => sendResponse({ok: false, error: String(e?.message || e)})); return true;`.

### Task 2: openSettings + Firefox action (independent)
**Files:** Modify `src/background.js`, `src/manifest.firefox.json`. Test: `TestOpenSettings(_BgPages)`, new `TestStatic`.
- [ ] **Failing tests:**
  - `test_popup_args_and_refocus` — send `openSettings` → `create` args `[{'url':'ext://options.html','type':'popup','width':560,'height':720,'focused':True}]`; send again → `count('create') == 1`, `update` args `[7, {'focused': True}]`; `fire('removed', 7)`, send → `count('create') == 2`.
  - `test_refocus_after_worker_restart` — `setup="window.__session = {cthSettingsWindowId: 7}"` → send → `count('create') == 0`, `update` `[7, {'focused': True}]`; if `setup` also makes `browser.windows.get` reject → `count('create') == 1`.
  - `test_concurrent_opens_create_one_window` — two sends in `Promise.all` → `count('create') == 1`.
  - `test_fallback_when_windows_missing` (`delete browser.windows`) and `test_fallback_when_create_rejects` (`create` rejects) → `count('openOptionsPage') == 1`.
  - `test_toolbar_click_with_zero_rules` — `bg(rules=[])`; `fire('clicked', {id:1})` → wait for `count('create') === 1`. `TestStatic.test_manifests_have_action_without_popup` — both manifests: `'action' in m and 'default_popup' not in m['action']`.
- [ ] **Fail → pass → commit:** `RUN 'TestOpenSettings or TestStatic'` first FAILS (`send` times out; `AssertionError: manifest.firefox.json`), then PASSES. Then commit `src/background.js src/manifest.firefox.json tests/test_extension.py` with the message `feat(background): settings popup with refocus across worker restarts`.
- [ ] **Implement.** Firefox manifest: add `"action": {"default_icon": {"128": "icon-128.png"}},` after `icons`. In the job selector, add `: msg?.type === 'openSettings' ? openSettings()` before `: null`.
```js
const SETTINGS_WIN_KEY = 'cthSettingsWindowId', winMem = {}; // storage.session survives worker restarts (Chrome 102+, Firefox 115+); memory otherwise
const sessionArea = API.storage?.session ?? {get: async k => ({[k]: winMem[k]}), set: async o => { Object.assign(winMem, o); }}; let settingsChain = Promise.resolve();
const settingsQueue = job => { const run = settingsChain.then(job); settingsChain = run.catch(() => {}); return run; }; // rapid clicks: one window
const openSettings = () => settingsQueue(async () => { try { if (!API.windows?.create) throw new Error('no windows API'); const id = (await sessionArea.get(SETTINGS_WIN_KEY))?.[SETTINGS_WIN_KEY];
    if (typeof id === 'number') { try { await API.windows.get(id); await API.windows.update(id, {focused: true}); return {}; } catch {} }
    const w = await API.windows.create({url: API.runtime.getURL('options.html'), type: 'popup', width: 560, height: 720, focused: true});
    await sessionArea.set({[SETTINGS_WIN_KEY]: w?.id ?? null}); } catch { await API.runtime.openOptionsPage?.(); } return {}; });
API.windows?.onRemoved?.addListener?.(id => settingsQueue(async () => { if ((await sessionArea.get(SETTINGS_WIN_KEY))?.[SETTINGS_WIN_KEY] === id) await sessionArea.set({[SETTINGS_WIN_KEY]: null}); }));
(API.action ?? API.browserAction)?.onClicked?.addListener?.(() => { openSettings(); });
```

### Task 3: options.js compare-and-set client, conflict banner, showQuickTag (after T1)
**Files:** Modify `src/options.js`, `src/options.html`. Test: `TestOptionsPage`, `TestStatic`.
- [ ] **Helpers:**
```python
    def _fresh(self, cfg):
        page = self._open_options(); self._set_config(page, cfg); page.reload(); page.wait_for_selector('#rows tr'); return page
    def _opts(self, cfg, setup='', with_bg=False, clock=False, delay=0):  # stubbed options page; optionally the real background.js in the same page
        page = self.context.new_page(); page.set_content((Path(EXT_PATH) / 'options.html').read_text().replace('<script src="options.js"></script>', ''))
        if clock: page.clock.install()
        page.evaluate(_BG_HARNESS, [{STORAGE_KEY: cfg}, delay])
        if setup: page.evaluate(f'() => {{ {setup} }}')  # statement body, never an auto-invoked expression
        for name in (['background.js'] if with_bg else []) + ['options.js']: page.add_script_tag(content=(Path(EXT_PATH) / name).read_text())
        return page
```
- [ ] **Failing tests.** All use `_opts(_full([A]), with_bg=True, setup=…)` (the real writer in the page; the test's own `send(...)` is another window) unless noted. `LOG` = `window.msgs = []; const real = browser.runtime.sendMessage; browser.runtime.sendMessage = m => { msgs.push(structuredClone(m)); return real(m); };`. `HOLD` = `window.releases = []; const real = browser.runtime.sendMessage; let first = true; browser.runtime.sendMessage = m => { if (!first) return real(m); first = false; return new Promise(r => releases.push(() => r(real(m)))); };`. Both are statement bodies (`_opts` wraps setup in `() => { … }`). `BANNER` = `#conflict` visible with text `Settings changed in another window.` and a `Reload` button.
  - Update `test_options_waits_for_loaded_rules_before_autosaving`: the stub's `sendMessage` pushes `m` to `writes` and returns `{ok: true, value: m.next}`; the stub adds `storage.onChanged`. Before release, checking `#dimUntagged` writes nothing; after `releaseConfig(...)` and checking again → `writes.at(-1).type == 'writeConfig'`, `.next.rules[0].tag == '[SAVED]'`, `.next.dimUntagged is True`.
  - `test_save_sends_cas_write` — LOG; check `#dimUntagged` → `msgs == [{'type': 'writeConfig', 'base': _full([A]), 'next': {**_full([A]), 'dimUntagged': True}}]` (init sent nothing: the stored value is already normalized); stored `dimUntagged` true; `count('set') == 1`.
  - `test_external_change_rerenders_when_clean` — `send({type:'addRule', tag:'[NEW]'})` → 2 rows; `#conflict` hidden.
  - `test_external_change_while_dirty_shows_banner_keeps_draft_and_writes_nothing` — focus `#rows .tag`, press End, type `Q` (unsaved); `send(addRule '[NEW]')` → BANNER; 1 row, value `[A]Q`; click `#debugTitle` (change → save attempt) → BANNER still; stored tags `['[A]','[NEW]']`; `count('set') == 1`.
  - `test_reload_discards_draft_and_shows_stored` — same start until BANNER; click `#conflictReload` → 2 rows `['[A]','[NEW]']`, `#conflict` hidden; check `#dimUntagged` → stored `dimUntagged` true, tags `['[A]','[NEW]']`.
  - `test_toggle_on_then_off_while_held_ends_false` — HOLD; check then uncheck `#dimUntagged` (second is pending); `releases[0]()` → wait for `count('set') === 2` → stored `dimUntagged` false; unchecked; `#conflict` hidden.
  - `test_held_save_then_external_add_conflicts_visibly` — HOLD; check `#dimUntagged` (held); `send(addRule '[NEW]')` → BANNER (dirty); release → BANNER still; stored tags `['[A]','[NEW]']` (nothing silently lost), `dimUntagged` false; `#dimUntagged` still checked (draft kept).
  - `test_messaging_failure_keeps_draft_and_retries_same_write` — `_opts(_full([A]), clock=True, setup="window.sent = []; browser.runtime.sendMessage = async m => { sent.push(JSON.stringify(m)); if (sent.length <= 3) throw new Error('down'); return {ok: true, value: m.next}; };")`; `run_for(50)`; click `#dimUntagged`, `run_for(10)` → 1 send, toast `Not saved — retrying`; `run_for(1000)` → 2; `run_for(3000)` → 3; `run_for(10000)` → 3; `sent[0] == sent[1] == sent[2]`; still checked; `count('set') == 0`; click `#lazyRenderTurns`, `run_for(10)` → `sent[3] == sent[0]` (the same write first), then `sent[4]` has `next.lazyRenderTurns` false and `base.dimUntagged` true; toast `Auto-saved ✓`.
  - `test_partial_hex_typed_during_held_save_is_not_lost` — `_opts(_full([_rule('[A]', '#999999')]), with_bg=True, setup=HOLD)`; check `#dimUntagged` (held); `fill('#rows .hex', '#12')` (input only, no blur); `releases[0]()` → wait for `count('set') === 1`; `send(addRule '[NEW]')` → BANNER; `#rows .hex` value `#12`; stored `[A]` colour `#999999`, tags `['[A]','[NEW]']`; `count('set') == 2` (options wrote only the held save).
  - `test_external_restore_of_previous_value_rerenders` — check `#dimUntagged` → wait for stored `dimUntagged` true (B); `c = cfg()`; `send(writeConfig c → {...c, dimUntagged: false})` (C) → unchecked, `#conflict` hidden; `c = cfg()`; `send(writeConfig c → {...c, dimUntagged: true})` (B again) → checked, `#conflict` hidden.
  - `test_rerender_of_focused_row_does_not_save` — LOG; focus `#rows .hex` (no typing); `send(addRule '[NEW]')` → 2 rows, the second `[NEW]`; wait 500 ms → `msgs == []`; stored tags `['[A]','[NEW]']`; `#conflict` hidden.
  - `test_reload_ignores_stale_conflict_reply` — `_opts(_full([A]), with_bg=True, delay=50, setup=HOLD_REPLY)` where `HOLD_REPLY` = `window.releases = []; const real = browser.runtime.sendMessage; let first = true; browser.runtime.sendMessage = m => { if (!first) return real(m); first = false; return real(m).then(r => new Promise(ok => releases.push(() => ok(r)))); };` (holds the first reply, not the write). Check `#dimUntagged`; immediately `send(addRule '[X]')` (lands first, so the held write gets `conflict`); wait for `releases.length === 1`; `send(addRule '[Y]')` → BANNER; click `#conflictReload` → rows `['[A]','[X]','[Y]']`, `#conflict` hidden; `releases[0]()`; wait 300 ms → rows still `['[A]','[X]','[Y]']`, `#conflict` hidden, `#dimUntagged` unchecked; stored tags `['[A]','[X]','[Y]']`, `dimUntagged` false.
  - `test_own_echo_not_a_conflict` — count `onChanged` events; mark the first `tr`; check `#dimUntagged`; 800 ms → count `== 1`, mark kept (no re-render), `#conflict` hidden.
  - Kept: `test_show_quick_tag_option_persists` (`_fresh(_full([A], showQuickTag=None))` → checked; uncheck → `wait_for_function` on `chrome.storage.sync.get` until stored `showQuickTag === false`; check → stored `true`), `TestStatic.test_only_background_writes_config` (options.js does not match `\bstore\.set\(`; content.js has no `storageSet(storeSync`, `storeSync.set(` or `storage.sync.set(`).
- [ ] **Fail → pass → commit:** `RUN 'TestOptionsPage or TestMigration or TestStatic'` first FAILS (`#conflict` missing; `#showQuickTag` missing; `store.set(` matched), then PASSES. Then commit `src/options.js src/options.html src/options.css tests/test_extension.py` with the message `feat(options): compare-and-set saves with a visible conflict banner`.
- [ ] **Implement.** `options.html`: a General row after `showDeleteUntagged` — `<input id="showQuickTag" type="checkbox" checked />`, "Show quick tag button", hint "Hover a chat or press Alt+T to add, change or remove its prefix tag. This renames the chat on ChatGPT."; above `<main>`: `<div id="conflict" class="conflict" role="alert" hidden>Settings changed in another window. <button id="conflictReload" type="button">Reload</button></div>`. `options.css`: `.conflict{margin:0 0 12px;padding:8px 12px;border:1px solid #fb4934;border-radius:12px;display:flex;gap:8px;align-items:center} .conflict[hidden]{display:none}`. options.js: add `showQuickTag` to `els`, `DEFAULT_CFG` (`true`), `render` (`!== false`) and `collectConfig` (last key); `els` also gains `conflict: $('conflict'), conflictReload: $('conflictReload')`. `toast(message, sticky = false)` skips the hide timer when sticky. Delete `set` and the old `autoSave`/`init`; existing listeners keep calling `autoSave()`; the rows `blur` handler starts with `if (rendering) return;` (removing a focused row during a render blurs it). Import: `const cfg = normalizeCfg(parsed)` (same "Invalid config" checks), `render(cfg); autoSave('Imported ✓')` (its `base` is the current base). Export is unchanged.
```js
function sendRuntimeMessage(msg) { // keep in sync with content.js
  return new Promise((resolve, reject) => { try { const r = API.runtime.sendMessage(msg, API === globalThis.chrome ? res => { const e = API.runtime.lastError; e ? reject(new Error(e.message)) : resolve(res); } : undefined);
    if (r?.then) r.then(resolve, reject); } catch (e) { reject(e); } });
}
const eq = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null); // only for our own values; background compares key-order-insensitively
const normalizeCfg = raw => ({rules: (raw.rules || []).map(r => ({tag: String(r?.tag || '').trim(), match: safeMatch(r?.match), color: toHex(r?.color, '#999999'), hide: r?.hide === true, overlay: r?.overlay !== false})).filter(r => r.tag),
  maxChatTurns: safeInt(raw.maxChatTurns, 0), hideNavBar: raw.hideNavBar !== false, dimUntagged: raw.dimUntagged === true, showBadge: raw.showBadge !== false,
  lazyRenderTurns: raw.lazyRenderTurns !== false, showDeleteUntagged: raw.showDeleteUntagged === true, showQuickTag: raw.showQuickTag !== false});
// base = last stored value rendered or acknowledged; a save is written only if storage still equals it.
// gen changes on every render from storage (incl. Reload); a reply from an older gen is ignored. rendering blocks saves caused by our own render.
let base = null, dirty = false, inFlight = false, pending = false, conflict = false, failed = null, sentNext = null, sentGen = -1, editSeq = 0, gen = 0, rendering = false, retryTimer = 0, retryStep = 0, okMsg = 'Auto-saved ✓';
const RETRY_MS = [1000, 3000];
function show(cfg) { gen++; rendering = true; try { render(cfg); } finally { rendering = false; } } // every programmatic render goes through here
function autoSave(message) {
  if (!ready || rendering) return; dirty = true; if (message) okMsg = message;
  if (conflict) return;                                 // the banner is up: edits stay on screen, nothing is sent
  if (inFlight) { pending = true; return; }             // one save at a time
  if (failed) { pending = true; send(failed); return; } // retry the same write first
  send({base, next: collectConfig(), seq: editSeq});
} async function send(write) {
  clearTimeout(retryTimer); inFlight = true; sentNext = write.next; const myGen = sentGen = gen, {seq, ...payload} = write; let res; // seq stays local
  try { res = await sendRuntimeMessage({type: 'writeConfig', ...payload}); if (!res || (!res.ok && !res.conflict)) throw new Error(res?.error || 'failed'); }
  catch { // never write storage: keep the draft, retry the same {base, next}
    inFlight = false; if (myGen !== gen) { flushPending(); return; } // Reload since: drop this write
    failed = write; toast('Not saved — retrying', true);
    if (retryStep < RETRY_MS.length) retryTimer = setTimeout(() => send(write), RETRY_MS[retryStep++]);
    return; }
  inFlight = false; if (myGen !== gen) { flushPending(); return; } // stale reply (Reload or re-render since): ignore it
  failed = null; retryStep = 0;
  if (res.conflict) { pending = false; if (dirty) showConflict(); else { base = res.value; show(normalizeCfg(res.value || DEFAULT_CFG())); } return; } // a lost init/migration race: just adopt
  base = res.value;
  if (pending) { pending = false; send({base, next: collectConfig(), seq: editSeq}); return; }
  if (editSeq === seq) dirty = false; // no edit since this write was built (a typed partial value keeps the page dirty)
  toast(okMsg); okMsg = 'Auto-saved ✓'; }
function flushPending() { if (pending && !conflict) { pending = false; send({base, next: collectConfig(), seq: editSeq}); } } // edits made after a Reload
function showConflict() { conflict = true; els.conflict.hidden = false; }
async function reload() { // discards the draft; any reply still in flight is now stale
  const v = (await get(STORAGE_KEY))?.[STORAGE_KEY]; clearTimeout(retryTimer);
  base = v ?? null; dirty = pending = conflict = false; failed = null; retryStep = 0; els.conflict.hidden = true; show(normalizeCfg(v || DEFAULT_CFG()));
}
els.conflictReload.addEventListener('click', reload);
els.showQuickTag.addEventListener('change', () => autoSave());
for (const box of [els.rows, ...document.querySelectorAll('.generalRow')]) for (const type of ['input', 'change']) box.addEventListener(type, () => { if (ready && !rendering) { editSeq++; dirty = true; } }, true); // capture: counts the edit before autoSave records seq
API.storage?.onChanged?.addListener((ch, area) => {
  const v = ch[STORAGE_KEY]?.newValue; if (!v || !ready || API.storage[area] !== store) return;
  const live = inFlight && sentGen === gen; // a write from before a Reload is not ours any more
  if (eq(v, base) || (live && eq(v, sentNext))) return; // our own echo (only while that write is in flight)
  if (!dirty && !live && !conflict) { base = v; show(normalizeCfg(v)); return; }
  showConflict();                                      // unsaved edits or a save in flight: keep the draft, write nothing
}); async function init() {
  const raw = (await get(STORAGE_KEY))?.[STORAGE_KEY] ?? null, cfg = raw && Array.isArray(raw.rules) ? normalizeCfg(raw) : DEFAULT_CFG();
  base = raw; show(cfg); ready = true;
  if (!eq(cfg, raw)) send({base: raw, next: cfg, seq: editSeq}); // seed / migration, compare-and-set safe
} init();
```

### Task 4: Narrow options layout (independent)
**Files:** Modify `src/options.html` (template `td`s get `data-label`: `#`, `Move`, `Tag`, `Match`, `Color`, `Hex`, `Hide`, `Overlay`, `Preview`, `Delete`) and `src/options.css`. Test: `TestOptionsPage`.
- [ ] **Failing test** `test_narrow_layout_no_horizontal_scroll[400|640]` — `_fresh(_full([A, B]))`, viewport `width×900` → `document.documentElement.scrollWidth <= innerWidth`; first `#rows tr` display `grid`; `getComputedStyle(td:nth-child(3), '::before').content == '"Tag"'`; at 400 only, match (`td:nth-child(4)`) and colour (`td:nth-child(5)`) have equal `getBoundingClientRect().top` and different `left`; at 900 px display is `table-row`.
- [ ] **Fail → pass → commit:** `RUN test_narrow_layout` first FAILS with `'table-row' == 'grid'`, then PASSES. Then commit `src/options.html src/options.css tests/test_extension.py` with the message `feat(options): stacked rule cards at 640px and below`.
- [ ] **Implement** (append to `options.css`; card rows: #/drag/swatch/delete · tag · match + colour · hex · hide + overlay):
```css
@media (max-width: 640px) {
  body { padding: 12px; } .header, .actions { flex-wrap: wrap; } .title { min-width: 0; }
  .table, .table tbody { display: block; width: 100%; } .table thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  #rows tr { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px 8px; padding: 8px; margin-bottom: 8px; border: 1px solid var(--border); border-radius: 12px; }
  #rows td { display: block; min-width: 0; padding: 0; } #rows td:nth-child(3), #rows td:nth-child(6) { grid-column: 1 / -1; }
  #rows td:nth-child(4), #rows td:nth-child(5), #rows td.hideCell, #rows td.overlayCell { grid-column: span 2; }
  #rows td.previewCell { grid-column: 3; grid-row: 1; } #rows td.delCell { grid-column: 4; grid-row: 1; justify-self: end; } #rows .del { width: 34px; }
  #rows td:nth-child(n+3):nth-child(-n+6)::before { content: attr(data-label); display: block; font-size: 12px; color: var(--muted); }
  #rows tr.drag-over { box-shadow: 0 -2px 0 var(--accent); } #rows .input, #rows .select { width: 100%; } }
```

### Task 5: content.js — showQuickTag, settings gear, bar threshold (T5–T9 run in sequence)
**Files:** Modify `src/content.js`. Test: `TestAppShellContentScript`.
- [ ] **Failing tests:**
  - `test_settings_gear_thresholds_and_label` — `_configure(rules=[CONTENT_RULES[0]])` → bar child ids `['cth-settings']`; `aria-label` and `title` are `Tag Highlighter settings`, text empty; `Alt+f` focuses it; `_configure(showDeleteUntagged=True)` → first child `.cth-pill`, then `#cth-delete-untagged`, then `#cth-settings` last.
  - `test_settings_gear_opens_one_settings_page` — `expect_page` on clicking `#cth-settings` → URL ends `/options.html`; click again, wait 800 ms → exactly one such page (add it to `self._pages`).
- [ ] **Fail → pass → commit:** `RUN test_settings_gear` first FAILS with `[] == ['cth-settings']`, then PASSES; the regression check `RUN 'TestAppShellContentScript or TestContentScript'` also PASSES. Then commit `src/content.js tests/test_extension.py` with the message `feat(content): settings gear in the filter bar`.
- [ ] **Implement.** `compileConfig` returns `showQuickTag: cfg?.showQuickTag !== false`. Copy `sendRuntimeMessage` from T3 verbatim. `renderFilterBar`: the early return becomes `if (!compiled || compiled.rules.length === 0)`; append order pills → delete → `createSettingsButton()`. Root observer (1983): `const needsBar = compiled?.rules.length > 0;`. Alt+F selector adds `#${SETTINGS_BTN_ID}`.
```js
const SETTINGS_BTN_ID = 'cth-settings';
const COG_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/></svg>';
function createSettingsButton() { const btn = el('button', {type: 'button', id: SETTINGS_BTN_ID, 'aria-label': 'Tag Highlighter settings', title: 'Tag Highlighter settings'});
  btn.innerHTML = COG_SVG; // static markup, no user data
  btn.addEventListener('click', () => { sendRuntimeMessage({type: 'openSettings'}).catch(() => {}); }); return btn; }
```
Append to `filterBarCss`: `#cth-settings{width:26px;height:26px;border-radius:999px;display:inline-grid;place-items:center;padding:0;background:transparent;cursor:pointer;border:1px solid rgba(255,255,255,.12);color:rgba(255,255,255,.60);margin-inline-start:auto} html.cth-light #cth-settings{border-color:rgba(0,0,0,.10);color:rgba(0,0,0,.55)} #cth-delete-untagged ~ #cth-settings{margin-inline-start:0} #cth-settings:focus-visible{outline:2px solid currentColor;outline-offset:2px}`.

### Task 6: Quick tag button, menu, Alt+T
**Files:** Modify `src/content.js` (new section before `// ---- History observer ----`; `quickTagCss` is added to the join at 534). Test: `TestAppShellContentScript`.
- [ ] **Helpers:** `_qt_page(self, chats=None, rules=None, **mock)` → `_configure(rules=rules)`, `_open_chat(...)`, `_ready`, then `calls, held = self._mock_chat_api(page, **mock)`; returns `page, calls, held`. `_open_qt(self, page, cid)` → hover `#row-{cid}`, click `#cth-qt-btn`, wait for `#cth-qt-menu[data-cth-chat="{cid}"]`.
- [ ] **Failing tests:**
  - `test_quick_tag_button_only_on_valid_chat_rows` — chats `DEFAULT_CHATS + [('bad id!', '[TODO] x')]`; hover c3 → visible, `aria-label == 'Tag chat'`; hover `[id="row-bad id!"]` and `#other-nav` → hidden; `focus('#row-c2 a')` → visible.
  - `test_quick_tag_menu_lists_prefix_rules_in_order` — on c2: `[tag, aria-checked, swatch]` = `[['[TODO]','false','rgb(250, 189, 47)'], ['[BUG]','true','rgb(251, 73, 52)'], ['[ARCHIVE]','false','rgb(146, 131, 116)']]`; Remove + New visible; c5 → no Remove; with rules `[CONTENT_RULES[3]]` → `No prefix tags yet`.
  - `test_quick_tag_menu_keyboard` — on c1: while open, `#cth-qt-btn` is visible with `aria-expanded == 'true'`; focus `[TODO]` → ArrowUp `new` → ArrowDown `[TODO]` → End `new` → Home `[TODO]`; Escape closes and focuses `#cth-qt-btn`; reopen, Tab → closed.
  - `test_quick_tag_hides_for_native_row_menu` — give `#row-c3 .menu` a click handler that sets `aria-expanded="true"` after `setTimeout(0)` (like ChatGPT); hover c3 → visible; click `.menu`, wait 700 ms, hover `#row-c3` → hidden; set `aria-expanded="false"`, hover c2 then c3 → visible; `focus('#row-c2 .menu')`, press Enter → hidden.
  - `test_alt_t_focused_row_vs_active_chat` — focus `#row-c3 a`, `Alt+t` → `data-cth-chat == 'c3'`; Escape, blur, `Alt+t` → `'c1'`. `test_quick_tag_default_on_and_option_off` — visible by default; `_configure(showQuickTag=False)` → no `#cth-qt-btn:not([hidden])` on hover, and `Alt+t` opens no menu.
- [ ] **Fail → pass → commit:** `RUN 'test_quick_tag or test_alt_t'` first FAILS with `Timeout … #cth-qt-btn`, then PASSES. Then commit `src/content.js tests/test_extension.py` with the message `feat(content): quick tag button, menu and Alt+T`.
- [ ] **Implement:**
```js
const QT_BTN_ID = 'cth-qt-btn', QT_MENU_ID = 'cth-qt-menu', QT_TOAST_ID = 'cth-qt-toast';
const TAG_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9z"/><circle cx="7.5" cy="7.5" r="1.5"/></svg>';
const chatIdOf = a => { const m = /^\/c\/([^/?#]+)$/.exec(a?.getAttribute('href') || ''); return m && CHAT_ID_RE.test(m[1]) ? m[1] : null; };
const findChatAnchorById = id => getChatAnchors().find(a => chatIdOf(a) === id) || null; function currentPrefixTag(title, rules) { let best = null;
  for (const r of rules) if (r.match === 'startsWith' && title.startsWith(r.tag) && (!best || r.tag.length > best.length)) best = r.tag;
  return best; } function computeTaggedTitle(title, tag, rules) { const cur = currentPrefixTag(title, rules), rest = (cur ? title.slice(cur.length) : title).replace(/^\s+/, '');
  return tag === null ? rest : (rest ? `${tag} ${rest}` : tag); } let qtBtn = null, qtAnchor = null, qtMenu = null, qtBound = null, qtBusy = false, qtToastTimer = 0;
function ensureQtButton() { if (qtBtn?.isConnected) return qtBtn;
  qtBtn = el('button', {type: 'button', id: QT_BTN_ID, 'aria-label': 'Tag chat', 'aria-haspopup': 'menu', 'aria-expanded': 'false', hidden: true}); qtBtn.innerHTML = TAG_SVG; // static markup
  qtBtn.addEventListener('click', () => (qtMenu ? closeQtMenu(true) : qtAnchor && openQtMenu(qtAnchor))); document.body.append(qtBtn); return qtBtn; }
function hideQtButton() { if (qtBtn && !qtMenu) { qtBtn.hidden = true; qtAnchor = null; } } function showQtFor(a) {
  if (qtMenu) return; // stays visible (aria-expanded) while its own menu is open: deliberate, see reconciliation
  const row = a && getChatTargets(a).row; // legacy rows are the anchor itself: no native ⋯ to align to
  if (row && row === qtSuppressRow && (performance.now() < qtSuppressUntil || row.querySelector('button[aria-expanded="true"]'))) { hideQtButton(); return; }
  if (row && row !== qtSuppressRow) qtSuppressRow = null; // pointer moved to another row
  const more = row && row !== a ? [...row.querySelectorAll('button')].filter(b => !a.contains(b)).at(-1) : null;
  if (!a || !compiled?.showQuickTag || !chatIdOf(a) || deleteDialog || more?.getAttribute('aria-expanded') === 'true') { hideQtButton(); return; }
  const btn = ensureQtButton(), r = row.getBoundingClientRect(), m = more?.getBoundingClientRect();
  btn.style.setProperty('--cth-qt-top', `${r.top + r.height / 2 - 12}px`); btn.style.setProperty('--cth-qt-left', `${m ? m.left - 28 : r.right - 32}px`);
  qtAnchor = a; btn.hidden = false; } function anchorFrom(node) { if (!historyRoot?.contains(node)) return null;
  const a = node.closest('a') || node.closest('[role="group"]')?.querySelector('a'); return a?.matches(CHAT_LINK_SELECTOR) ? a : null; }
for (const type of ['pointerover', 'focusin']) document.addEventListener(type, e => { if (!e.target.closest?.(`#${QT_BTN_ID}, #${QT_MENU_ID}`)) showQtFor(anchorFrom(e.target)); }, true);
let qtSuppressRow = null, qtSuppressUntil = 0; // ChatGPT's own row menu is opening: stay out of its way
function suppressForNative(t) { const b = t.closest?.('button'); if (!b || b.id === QT_BTN_ID || !historyRoot?.contains(b)) return;
  const a = anchorFrom(b); qtSuppressRow = a ? getChatTargets(a).row : null; qtSuppressUntil = performance.now() + 600; hideQtButton(); }
document.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') suppressForNative(e.target); }, true);
const qtItems = () => (qtMenu ? [...qtMenu.querySelectorAll('[role^="menuitem"]:not([aria-disabled])')] : []);
function openQtMenu(a) { closeQtMenu(false); showQtFor(a); const id = chatIdOf(a); if (!id || qtAnchor !== a) return;
  const title = getChatTitleText(a), cur = currentPrefixTag(title, compiled.rules); qtBound = {id, title};
  const items = compiled.rules.filter(r => r.match === 'startsWith').map(r => el('div', {role: 'menuitemradio', tabindex: '-1', 'aria-checked': String(r.tag === cur), 'data-tag': r.tag, class: 'cth-qt-item'},
    [el('span', {class: 'cth-qt-swatch', style: `background:${r.color}`}), el('span', {class: 'cth-qt-label', text: r.tag}), el('span', {class: 'cth-qt-check', text: r.tag === cur ? '✓' : ''})]));
  const tail = [el('div', {role: 'separator'})]; if (cur) tail.push(el('div', {role: 'menuitem', tabindex: '-1', 'data-action': 'remove', class: 'cth-qt-item cth-qt-danger', text: 'Remove tag'}));
  tail.push(el('div', {role: 'menuitem', tabindex: '-1', 'data-action': 'new', class: 'cth-qt-item', text: 'New tag…'}));
  qtMenu = el('div', {id: QT_MENU_ID, role: 'menu', 'aria-label': 'Tag chat', 'data-cth-chat': id},
    [el('div', {class: 'cth-qt-list'}, items.length ? items : [el('div', {class: 'cth-qt-empty', text: 'No prefix tags yet'})]), ...tail]);
  qtMenu.addEventListener('keydown', onQtMenuKey); document.body.append(qtMenu); positionQtMenu();
  qtBtn.setAttribute('aria-expanded', 'true'); qtItems()[0]?.focus(); } function closeQtMenu(refocus) { if (!qtMenu) return;
  qtMenu.remove(); qtMenu = null; qtBound = null; qtBusy = false; qtBtn?.setAttribute('aria-expanded', 'false'); if (refocus) qtBtn?.focus(); } function onQtMenuKey(e) {
  const items = qtItems(), i = items.indexOf(document.activeElement), go = n => { e.preventDefault(); items[(n + items.length) % items.length]?.focus(); };
  if (e.key === 'ArrowDown') go(i + 1); else if (e.key === 'ArrowUp') go(i - 1); else if (e.key === 'Home') go(0); else if (e.key === 'End') go(items.length - 1);
  else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); document.activeElement?.click(); }
  else if (e.key === 'Escape') { e.preventDefault(); closeQtMenu(true); } else if (e.key === 'Tab') closeQtMenu(false); }
function positionQtMenu() { const b = qtBtn.getBoundingClientRect(), h = qtMenu.offsetHeight, up = b.bottom + 4 + h > innerHeight;
  qtMenu.style.setProperty('--cth-qt-top', `${up ? Math.max(8, b.top - 4 - h) : b.bottom + 4}px`); qtMenu.style.setProperty('--cth-qt-left', `${Math.max(8, b.right - 220)}px`); }
document.addEventListener('pointerdown', e => { if (qtMenu && !e.target.closest?.(`#${QT_MENU_ID}, #${QT_BTN_ID}`)) closeQtMenu(false); suppressForNative(e.target); }, true);
```
Keydown handler, before Alt+H: `if (isAltKey(e, 't')) { e.preventDefault(); const a = anchorFrom(document.activeElement) || (historyRoot && getActiveChatAnchor(historyRoot)); if (a) openQtMenu(a); return; }`. In the config `onChanged` handler, after recompiling: `if (!compiled.showQuickTag) { closeQtMenu(false); hideQtButton(); }`. In `bindHistoryRoot`: `hr.addEventListener('scroll', hideQtButton, {passive: true})`.
`quickTagCss`: `#cth-qt-btn{position:fixed;top:var(--cth-qt-top);left:var(--cth-qt-left);z-index:30;width:24px;height:24px;border-radius:6px;border:0;padding:0;background:transparent;color:rgba(255,255,255,.70);display:grid;place-items:center;cursor:pointer} #cth-qt-btn[hidden]{display:none} #cth-qt-btn:hover,#cth-qt-btn:focus-visible{background:rgba(255,255,255,.08)} html.cth-light #cth-qt-btn{color:rgba(0,0,0,.60)} html.cth-light #cth-qt-btn:hover{background:rgba(0,0,0,.06)} #cth-qt-menu{position:fixed;top:var(--cth-qt-top);left:var(--cth-qt-left);z-index:2147482000;width:220px;padding:4px;border-radius:12px;background:#212121;border:1px solid rgba(255,255,255,.12);box-shadow:0 10px 30px rgba(0,0,0,.4);font:600 13px system-ui;color:#fff} html.cth-light #cth-qt-menu{background:#fff;border-color:rgba(0,0,0,.10);color:#000} .cth-qt-list{max-height:min(320px,calc(100vh - 16px));overflow-y:auto} .cth-qt-item{display:flex;align-items:center;gap:8px;height:32px;padding:0 8px;border-radius:8px;cursor:pointer} .cth-qt-item:hover{background:rgba(255,255,255,.08)} html.cth-light .cth-qt-item:hover{background:rgba(0,0,0,.06)} .cth-qt-item[aria-disabled]{opacity:.45;pointer-events:none} .cth-qt-swatch{width:10px;height:10px;border-radius:999px;flex:none} .cth-qt-label{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap} .cth-qt-check{width:14px} .cth-qt-danger{color:#fb4934} html.cth-light .cth-qt-danger{color:#cc241d} #cth-qt-menu [role=separator]{height:1px;margin:4px 0;background:rgba(255,255,255,.12)} .cth-qt-empty{padding:8px;opacity:.6} #cth-qt-btn:focus-visible,#cth-qt-menu :focus-visible{outline:2px solid currentColor;outline-offset:2px}`.

### Task 7: Rename, errors, identity guards, per-chat serialization, overrides, toast
**Files:** Modify `src/content.js`. Test: `tests/test_extension.py`. `_mock_chat_api` gains `patch_abort=False, patch_statuses=None, hold_session=False` and a counter `pn`. In `session()`: `if hold_session and not held: held.append(route); return`. In `patch()`, after the hold check: `pn['n'] += 1`; `if patch_abort: return route.abort()`; `status = patch_statuses[pn['n'] - 1] if patch_statuses else (patch_status or 200)`. Helper: `_pick(page, cid, tag)` = `_open_qt` + click `#cth-qt-menu [data-tag="{tag}"]`. `OK = '{"success": true}'`; `TOKEN = '{"accessToken": "test-token"}'`.
- [ ] **Failing tests:**
  - `test_pick_tag_patches_exact_chat_with_bearer` — pick `[BUG]` on c5 → title `[BUG] plain chat`; one PATCH, URL ends `/backend-api/conversation/c5`, auth `Bearer test-token`, body `{'title': '[BUG] plain chat'}`; `#row-c5` background `rgba(251, 73, 52, 0.12)`.
  - `test_pick_replaces_longest_prefix_and_spaces` — rules `[A]`, `[A][B]`, `[C]`; chats `c2 '[A][B]   two'`, `c3 '[C] three'`; `[C]` on c2 → `[C] two`; Remove on c3 → `three`; `[C]` on c2 again → still 2 PATCHes.
  - `test_rename_keeps_title_text_node` — same `firstChild` before and after, `childNodes.length == 1`.
  - `test_rename_errors_change_nothing[6]` — abort → `Couldn't reach ChatGPT. Nothing changed.`; 401 and 403 → `Sign in to ChatGPT first. Nothing changed.`; 429 → `ChatGPT is rate-limiting requests (HTTP 429). Wait a minute and try again.`; 500 → `ChatGPT refused the rename (HTTP 500). Nothing changed.`; `{'success': False}` → `ChatGPT said the rename didn't go through. Nothing changed.`. Each: alert contains the text, title `plain chat`, no `data-cth` on `#row-c5`.
  - `test_override_survives_remount_and_yields_to_third_title` — after the pick, span `textContent = 'plain chat'` → back to `[BUG] plain chat`; set `[BUG] plain chat` and count characterData mutations for 300 ms → 0; set `renamed elsewhere` then `plain chat` → stays `plain chat`.
  - `test_title_changed_before_pick_aborts` / `test_recycled_anchor_other_id_aborts` — open on c5, then set span `other` / set href `/c/c9`, click `[BUG]` → alert `Title changed — try again`, 0 PATCHes.
  - `test_title_change_while_token_pending_aborts` — `hold_session=True`; pick on c5; set span `other`; `held[0].fulfill(status=200, content_type='application/json', body=TOKEN)` → alert `Title changed — try again`, 0 PATCHes, title `other`.
  - `test_post_request_change_aborts_dom_write[title|href]` — `hold_first_patch=True`; pick on c5; set span `other` / href `/c/c9`; fulfill the held PATCH with `OK` → alert `Title changed — try again`; span is `other` / `plain chat`, no `data-cth`; title variant: set `plain chat`, wait 300 ms → still `plain chat` (no override).
  - `test_overlapping_rename_same_chat_refused` — `hold_first_patch=True`; pick `[BUG]` on c5; `mouse.click(640, 400)`; pick `[TODO]` on c5 → alert `Still saving this chat — try again`, 1 PATCH; fulfill with `OK` → `[BUG] plain chat`.
  - `test_toast_above_overlay_auto_hides_and_pauses` — `_overlay_visible(page)` (active c1 has an overlay rule); pick on c5 → `role=status`; toast `getBoundingClientRect().bottom <= #cth-overlay top - 12 + 0.5`; hover 7 s → visible; mouse to (640, 5), 6.5 s → gone.
- [ ] **Fail → pass → commit:** `RUN 'test_pick or test_rename or test_override or test_title_change or test_recycled or test_post_request or test_overlapping or test_toast'` first FAILS with `Timeout` (no click handler), then PASSES. Then commit `src/content.js tests/test_extension.py` with the message `feat(content): rename chats from the quick tag menu`.
- [ ] **Implement.** Replace `getChatTitleText(a)` with `effectiveTitle(a)` at 894, 1429, 1585 and in `openQtMenu`. In `openQtMenu`, after `qtMenu` is created: `qtMenu.addEventListener('click', e => { const it = e.target.closest('.cth-qt-item'); if (!it || it.hasAttribute('aria-disabled') || qtBusy) return; if (it.dataset.action === 'remove') applyTag(qtBound, null); else if (it.dataset.tag) applyTag(qtBound, it.dataset.tag); });`.
```js
async function renameChat(id, title, stillValid = () => true, staleText = 'Title changed — try again') { if (!CHAT_ID_RE.test(id)) throw new Error(staleText); let token, r;
  try { token = await getAccessToken(); } catch (e) { throw new Error(e instanceof TypeError ? "Couldn't reach ChatGPT. Nothing changed." : 'Sign in to ChatGPT first. Nothing changed.'); }
  if (!stillValid()) throw new Error(staleText); // re-check right before the PATCH
  try { r = await pageFetch(`/backend-api/conversation/${encodeURIComponent(id)}`, {method: 'PATCH', headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'}, body: JSON.stringify({title})}); }
  catch { throw new Error("Couldn't reach ChatGPT. Nothing changed."); } const body = await readJson(r);
  if (r.status === 401 || r.status === 403) throw new Error('Sign in to ChatGPT first. Nothing changed.');
  if (r.status === 429) throw new Error('ChatGPT is rate-limiting requests (HTTP 429). Wait a minute and try again.');
  if (!r.ok) throw new Error(`ChatGPT refused the rename (HTTP ${r.status}). Nothing changed.`);
  if (body?.success === false) throw new Error("ChatGPT said the rename didn't go through. Nothing changed."); }
const titleOverrides = new Map(), qtPending = new Set(); // id -> {old, new}; ids with a rename in flight (survives menu close)
const titleNodeOf = a => { const s = a.querySelector('[data-thread-title="true"] span[dir="auto"], .truncate span[dir="auto"]'); return s?.childNodes.length === 1 && s.firstChild.nodeType === Node.TEXT_NODE ? s.firstChild : null; };
function effectiveTitle(a) { const shown = getChatTitleText(a), id = chatIdOf(a), o = id && titleOverrides.get(id);
  if (!o || shown === o.new) return shown; if (shown !== o.old) { titleOverrides.delete(id); return shown; } // third title: renamed elsewhere
  const node = titleNodeOf(a); if (node) node.nodeValue = o.new;   // stale remount; converges on the next scan
  return o.new; } const titleIs = (id, t) => { const a = findChatAnchorById(id); return !!a && effectiveTitle(a) === t; }; // re-find by id every time
const closeIfBound = (bound, refocus = false) => { if (qtBound === bound) closeQtMenu(refocus); }; // never close a menu opened since for another chat
const busyIfBound = bound => { if (qtBound === bound) setQtBusy(true); };
function setQtBusy(on) { qtBusy = on; for (const n of qtMenu?.querySelectorAll('.cth-qt-item') || []) on ? n.setAttribute('aria-disabled', 'true') : n.removeAttribute('aria-disabled'); }
function commitTitle(id, expected, next) { if (!titleIs(id, expected)) return false; const node = titleNodeOf(findChatAnchorById(id)); if (node) node.nodeValue = next; // never add or remove nodes
  titleOverrides.set(id, {old: expected, new: next}); scheduleSidebarScan(); return true; }
async function applyTag(bound, tag, rules = compiled.rules) { // bound is captured by the caller before any await; this body never reads menu state
  if (!bound || !titleIs(bound.id, bound.title)) { closeIfBound(bound); qtToast('Title changed — try again', {error: true}); return; }
  if (tag !== null && currentPrefixTag(bound.title, rules) === tag) { closeIfBound(bound, true); return; } // current tag: no-op
  const next = computeTaggedTitle(bound.title, tag, rules); if (!next) { closeIfBound(bound); qtToast("Can't leave the title empty.", {error: true}); return; }
  if (qtPending.has(bound.id)) { closeIfBound(bound); qtToast('Still saving this chat — try again', {error: true}); return; } // one mutation per chat
  busyIfBound(bound); qtPending.add(bound.id);
  try { await renameChat(bound.id, next, () => titleIs(bound.id, bound.title)); } catch (e) { closeIfBound(bound); qtToast(e.message, {error: true}); return; } finally { qtPending.delete(bound.id); }
  closeIfBound(bound); if (!commitTitle(bound.id, bound.title, next)) { qtToast('Title changed — try again', {error: true}); return; }
  qtToast(tag === null ? 'Tag removed' : 'Tagged', {undo: {id: bound.id, tagged: next, old: bound.title}}); }
function qtToast(message, {error = false, undo = null} = {}) { document.getElementById(QT_TOAST_ID)?.remove(); clearTimeout(qtToastTimer);
  const t = el('div', {id: QT_TOAST_ID, role: error ? 'alert' : 'status', class: error ? 'cth-qt-error' : ''}, [el('span', {text: message})]);
  if (error) { const x = el('button', {type: 'button', 'aria-label': 'Close', class: 'cth-qt-close', text: '×'}); x.addEventListener('click', () => t.remove()); t.append(x); }
  const ov = document.getElementById(OVERLAY_ID), box = (ov && getComputedStyle(ov).display !== 'none' && ov.getClientRects().length) ? ov : findComposerBox(), r = box?.getBoundingClientRect();
  t.style.setProperty('--cth-qt-bottom', `${r ? innerHeight - r.top + 12 : 24}px`); t.style.setProperty('--cth-qt-center', `${r ? r.left + r.width / 2 : innerWidth / 2}px`);
  document.body.append(t); if (!error) { const arm = () => { clearTimeout(qtToastTimer); qtToastTimer = setTimeout(() => t.remove(), 6000); };
    for (const ev of ['pointerenter', 'focusin']) t.addEventListener(ev, () => clearTimeout(qtToastTimer));
    for (const ev of ['pointerleave', 'focusout']) t.addEventListener(ev, arm); arm(); } return t; }
```
Add to `quickTagCss`: `#cth-qt-toast{position:fixed;bottom:var(--cth-qt-bottom);left:var(--cth-qt-center);transform:translateX(-50%);z-index:2147482000;display:flex;gap:8px;align-items:center;padding:8px 12px;border-radius:12px;background:#212121;color:#fff;border:1px solid rgba(255,255,255,.12);font:600 12px system-ui} html.cth-light #cth-qt-toast{background:#fff;color:#000;border-color:rgba(0,0,0,.10)} #cth-qt-toast.cth-qt-error{border-left:3px solid #fb4934} .cth-qt-close{width:24px;height:24px;border:0;background:transparent;color:inherit;cursor:pointer} #cth-qt-toast button:focus-visible{outline:2px solid currentColor;outline-offset:2px}`.

### Task 8: New tag
**Files:** Modify `src/content.js`. Test: `TestAppShellContentScript`. Helpers: `_stored_rules()` opens `options.html`, reads the stored rules, closes the page; `_new_tag(page, cid, text)` opens the menu, clicks `[data-action=new]`, fills `#cth-qt-menu input`, presses Enter.
- [ ] **Failing tests:**
  - `test_new_tag_trims_creates_rule_and_renames` — New tag on c5 → `placeholder == '[TAG]'`; Escape → `[data-action=new]` back; New tag again, Tab → no `#cth-qt-menu`; `_new_tag(c5, '  [NEW]  ')` → `[NEW] plain chat`; last stored rule `== _rule('[NEW]', '#b8bb26')`.
  - `test_new_tag_length_bounds['' | 'x'*41 | 'x'*40]` — invalid: alert `Tags are 1–40 characters.`, 0 PATCHes, rule count unchanged; 40 chars → `'x'*40 + ' plain chat'`.
  - `test_new_tag_reuses_existing['[BUG]' | 'code']` → `[BUG] plain chat` / `code plain chat`; rule count unchanged. `test_new_tag_rename_failure_keeps_rule` — `patch_status=500` → alert, `plain chat`, last stored tag `[NEW]`.
  - `test_new_tag_keeps_original_chat_across_await` — `hold_first_patch=True`; `_new_tag(c1, '[NEW]')` (PATCH held); `mouse.click(640, 400)`; `_open_qt(page, 'c2')`; `held[0].fulfill(status=200, content_type='application/json', body=OK)` → c1 `[NEW] ship release`; one PATCH, to `/c1`; `#cth-qt-menu[data-cth-chat="c2"]` still open; c2 title unchanged.
  - `TestStatic.test_apply_tag_never_reads_menu_state` — with `src = content.js`: `'qtBound' not in _fn(src, 'applyTag')`; in `t = _fn(src, 'startNewTag')`, `t.index('const bound = qtBound') < t.index('await')`. `_fn` (reused by T10):
```python
    @staticmethod
    def _fn(text, name):  # function source with indentation stripped, by brace matching
        start, depth = text.index(f'function {name}('), 0
        for i in range(text.index('{', start), len(text)):
            depth += {'{': 1, '}': -1}.get(text[i], 0)
            if depth == 0: return '\n'.join(l.strip() for l in text[start:i + 1].splitlines())
```
- [ ] **Fail → pass → commit:** `RUN 'test_new_tag or test_apply_tag_never'` first FAILS with `Timeout … #cth-qt-menu input` and `ValueError: substring not found`, then PASSES. Then commit `src/content.js tests/test_extension.py` with the message `feat(content): create a prefix tag from the quick tag menu`.
- [ ] **Implement.** The click handler gains `else if (it.dataset.action === 'new') startNewTag(it);`. Add:
```js
function startNewTag(item) { const bound = qtBound, input = el('input', {type: 'text', placeholder: '[TAG]', 'aria-label': 'New tag', class: 'cth-qt-input'}); // capture the chat now
  item.replaceWith(input); input.focus(); input.addEventListener('keydown', async e => { if (e.key === 'Tab') { closeIfBound(bound); return; } // let focus move on
    e.stopPropagation(); if (e.key === 'Escape') { e.preventDefault(); input.replaceWith(item); item.focus(); return; }
    if (e.key !== 'Enter' || qtBusy) return; e.preventDefault(); const tag = input.value.trim();
    if (tag.length < 1 || tag.length > 40) { closeIfBound(bound); qtToast('Tags are 1–40 characters.', {error: true}); return; } busyIfBound(bound);
    const res = await sendRuntimeMessage({type: 'addRule', tag}).catch(() => null); // background validates again and persists first
    if (!res?.ok) { closeIfBound(bound); qtToast(res?.error || "Couldn't save the tag. Nothing changed.", {error: true}); return; }
    // compileConfig has DOM side effects, so build the rule directly; storage.onChanged recompiles shortly after.
    const rules = compiled.rules.some(r => r.tag === res.rule.tag) ? compiled.rules : [...compiled.rules, {tag: res.rule.tag, match: 'startsWith', color: res.rule.color, hide: false, overlay: true}];
    await applyTag(bound, res.rule.tag, rules); }); }
```
CSS: `.cth-qt-input{width:100%;height:28px;box-sizing:border-box;padding:0 8px;border-radius:8px;border:1px solid rgba(255,255,255,.12);background:transparent;color:inherit;font:inherit}`.

### Task 9: Undo + legacy smoke test
**Files:** Modify `src/content.js`. Test: `TestAppShellContentScript`, `TestContentScript`.
- [ ] **Failing tests:**
  - `test_undo_restores_title` — pick `[BUG]` on c5 → toast children text `['Tagged', '·', 'Undo']`; click `.cth-qt-undo` → `plain chat`; PATCH titles `['[BUG] plain chat', 'plain chat']`.
  - `test_undo_failure_keeps_tag` — `patch_statuses=[200, 500]` → alert; title stays `[BUG] plain chat`. `test_undo_refused_after_intervening_rename` — set span `renamed elsewhere`, Undo → alert `Title changed — not undone`, 1 PATCH.
  - `TestContentScript.test_legacy_quick_tag_pick_and_undo` — `_configure()`; `_open_chat()`; `_mock_chat_api`; hover `#history a[href="/c/c5"]` → `#cth-qt-btn` visible and its right edge within 4 px of the anchor's right edge minus 8 (legacy fallback, no unrelated button); save the span's `firstChild`; click it, pick `[BUG]` → span `[BUG] plain chat`, same node, one PATCH to `/c5` with `Bearer test-token`; Undo → `plain chat`, 2 PATCHes.
- [ ] **Fail → pass → commit:** `RUN 'test_undo or test_legacy_quick_tag'` first FAILS with `['Tagged'] == ['Tagged', '·', 'Undo']`, then PASSES. Then commit `src/content.js tests/test_extension.py` with the message `feat(content): undo a quick tag rename`.
- [ ] **Implement.** In `qtToast`, before `document.body.append(t)`: `if (undo) { const b = el('button', {type: 'button', class: 'cth-qt-undo', text: 'Undo'}); b.addEventListener('click', () => { t.remove(); undoTag(undo.id, undo.tagged, undo.old); }); t.append(el('span', {text: '·', 'aria-hidden': 'true'}), b); }`. Add:
```js
async function undoTag(id, tagged, old) { if (!titleIs(id, tagged)) { qtToast('Title changed — not undone', {error: true}); return; }
  if (qtPending.has(id)) { qtToast('Still saving this chat — try again', {error: true}); return; } qtPending.add(id);
  try { await renameChat(id, old, () => titleIs(id, tagged), 'Title changed — not undone'); } catch (e) { qtToast(e.message, {error: true}); return; } finally { qtPending.delete(id); }
  const ok = commitTitle(id, tagged, old); qtToast(ok ? 'Undone' : 'Title changed — not undone', {error: !ok}); }
```
CSS: `.cth-qt-undo{padding:4px 12px;border-radius:999px;border:1px solid rgba(255,255,255,.12);background:transparent;color:inherit;font:inherit;cursor:pointer} html.cth-light .cth-qt-undo{border-color:rgba(0,0,0,.10)}`.

### Task 10: unit_test.html copies (after T8)
**Files:** Modify `tests/unit_test.html`. Test: `TestStatic`, `TestUnitTests`.
- [ ] **Failing test** `TestStatic.test_unit_copies_match_source` — for `currentPrefixTag` and `computeTaggedTitle` (content.js), `_fn(unit) == _fn(src)` (`_fn` from T8).
- [ ] **Fail → pass → commit:** `RUN 'TestStatic or TestUnitTests'` first FAILS with `ValueError: substring not found`, then PASSES. Then commit `tests/unit_test.html tests/test_extension.py` with the message `test: unit copies of computeTaggedTitle`.
- [ ] **Implement:** after `buildPrunedFilterSet`, paste `currentPrefixTag` and `computeTaggedTitle` verbatim. Before `// ---- Summary ----`, add:
```js
  group('computeTaggedTitle'); const qtRules = [{tag: '[A]', match: 'startsWith'}, {tag: '[A][B]', match: 'startsWith'}, {tag: '[C]', match: 'startsWith'}, {tag: 'code', match: 'includes'}];
  assert('adds tag', computeTaggedTitle('plain', '[C]', qtRules), '[C] plain'); assert('replaces longest prefix and all spaces', computeTaggedTitle('[A][B]   x', '[C]', qtRules), '[C] x');
  assert('removes tag', computeTaggedTitle('[C]  x', null, qtRules), 'x'); assert('tag-only title', computeTaggedTitle('[A]', '[C]', qtRules), '[C]');
  assert('includes rule never stripped', computeTaggedTitle('code x', '[C]', qtRules), '[C] code x'); assert('current = longest match', currentPrefixTag('[A][B] x', qtRules), '[A][B]');
```

### Task 11: Docs and release 1.3.0
**Files:** both manifests (`"version": "1.3.0"`), `CHANGELOG.md`, `CLAUDE.md`, `wiki/{Usage,Configuration,Privacy,Architecture}{,-zh-CN}.md`.
- [ ] **Failing check:** `python3 scripts/release-check.py --tag v1.3.0` fails with `tag v1.3.0 does not match manifest version 1.2.0`.
- [ ] **Write.** CHANGELOG `## [1.3.0] — 2026-11-02`: **Added** quick tag + Alt+T, New tag, Undo, settings gear, floating settings window, Firefox toolbar action, `showQuickTag`. **Changed** background.js is the only config writer (compare-and-set); the options page re-renders outside changes when it has no unsaved edits, otherwise shows a conflict banner, and retries failed saves; rule cards stack at ≤640 px. Usage (EN + zh-CN, same positions): `## Quick tag` and `## Settings window` before `## Keyboard shortcuts`, plus Alt+T. Configuration: a `showQuickTag` row; a save never overwrites another window's change; the page shows "Settings changed in another window" with Reload. Privacy: renames a chat only when you pick a tag or Undo (`PATCH /backend-api/conversation/{id}`, session token never stored); no new permissions. Architecture: table + mermaid `OPT -- "writeConfig (compare-and-set)" --> BG`, `CS -- "addRule / openSettings" --> BG`, `BG --> CFG`. CLAUDE.md: background.js bullet (one chain: compare-and-set `writeConfig`, `addRule` appends for content.js, migration, `openSettings` + `storage.session`); options.js bullet (one save in flight, re-render only with no unsaved edits, conflict banner with Reload); rename endpoint; quick-tag DOM notes (body-level button, `nodeValue` overrides, one rename per chat); `PALETTE` is duplicated in options.js and background.js.
- [ ] **Verify and commit:** `BUILD && CI=true pytest tests/test_extension.py -v && python3 scripts/check-wiki.py wiki && python3 scripts/release-check.py --tag v1.3.0 && npx --yes web-ext@8.3.0 lint --source-dir dist/firefox --warnings-as-errors=false --self-hosted` must all PASS. Then commit the files above with the message `docs: quick tag and floating settings, release 1.3.0`.

### Task 12: Designer screenshot critique (PM-dispatched, not a developer task)
**Files:** `tests/test_extension.py` (a skip-gated capture test only).
- [ ] **Capture** `TestAppShellContentScript.test_capture_ui_screenshots`, `@pytest.mark.skipif(not os.environ.get('CTH_SCREENSHOTS'), reason='designer capture only')`. For `dark` and `light` (swap the `dark`/`light` class on `<html>`): `_qt_page()` → `#cth-filter-bar` element screenshot `gear-{theme}.png`; `_open_qt(page, 'c2')` → `menu-{theme}.png`; pick `[TODO]` → `toast-{theme}.png`. Then an options page at 400×900 → full-page `options-400.png`. Run `BUILD && CTH_SCREENSHOTS=/tmp/cth-shots CI=true pytest tests/test_extension.py -k test_capture_ui_screenshots -v` → 7 PNGs.
- [ ] **Critique:** the PM sends the PNGs plus the UI brief to fc-designer in critique mode. **Acceptance:** no CRITICAL findings; MAJOR ones become follow-up tasks with tests. Commit the capture test with the message `test: designer screenshot capture`.

## Reconciliation with second design

Second design: blind sketch (Sonnet), compared on 2026-11-03.

| agree | differ | chosen and why |
|---|---|---|
| Body-level button/menu; id+title recheck before PATCH and DOM write; `nodeValue` override until a third title; longest prefix for check/remove; neutral auth text; 6 s Undo refused on changed title; gear/bar thresholds; background validates and persists first; one write chain; focus restore by tag | — | Same (T1, T3, T5–T9). |
| — | Per-chat mutation serialization (theirs) | **Adopted**: `qtBusy` resets on menu close, so a second pick or an Undo could overlap a held PATCH. `qtPending` in `applyTag`/`undoTag`; `test_overlapping_rename_same_chat_refused`. |
| — | Remove the zero-rule init gate (theirs) | **Kept the spec**: it changes the documented "early return by design" and starts observers on zero-rule pages; the toolbar icon covers zero rules; live removal after boot already works. |
| — | Reject ambiguous conflicts (theirs) | **Adopted in cycle 5**: a stale save is refused (`conflict`), writes nothing, and the page shows a banner with Reload; no merge. |
| — | Popup rediscovery after worker restart, `windows.getAll` (theirs) | **Adopted via `storage.session`** (no `tabs` permission needed to read extension URLs); memory fallback for Firefox < 115; popup creation serialized. Tests: `test_refocus_after_worker_restart`, `test_concurrent_opens_create_one_window`. |

**Plan cross-audit (GPT-6 Astra), 12 findings, all adopted:** (1) `applyTag(bound, tag, rules)` with `bound` captured in `startNewTag`, plus `closeIfBound` → `test_new_tag_keeps_original_chat_across_await`. (2) `renameChat(…, stillValid)` re-checks after the token → `test_title_change_while_token_pending_aborts`. (3)–(5) superseded by cycle 5 (no merge, no ids). (6) Toast anchors to the overlay only when it is visible → `test_toast_above_overlay_auto_hides_and_pauses`. (7) Tab closes the New-tag input. (8) Our button stays visible with `aria-expanded=true` while its own menu is open; this is a **deliberate deviation from the brief** (APG: Escape returns focus to the trigger). It hides on native-button pointerdown/Enter/Space and re-checks `aria-expanded` → `test_quick_tag_hides_for_native_row_menu`. (9) `test_post_request_change_aborts_dom_write[title,href]`. (10) Match + colour share one card row. (11) `test_legacy_quick_tag_pick_and_undo`; the "more" lookup skips legacy rows. (12) T12 designer critique.

**Re-audit, cycle 2 (4 CRITICAL; approach changed, not patched):** (A) superseded by cycle 5. (B) `qtSuppressRow` + 600 ms window + any `aria-expanded="true"` button in that row, cleared on another row → `test_quick_tag_hides_for_native_row_menu`. (C) `applyTag(bound, tag, rules)`; static `test_apply_tag_never_reads_menu_state` + the held-PATCH behaviour test. T10 now reuses `_fn` from T8.

**Cycle 3: switched to operations** — superseded by cycle 5.

**Cycle 4: stable ids, idempotent ops, idle re-render** — superseded by cycle 5.

**Cycle 5: replaced merge/op/id machinery with compare-and-set + visible conflict; R6 now "no silently lost settings".** Five audit cycles of merging, operations and ids each produced new races (duplicate-id repair, replay with intervening writes, stale reply after `onChanged`, temporary ids before migration, focused-but-unchanged re-render), so the design is now the smallest safe one. `writeConfig {base, next}` writes only if storage still equals `base`; if storage already equals `next` (a retried write that landed) it is ok; otherwise it returns `conflict` and writes nothing. `addRule` still appends to the freshest value for content.js. options.js has one save in flight (edits meanwhile set `pending` and are sent against the acknowledged base), re-renders outside changes only with no unsaved edits, and otherwise keeps the draft and shows "Settings changed in another window." with Reload; while the banner shows, edits are not sent. Failed messaging retries the same `{base, next}`. Trade-off: concurrent edits in two windows are never merged; the second writer must Reload. Removed: rule ids, the op layer, `mergeConfig`, focus restore, draft-row machinery.

**Cycle 6 (3 local T3 fixes, design unchanged):** `dirty` is cleared only when no edit happened since the write was built (`editSeq++` on every form `input`/`change`, counted in the capture phase; each write carries a local `seq`) → `test_partial_hex_typed_during_held_save_is_not_lost`. The explicit `showQuickTag` change → `autoSave()` listener is added, and its test asserts storage. Echo suppression no longer keeps a permanent `lastSent`: a stored value is ignored only if it equals `base` or equals the in-flight write's `next`; a clean re-render sets `base` → `test_external_restore_of_previous_value_rerenders`.

**Cycle 7 (2 local T3 fixes):** every programmatic render goes through `show()`, which sets `rendering` around `render()`; `autoSave()`, the rows `blur` handler and the edit counter return early while it is set, so blurring a focused row that a re-render removes never saves → `test_rerender_of_focused_row_does_not_save`. `gen` increments on every render from storage (Reload included); each send captures it, and an ok, conflict or failure reply from an older `gen` is dropped (after clearing `inFlight`, then sending any edit made since) → `test_reload_ignores_stale_conflict_reply`. A write from before a Reload no longer counts as "in flight" for echo suppression or the clean re-render.
