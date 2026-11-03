"""
ChatGPT Tag Highlighter — Test Suite
=====================================
Runs unit tests and E2E tests for the browser extension.

Usage:
    # Setup (one-time)
    python3 -m venv .venv
    source .venv/bin/activate
    pip install playwright pytest
    playwright install chromium

    # Run tests
    pytest tests/test_extension.py -v
"""

import json
import os
import re
import tempfile
import time
import pytest
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parent.parent
EXT_PATH = str(ROOT / 'dist' / 'chrome')
UNIT_TEST_PATH = str(ROOT / 'tests' / 'unit_test.html')
STORAGE_KEY = 'tagHighlighterConfigV1'

# CI detection — GitHub Actions and most CI providers set CI=true.
# In CI we use a throwaway profile dir under tempfile so each run is clean.
# Locally we keep the persistent .test-profile so contributors can reuse
# extension state (and, for live ChatGPT tests, login cookies).
IS_CI = os.environ.get('CI', '').lower() in ('1', 'true', 'yes')

# Headless by default so a local run never opens a window or steals focus.
# HEADED=1 shows the browser for debugging.
HEADED = os.environ.get('HEADED', '').lower() in ('1', 'true', 'yes')


def _profile_dir():
    if IS_CI:
        # tmp_path_factory would also work, but we want a stable per-session
        # path so a single browser_context is reused across the whole run.
        return tempfile.mkdtemp(prefix='cth-ci-profile-')
    return str(Path(__file__).parent / '.test-profile')


@pytest.fixture(scope='session')
def browser_context():
    """Launch Chromium with the extension loaded.

    Local dev: persistent profile at tests/.test-profile. CI: throwaway
    temp profile. Both run headless unless HEADED=1. channel='chromium'
    uses full Chromium's new headless mode, which loads MV3 extensions;
    the default headless shell does not.
    """
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        _profile_dir(),
        channel='chromium',
        headless=not HEADED,
        args=[
            f'--disable-extensions-except={EXT_PATH}',
            f'--load-extension={EXT_PATH}',
            '--disable-blink-features=AutomationControlled',
            # Keep the viewport deterministic, headless or headed.
            '--window-size=1280,900',
        ],
        ignore_default_args=['--enable-automation', '--disable-extensions'],
    )
    yield context
    context.close()
    pw.stop()


# Match the 32-char lowercase a–p extension ID portion of an extension URL.
_EXT_ID_RE = re.compile(r'chrome-extension://([a-p]{32})/')


@pytest.fixture(scope='session')
def ext_id(browser_context):
    """Discover the extension ID from the loaded service worker URL.

    More robust than scraping chrome://extensions shadow DOM, which breaks
    on Chrome UI updates. The MV3 service worker registers as soon as the
    extension loads — we either find it already registered or wait for the
    'serviceworker' event.
    """
    sw = next(iter(browser_context.service_workers), None)
    if sw is None:
        try:
            sw = browser_context.wait_for_event('serviceworker', timeout=10_000)
        except Exception as exc:
            raise RuntimeError(
                'Could not discover extension service worker. '
                f'EXT_PATH={EXT_PATH}'
            ) from exc

    m = _EXT_ID_RE.match(sw.url)
    if not m:
        raise RuntimeError(f'Unexpected service worker URL: {sw.url}')
    return m.group(1)


# ============================================================
# Unit Tests — run in-browser via unit_test.html
# ============================================================

class TestUnitTests:
    """Run the in-browser unit tests and check results."""

    def test_all_unit_tests_pass(self, browser_context):
        page = browser_context.new_page()
        page.goto(f'file://{UNIT_TEST_PATH}')
        page.wait_for_timeout(1000)

        results = page.evaluate('window.__testResults')
        page.close()

        assert results is not None, 'Unit test results not found'
        assert results['failed'] == 0, (
            f"{results['failed']}/{results['total']} unit tests failed"
        )
        assert results['passed'] > 0, 'No unit tests ran'
        print(f"  ✓ {results['passed']}/{results['total']} unit tests passed")


# ============================================================
# Options Page Tests
# ============================================================

class TestOptionsPage:
    """Test the options page UI and config persistence."""

    @pytest.fixture(autouse=True)
    def setup(self, browser_context, ext_id):
        self.context = browser_context
        self.ext_id = ext_id
        self.options_url = f'chrome-extension://{ext_id}/options.html'
        self._pages = []
        yield
        for p in self._pages:
            if not p.is_closed():
                p.close()

    def _open_options(self):
        page = self.context.new_page()
        page.goto(self.options_url)
        page.wait_for_timeout(1500)
        return page

    def _get_config(self, page):
        return json.loads(page.evaluate(
            f"new Promise(r => chrome.storage.sync.get('{STORAGE_KEY}', "
            f"d => r(JSON.stringify(d['{STORAGE_KEY}']))))"
        ))

    def _set_config(self, page, config):
        page.evaluate(
            f"new Promise(r => chrome.storage.sync.set("
            f"{{'{STORAGE_KEY}': {json.dumps(config)}}}, r))"
        )

    def test_options_waits_for_loaded_rules_before_autosaving(self):
        page = self.context.new_page()
        try:
            markup = (Path(EXT_PATH) / 'options.html').read_text().replace('<script src="options.js"></script>', '')
            page.set_content(markup)
            page.evaluate("""() => {
                window.writes = [];
                window.browser = {
                    runtime: {sendMessage: async m => { window.writes.push(m); return {ok: true, value: m.next}; }},
                    storage: {onChanged: {addListener() {}}, sync: {
                        get: () => new Promise(resolve => {window.releaseConfig = resolve}),
                        set: async value => {window.writes.push(value)},
                    }},
                };
            }""")
            page.add_script_tag(content=(Path(EXT_PATH) / 'options.js').read_text())
            page.check('#dimUntagged')
            assert page.evaluate('writes.length') == 0, 'loading an empty table must not overwrite stored rules'
            page.evaluate("releaseConfig({tagHighlighterConfigV1:{rules:[{tag:'[SAVED]',color:'#fabd2f'}]}})")
            page.wait_for_function("() => document.querySelector('#rows .tag')?.value === '[SAVED]'")
            page.check('#dimUntagged')
            page.wait_for_function('() => writes.at(-1)?.next?.dimUntagged === true', timeout=3000)
            assert page.evaluate('writes.at(-1).type') == 'writeConfig'
            assert page.evaluate('writes.at(-1).next.rules[0].tag') == '[SAVED]'
            assert page.evaluate('writes.at(-1).next.dimUntagged') is True
        finally:
            page.close()

    def test_removing_last_rule_saves_and_general_settings_still_save(self):
        page = self._open_options()
        try:
            self._set_config(page, {'rules': [{'tag': '[LAST]', 'color': '#fabd2f'}], 'maxChatTurns': 0})
            page.reload()
            page.wait_for_selector('#rows tr')
            page.click('#rows .del')
            page.wait_for_function("async () => (await chrome.storage.sync.get('tagHighlighterConfigV1')).tagHighlighterConfigV1.rules.length === 0", timeout=3000)
            page.check('#dimUntagged')
            page.wait_for_function("async () => (await chrome.storage.sync.get('tagHighlighterConfigV1')).tagHighlighterConfigV1.dimUntagged === true", timeout=3000)
            page.reload()
            page.wait_for_timeout(300)
            assert page.locator('#rows tr').count() == 0
            assert page.is_checked('#dimUntagged')
        finally:
            self._set_config(page, {'rules': [{'tag': '[TEST]', 'match': 'startsWith', 'color': '#fabd2f'}], 'maxChatTurns': 0})
            page.close()

    def test_import_empty_rules_roundtrip_and_reject_blank_only(self):
        page = self._open_options()
        try:
            page.click('#importCfg')
            page.fill('#importText', json.dumps({'rules': [], 'dimUntagged': True}))
            page.click('#importApply')
            page.wait_for_function("async () => (await chrome.storage.sync.get('tagHighlighterConfigV1')).tagHighlighterConfigV1.rules.length === 0", timeout=3000)
            assert page.locator('#rows tr').count() == 0
            page.click('#importCfg')
            page.fill('#importText', json.dumps({'rules': [{'tag': '   '}]}))
            page.click('#importApply')
            assert page.inner_text('#toast') == 'Invalid config'
            assert self._get_config(page)['rules'] == []
        finally:
            self._set_config(page, {'rules': [{'tag': '[TEST]', 'match': 'startsWith', 'color': '#fabd2f'}], 'maxChatTurns': 0})
            page.close()

    def test_import_refreshes_existing_rule_tester_result(self):
        page = self._open_options()
        try:
            self._set_config(page, {'rules': [{'tag': '[OLD]', 'match': 'startsWith', 'color': '#fabd2f'}]})
            page.reload()
            page.wait_for_selector('#rows tr')
            page.fill('#debugTitle', '[OLD] example')
            assert 'WINNER' in page.inner_text('#debugResult')
            page.click('#importCfg')
            page.fill('#importText', json.dumps({'rules': [{'tag': '[NEW]', 'match': 'startsWith', 'color': '#abcdef'}]}))
            page.click('#importApply')
            page.wait_for_function("() => document.querySelector('#rows .tag').value === '[NEW]'")
            result = page.inner_text('#debugResult')
            assert 'WINNER' not in result and page.locator('#debugResult .matchHit').count() == 0
            assert page.inner_text('#debugResult .matchMiss code') == '[NEW]'
            assert page.input_value('#debugTitle') == '[OLD] example'
        finally:
            self._set_config(page, {'rules': [{'tag': '[TEST]', 'match': 'startsWith', 'color': '#fabd2f'}], 'maxChatTurns': 0})
            page.close()

    def test_default_config_seeded(self, browser_context, ext_id):
        """background.js should seed default config on install."""
        page = self._open_options()
        cfg = self._get_config(page)
        page.close()

        assert cfg is not None, 'No config found in storage'
        assert 'rules' in cfg, 'Config missing rules'
        assert isinstance(cfg['rules'], list), 'Rules should be a list'
        assert len(cfg['rules']) >= 1, 'Should have at least 1 default rule'
        assert 'maxChatTurns' in cfg, 'Config missing maxChatTurns'
        assert 'hideNavBar' in cfg, 'Config missing hideNavBar'

    def test_options_renders_rules(self, browser_context, ext_id):
        """Options page should render rule rows from config."""
        page = self._open_options()

        # Set a known config
        self._set_config(page, {
            'rules': [
                {'tag': '[TEST]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False},
                {'tag': '[BUG]', 'match': 'includes', 'color': '#fb4934', 'hide': True},
            ],
            'maxChatTurns': 5,
            'hideNavBar': True,
        })

        page.reload()
        page.wait_for_timeout(1500)

        row_count = page.evaluate("document.querySelectorAll('#rows tr').length")
        assert row_count == 2, f'Expected 2 rule rows, got {row_count}'

        tag0 = page.evaluate("document.querySelector('#rows tr .tag').value")
        assert tag0 == '[TEST]', f'First tag should be [TEST], got {tag0}'

        max_turns = page.evaluate("document.getElementById('maxChatTurns').value")
        assert max_turns == '5', f'Max chat turns should be 5, got {max_turns}'

        hide_nav = page.evaluate("document.getElementById('hideNavBar').checked")
        assert hide_nav is True, 'hideNavBar checkbox should be checked'

        page.close()

    def test_save_persists_config(self, browser_context, ext_id):
        """Changes should auto-save to storage."""
        page = self._open_options()

        # Set a clean config
        self._set_config(page, {
            'rules': [{'tag': '[SAVE-TEST]', 'match': 'startsWith', 'color': '#b8bb26', 'hide': False}],
            'maxChatTurns': 0,
            'hideNavBar': False,
        })
        page.reload()
        page.wait_for_timeout(1500)

        # Modify maxChatTurns in UI
        page.fill('#maxChatTurns', '20')
        page.evaluate("document.getElementById('maxChatTurns').dispatchEvent(new Event('change', {bubbles: true}))")
        page.wait_for_timeout(500)
        # Check hideNavBar
        page.check('#hideNavBar')
        page.wait_for_timeout(500)

        cfg = self._get_config(page)
        page.close()

        assert cfg['maxChatTurns'] == 20, f'Expected maxChatTurns=20, got {cfg["maxChatTurns"]}'
        assert cfg['hideNavBar'] is True, 'hideNavBar should be True after checking'
        assert cfg['rules'][0]['tag'] == '[SAVE-TEST]', 'Rule tag should survive save'

    def test_add_and_delete_row(self, browser_context, ext_id):
        """Adding and deleting rule rows should work."""
        page = self._open_options()

        self._set_config(page, {
            'rules': [{'tag': '[A]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False}],
            'maxChatTurns': 0,
            'hideNavBar': True,
        })
        page.reload()
        page.wait_for_timeout(1500)

        initial_rows = page.evaluate("document.querySelectorAll('#rows tr').length")
        assert initial_rows == 1

        # Add a row
        page.click('#addRow')
        page.wait_for_timeout(500)
        after_add = page.evaluate("document.querySelectorAll('#rows tr').length")
        assert after_add == 2, f'Expected 2 rows after add, got {after_add}'

        # Delete the first row
        page.click('#rows tr:first-child .del')
        page.wait_for_timeout(500)
        after_delete = page.evaluate("document.querySelectorAll('#rows tr').length")
        assert after_delete == 1, f'Expected 1 row after delete, got {after_delete}'

        page.close()

    def test_import_applies_config(self, browser_context, ext_id):
        """Import should parse JSON, persist, and re-render."""
        page = self._open_options()
        page.click('#importCfg')
        page.wait_for_timeout(300)

        new_cfg = {
            'rules': [{'tag': '[IMP]', 'match': 'includes', 'color': '#b8bb26', 'hide': False}],
            'maxChatTurns': 7, 'hideNavBar': False,
        }
        page.fill('#importText', json.dumps(new_cfg))
        page.click('#importApply')
        page.wait_for_timeout(500)

        cfg = self._get_config(page)
        page.close()
        assert cfg['rules'][0]['tag'] == '[IMP]'
        assert cfg['maxChatTurns'] == 7

    def test_import_rejects_invalid_json(self, browser_context, ext_id):
        """Import should show error toast for invalid JSON."""
        page = self._open_options()
        page.click('#importCfg')
        page.wait_for_timeout(300)
        page.fill('#importText', 'not json')
        page.click('#importApply')
        page.wait_for_timeout(500)

        toast_text = page.evaluate("document.getElementById('toast').textContent")
        page.close()
        assert 'Invalid' in toast_text

    def test_drag_reorder_saves(self, browser_context, ext_id):
        """Reordering rows should auto-save the new order."""
        page = self._open_options()
        self._set_config(page, {
            'rules': [
                {'tag': '[FIRST]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False},
                {'tag': '[SECOND]', 'match': 'startsWith', 'color': '#fb4934', 'hide': False},
            ],
            'maxChatTurns': 0, 'hideNavBar': True,
        })
        page.reload()
        page.wait_for_timeout(1500)

        tag0 = page.evaluate("document.querySelectorAll('#rows tr .tag')[0].value")
        assert tag0 == '[FIRST]'

        # Simulate reorder via JS (drag API is hard in Playwright) then trigger auto-save
        page.evaluate("""
            const rows = document.getElementById('rows');
            const trs = rows.querySelectorAll('tr');
            rows.insertBefore(trs[1], trs[0]);
            // Trigger change from a child element so event delegation works
            rows.querySelectorAll('tr')[0].querySelector('.tag')
                .dispatchEvent(new Event('change', {bubbles: true}));
        """)
        page.wait_for_timeout(500)

        cfg = self._get_config(page)
        page.close()
        assert cfg['rules'][0]['tag'] == '[SECOND]'
        assert cfg['rules'][1]['tag'] == '[FIRST]'

    def test_color_normalized_to_hex(self, browser_context, ext_id):
        """Saving should normalize all colors to #RRGGBB hex."""
        page = self._open_options()

        # Set config with a legacy color name
        self._set_config(page, {
            'rules': [{'tag': '[COLOR]', 'match': 'startsWith', 'color': 'gruvboxRed', 'hide': False}],
            'maxChatTurns': 0,
            'hideNavBar': True,
        })
        page.reload()
        page.wait_for_timeout(1500)

        # The init migration should have normalized to hex
        cfg = self._get_config(page)
        page.close()

        assert cfg['rules'][0]['color'] == '#fb4934', (
            f"Expected #fb4934, got {cfg['rules'][0]['color']}"
        )

    def test_overlay_field_persists(self, browser_context, ext_id):
        """Overlay toggle should persist in config."""
        page = self._open_options()
        self._set_config(page, {
            'rules': [{'tag': '[OV]', 'match': 'startsWith', 'color': '#fabd2f',
                        'hide': False, 'overlay': True}],
            'maxChatTurns': 0, 'hideNavBar': True,
        })
        page.reload()
        page.wait_for_timeout(1500)

        page.uncheck('#rows tr:first-child .overlay')
        page.wait_for_timeout(500)

        cfg = self._get_config(page)
        page.close()
        assert cfg['rules'][0]['overlay'] is False

    def test_overlay_defaults_true(self, browser_context, ext_id):
        """Rules without overlay field should default to true after migration."""
        page = self._open_options()
        self._set_config(page, {
            'rules': [{'tag': '[DEF]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False}],
            'maxChatTurns': 0, 'hideNavBar': True,
        })
        page.reload()
        page.wait_for_timeout(1500)

        cfg = self._get_config(page)
        page.close()
        assert cfg['rules'][0].get('overlay') is True

    def test_row_numbers_displayed(self, browser_context, ext_id):
        """Row numbers should be displayed for each rule."""
        page = self._open_options()
        self._set_config(page, {
            'rules': [
                {'tag': '[A]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False, 'overlay': True},
                {'tag': '[B]', 'match': 'startsWith', 'color': '#fb4934', 'hide': False, 'overlay': True},
            ],
            'maxChatTurns': 0, 'hideNavBar': True,
        })
        page.reload()
        page.wait_for_timeout(1500)

        num1 = page.evaluate("document.querySelectorAll('#rows tr .rowNum')[0].textContent")
        num2 = page.evaluate("document.querySelectorAll('#rows tr .rowNum')[1].textContent")
        page.close()
        assert num1 == '1', f'First row should be 1, got {num1}'
        assert num2 == '2', f'Second row should be 2, got {num2}'

    def test_row_numbers_update_on_delete(self, browser_context, ext_id):
        """Row numbers should update after deleting a row."""
        page = self._open_options()
        self._set_config(page, {
            'rules': [
                {'tag': '[A]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False},
                {'tag': '[B]', 'match': 'startsWith', 'color': '#fb4934', 'hide': False},
                {'tag': '[C]', 'match': 'startsWith', 'color': '#b8bb26', 'hide': False},
            ],
            'maxChatTurns': 0, 'hideNavBar': True,
        })
        page.reload()
        page.wait_for_timeout(1500)

        # Delete first row
        page.click('#rows tr:first-child .del')
        page.wait_for_timeout(300)

        num1 = page.evaluate("document.querySelectorAll('#rows tr .rowNum')[0].textContent")
        num2 = page.evaluate("document.querySelectorAll('#rows tr .rowNum')[1].textContent")
        page.close()
        assert num1 == '1', f'After delete, first should be 1, got {num1}'
        assert num2 == '2', f'After delete, second should be 2, got {num2}'

    def test_rule_tester_matches(self, browser_context, ext_id):
        """Rule tester should show which rule matches a typed title."""
        page = self._open_options()
        self._set_config(page, {
            'rules': [
                {'tag': '[TODO]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False},
                {'tag': 'bug', 'match': 'includes', 'color': '#fb4934', 'hide': False},
            ],
            'maxChatTurns': 0, 'hideNavBar': True,
        })
        page.reload()
        page.wait_for_timeout(1500)

        # Test startsWith match
        page.fill('#debugTitle', '[TODO] Fix build')
        page.wait_for_timeout(300)
        result = page.evaluate("document.getElementById('debugResult').textContent")
        page.close()
        assert '#1' in result and 'WINNER' in result, f'Should match rule #1, got: {result}'

    def test_rule_tester_no_match(self, browser_context, ext_id):
        """Rule tester should show no match for unmatched title."""
        page = self._open_options()
        self._set_config(page, {
            'rules': [
                {'tag': '[TODO]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False},
            ],
            'maxChatTurns': 0, 'hideNavBar': True,
        })
        page.reload()
        page.wait_for_timeout(1500)

        page.fill('#debugTitle', 'Random chat title')
        page.wait_for_timeout(300)
        result = page.evaluate("document.getElementById('debugResult').textContent")
        page.close()
        assert 'No rule matches' in result, f'Should show no match, got: {result}'

    def test_rule_tester_includes_match(self, browser_context, ext_id):
        """Rule tester should match includes rules."""
        page = self._open_options()
        self._set_config(page, {
            'rules': [
                {'tag': '[TODO]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False},
                {'tag': 'code', 'match': 'includes', 'color': '#83a598', 'hide': False},
            ],
            'maxChatTurns': 0, 'hideNavBar': True,
        })
        page.reload()
        page.wait_for_timeout(1500)

        page.fill('#debugTitle', 'My code review')
        page.wait_for_timeout(300)
        result = page.evaluate("document.getElementById('debugResult').textContent")
        page.close()
        assert '#2' in result and 'WINNER' in result, f'Should match rule #2 (code includes), got: {result}'

    def test_rule_tester_does_not_execute_injected_html(self, browser_context, ext_id):
        """CodeQL #1 (js/xss-through-dom): rule tester must escape user input.

        The debugTitle field and rule .tag inputs both flow into innerHTML in
        runDebugTest(). A payload that would execute (e.g. <img onerror=>) must
        be rendered as literal text, never materialized as DOM elements.
        """
        page = self._open_options()
        page.evaluate("window.__pwned = false")

        # 1) Malicious title in the 'no match' branch.
        self._set_config(page, {
            'rules': [{'tag': '[TODO]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False}],
            'maxChatTurns': 0, 'hideNavBar': True,
        })
        page.reload()
        page.wait_for_timeout(1500)

        payload_title = '<img src=x onerror="window.__pwned=true">'
        page.fill('#debugTitle', payload_title)
        page.wait_for_timeout(400)

        injected_imgs = page.evaluate(
            "document.getElementById('debugResult').querySelectorAll('img').length"
        )
        result_text = page.evaluate("document.getElementById('debugResult').textContent")
        pwned_after_title = page.evaluate("window.__pwned")

        assert injected_imgs == 0, f'Title payload materialized {injected_imgs} <img> elements'
        assert not pwned_after_title, f'XSS via title executed (window.__pwned={pwned_after_title!r})'
        assert payload_title in result_text, (
            f'Payload should appear as literal text, got: {result_text!r}'
        )

        # 2) Malicious tag in the 'winner' branch (via Import — the realistic
        # vector since users paste shared configs from untrusted sources).
        page.evaluate("window.__pwned = false")
        page.click('#importCfg')
        page.wait_for_timeout(200)
        payload_tag = '<svg onload="window.__pwned=true">'
        import_cfg = {
            'rules': [{'tag': payload_tag, 'match': 'startsWith',
                       'color': '#fabd2f', 'hide': False, 'overlay': True}],
            'maxChatTurns': 0, 'hideNavBar': True,
        }
        page.fill('#importText', json.dumps(import_cfg))
        page.click('#importApply')
        page.wait_for_timeout(400)

        # Type something that triggers the matchHit branch (startsWith payload_tag).
        page.fill('#debugTitle', payload_tag + ' some chat title')
        page.wait_for_timeout(400)

        injected_svgs = page.evaluate(
            "document.getElementById('debugResult').querySelectorAll('svg').length"
        )
        result_text2 = page.evaluate("document.getElementById('debugResult').textContent")
        pwned_after_tag = page.evaluate("window.__pwned")
        page.close()

        assert injected_svgs == 0, f'Tag payload materialized {injected_svgs} <svg> elements'
        assert not pwned_after_tag, f'XSS via imported tag executed (window.__pwned={pwned_after_tag!r})'
        assert payload_tag in result_text2, (
            f'Tag payload should appear as literal text, got: {result_text2!r}'
        )

    def test_import_with_all_fields(self, browser_context, ext_id):
        """Import should handle all config fields including overlay, dimUntagged, showBadge."""
        page = self._open_options()
        page.click('#importCfg')
        page.wait_for_timeout(300)

        new_cfg = {
            'rules': [{'tag': '[X]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False, 'overlay': False}],
            'maxChatTurns': 5, 'hideNavBar': False, 'dimUntagged': True, 'showBadge': False,
            'showDeleteUntagged': True,
        }
        page.fill('#importText', json.dumps(new_cfg))
        page.click('#importApply')
        page.wait_for_timeout(500)

        cfg = self._get_config(page)
        page.close()
        assert cfg['rules'][0]['overlay'] is False
        assert cfg['dimUntagged'] is True
        assert cfg['showBadge'] is False
        assert cfg['showDeleteUntagged'] is True
        assert cfg['hideNavBar'] is False
        assert cfg['maxChatTurns'] == 5

    # ---- compare-and-set client: options.js against the real background.js in one page ----

    def _fresh(self, cfg):
        page = self._open_options()
        self._pages.append(page)
        self._set_config(page, cfg)
        page.reload()
        page.wait_for_selector('#rows tr')
        return page

    def _opts(self, cfg, setup='', with_bg=False, clock=False, delay=0):
        """Stubbed options page; optionally the real background.js in the same page."""
        page = self.context.new_page()
        self._pages.append(page)
        markup = (Path(EXT_PATH) / 'options.html').read_text()
        link = '<link rel="stylesheet" href="options.css" />'
        assert link in markup
        css = (Path(EXT_PATH) / 'options.css').read_text()
        page.set_content(markup.replace('<script src="options.js"></script>', '').replace(link, f'<style>{css}</style>'))
        if clock:
            page.clock.install()
        page.evaluate(_BG_HARNESS, [{STORAGE_KEY: cfg}, delay])
        if setup:
            page.evaluate(f'() => {{ {setup} }}')  # statement body, never an auto-invoked expression
        for name in (['background.js'] if with_bg else []) + ['options.js']:
            page.add_script_tag(content=(Path(EXT_PATH) / name).read_text())
        if not clock:
            page.wait_for_selector('#rows tr')
        return page

    # Statement bodies for _opts(setup=...).
    LOG = 'window.msgs = []; const real = browser.runtime.sendMessage; browser.runtime.sendMessage = m => { msgs.push(structuredClone(m)); return real(m); };'
    HOLD = ('window.releases = []; const real = browser.runtime.sendMessage; let first = true;'
            ' browser.runtime.sendMessage = m => { if (!first) return real(m); first = false; return new Promise(r => releases.push(() => r(real(m)))); };')
    # Holds the first request before it is sent, then holds its reply: releases[0]() sends, releases[1]() answers.
    HOLD_REQ_REPLY = ('window.releases = []; const real = browser.runtime.sendMessage; let first = true;'
                      ' browser.runtime.sendMessage = m => { if (!first) return real(m); first = false;'
                      ' return new Promise(go => releases.push(go)).then(() => real(m)).then(r => new Promise(ok => releases.push(() => ok(r)))); };')

    @staticmethod
    def _toast_visible(page):
        time.sleep(0.3)  # the opacity transition runs on real time, not the page's fake clock
        return page.evaluate("() => { const t = document.getElementById('toast'); return t.classList.contains('show') && Number(getComputedStyle(t).opacity) > 0; }")

    def _banner(self, page):
        page.wait_for_selector('#conflict', state='visible', timeout=3000)
        assert page.inner_text('#conflict').startswith('Settings changed in another window.')
        assert page.inner_text('#conflictReload') == 'Reload'

    def _row_tags(self, page):
        return page.evaluate("[...document.querySelectorAll('#rows .tag')].map(i => i.value)")

    def _add(self, page, tag):
        return page.evaluate('t => send({type: "addRule", tag: t})', tag)

    def test_save_sends_cas_write(self):
        page = self._opts(_full([_rule('[A]')]), with_bg=True, setup=self.LOG)
        page.check('#dimUntagged')
        page.wait_for_function('() => cfg().dimUntagged === true', timeout=3000)
        assert page.evaluate('msgs') == [{'type': 'writeConfig', 'base': _full([_rule('[A]')]), 'next': {**_full([_rule('[A]')]), 'dimUntagged': True}}]
        assert page.evaluate("count('set')") == 1

    MUTE = 'window.muted = false; const realFire = fire; window.fire = (n, ...a) => { if (n === "changed" && muted) return; realFire(n, ...a); };'

    def test_conflict_reply_alone_shows_banner(self):
        page = self._opts(_full([_rule('[A]')]), with_bg=True, setup=self.HOLD + ' ' + self.MUTE)
        page.check('#dimUntagged')            # held before dispatch
        page.evaluate('muted = true')         # this page never hears about the next change
        self._add(page, '[NEW]')
        assert page.is_hidden('#conflict')
        page.evaluate('releases[0]()')        # only the conflict reply can raise the banner now
        self._banner(page)
        assert page.is_checked('#dimUntagged')
        assert self._row_tags(page) == ['[A]']
        assert _tags(page.evaluate('cfg()')) == ['[A]', '[NEW]']
        assert page.evaluate('cfg().dimUntagged') is False
        assert page.evaluate("count('set')") == 1
        assert page.text_content('#toast') != 'Auto-saved ✓'

    def test_external_change_rerenders_when_clean(self):
        page = self._opts(_full([_rule('[A]')]), with_bg=True)
        self._add(page, '[NEW]')
        page.wait_for_function("() => document.querySelectorAll('#rows tr').length === 2", timeout=3000)
        assert page.is_hidden('#conflict')

    def _dirty_then_external_add(self, page):
        page.focus('#rows .tag')
        page.keyboard.press('End')
        page.keyboard.type('Q')
        self._add(page, '[NEW]')
        self._banner(page)
        assert self._row_tags(page) == ['[A]Q']

    def test_external_change_while_dirty_shows_banner_keeps_draft_and_writes_nothing(self):
        page = self._opts(_full([_rule('[A]')]), with_bg=True)
        self._dirty_then_external_add(page)
        page.click('#debugTitle')
        page.wait_for_timeout(300)
        self._banner(page)
        assert _tags(page.evaluate('cfg()')) == ['[A]', '[NEW]']
        assert page.evaluate("count('set')") == 1

    def test_reload_discards_draft_and_shows_stored(self):
        page = self._opts(_full([_rule('[A]')]), with_bg=True)
        self._dirty_then_external_add(page)
        page.click('#conflictReload')
        page.wait_for_function("() => document.querySelectorAll('#rows tr').length === 2", timeout=3000)
        assert self._row_tags(page) == ['[A]', '[NEW]']
        assert page.is_hidden('#conflict')
        page.check('#dimUntagged')
        page.wait_for_function('() => cfg().dimUntagged === true', timeout=3000)
        assert _tags(page.evaluate('cfg()')) == ['[A]', '[NEW]']

    def test_toggle_on_then_off_while_held_ends_false(self):
        page = self._opts(_full([_rule('[A]')]), with_bg=True, setup=self.HOLD)
        page.check('#dimUntagged')
        page.uncheck('#dimUntagged')
        page.evaluate('releases[0]()')
        page.wait_for_function("() => count('set') === 2", timeout=3000)
        assert page.evaluate('cfg().dimUntagged') is False
        assert not page.is_checked('#dimUntagged')
        assert page.is_hidden('#conflict')

    def test_held_save_then_external_add_conflicts_visibly(self):
        page = self._opts(_full([_rule('[A]')]), with_bg=True, setup=self.HOLD)
        page.check('#dimUntagged')
        self._add(page, '[NEW]')
        self._banner(page)
        page.evaluate('releases[0]()')
        page.wait_for_timeout(300)
        self._banner(page)
        assert _tags(page.evaluate('cfg()')) == ['[A]', '[NEW]']
        assert page.evaluate('cfg().dimUntagged') is False
        assert page.is_checked('#dimUntagged')

    def test_messaging_failure_keeps_draft_and_retries_same_write(self):
        page = self._opts(_full([_rule('[A]')]), clock=True, setup=(
            "window.sent = []; browser.runtime.sendMessage = async m => { sent.push(JSON.stringify(m));"
            " if (sent.length <= 3) throw new Error('down'); return {ok: true, value: m.next}; };"))
        page.clock.run_for(50)
        page.click('#dimUntagged')
        page.clock.run_for(10)
        assert page.evaluate('sent.length') == 1
        assert page.text_content('#toast') == 'Not saved — retrying'
        assert self._toast_visible(page)
        page.clock.run_for(1000)
        assert page.evaluate('sent.length') == 2
        page.clock.run_for(3000)
        assert page.evaluate('sent.length') == 3
        assert self._toast_visible(page)
        page.clock.run_for(10000)
        assert page.evaluate('sent.length') == 3
        assert self._toast_visible(page), 'the retry toast stays up until a save succeeds'
        assert page.evaluate('sent[0] === sent[1] && sent[1] === sent[2]') is True
        assert page.is_checked('#dimUntagged')
        assert page.evaluate("count('set')") == 0
        page.click('#lazyRenderTurns')
        page.clock.run_for(10)
        assert page.evaluate('sent[3] === sent[0]') is True
        fifth = json.loads(page.evaluate('sent[4]'))
        assert fifth['next']['lazyRenderTurns'] is False and fifth['base']['dimUntagged'] is True
        assert page.text_content('#toast') == 'Auto-saved ✓'

    def test_conflict_stops_automatic_retries(self):
        page = self._opts(_full([_rule('[A]')]), with_bg=True, clock=True, setup=(
            "const real = browser.runtime.sendMessage; let n = 0;"
            " browser.runtime.sendMessage = m => (++n === 1 ? Promise.reject(new Error('down')) : real(m));"))
        page.clock.run_for(50)
        page.evaluate('window.orig = structuredClone(cfg())')
        page.click('#dimUntagged')            # first save is rejected; a retry is scheduled for 1 s
        page.clock.run_for(10)
        assert page.text_content('#toast') == 'Not saved — retrying'
        page.evaluate("() => { const c = cfg(); send({type: 'writeConfig', base: c, next: {...c, maxChatTurns: 5}}); }")
        page.clock.run_for(10)
        self._banner(page)
        page.evaluate("() => { send({type: 'writeConfig', base: cfg(), next: orig}); }")  # restore the original
        page.clock.run_for(10)
        assert page.evaluate('cfg().maxChatTurns') == 0
        page.clock.run_for(10000)             # past every retry delay
        assert page.evaluate("count('set')") == 2, 'only the two external writes'
        assert page.evaluate('cfg().dimUntagged') is False
        self._banner(page)
        assert page.is_checked('#dimUntagged')

    def test_partial_hex_typed_during_held_save_is_not_lost(self):
        page = self._opts(_full([_rule('[A]', '#999999')]), with_bg=True, setup=self.HOLD)
        page.check('#dimUntagged')
        page.fill('#rows .hex', '#12')
        page.evaluate('releases[0]()')
        page.wait_for_function("() => count('set') === 1", timeout=3000)
        self._add(page, '[NEW]')
        self._banner(page)
        assert page.input_value('#rows .hex') == '#12'
        assert page.evaluate('cfg().rules[0].color') == '#999999'
        assert _tags(page.evaluate('cfg()')) == ['[A]', '[NEW]']
        assert page.evaluate("count('set')") == 2

    def test_external_restore_of_previous_value_rerenders(self):
        page = self._opts(_full([_rule('[A]')]), with_bg=True)
        page.check('#dimUntagged')
        page.wait_for_function('() => cfg().dimUntagged === true', timeout=3000)
        page.wait_for_function("() => document.getElementById('toast').textContent === 'Auto-saved ✓'", timeout=3000)
        flip = "v => { const c = cfg(); return send({type: 'writeConfig', base: c, next: {...c, dimUntagged: v}}); }"
        assert page.evaluate(flip, False)['ok'] is True
        page.wait_for_function("() => !document.getElementById('dimUntagged').checked", timeout=3000)
        assert page.is_hidden('#conflict')
        assert page.evaluate(flip, True)['ok'] is True
        page.wait_for_function("() => document.getElementById('dimUntagged').checked", timeout=3000)
        assert page.is_hidden('#conflict')

    def test_rerender_of_focused_row_does_not_save(self):
        page = self._opts(_full([_rule('[A]')]), with_bg=True, setup=self.LOG)
        page.focus('#rows .hex')
        self._add(page, '[NEW]')
        page.wait_for_function("() => document.querySelectorAll('#rows tr').length === 2", timeout=3000)
        assert self._row_tags(page)[1] == '[NEW]'
        page.wait_for_timeout(500)
        assert page.evaluate('msgs') == []
        assert _tags(page.evaluate('cfg()')) == ['[A]', '[NEW]']
        assert page.is_hidden('#conflict')

    def test_reload_ignores_stale_conflict_reply(self):
        page = self._opts(_full([_rule('[A]')]), with_bg=True, delay=50, setup=self.HOLD_REQ_REPLY)
        page.check('#dimUntagged')            # write built against [A]; request held before dispatch
        self._add(page, '[X]')                 # lands first, so the held write must conflict
        page.evaluate('releases[0]()')         # dispatch the held write; its (conflict) reply is held
        page.wait_for_function('() => releases.length === 2', timeout=3000)
        self._add(page, '[Y]')
        self._banner(page)
        page.click('#conflictReload')
        page.wait_for_function("() => document.querySelectorAll('#rows tr').length === 3", timeout=3000)
        assert self._row_tags(page) == ['[A]', '[X]', '[Y]']
        assert page.is_hidden('#conflict')
        page.evaluate('releases[1]()')
        page.wait_for_timeout(300)
        assert self._row_tags(page) == ['[A]', '[X]', '[Y]']
        assert page.is_hidden('#conflict')
        assert not page.is_checked('#dimUntagged')
        assert _tags(page.evaluate('cfg()')) == ['[A]', '[X]', '[Y]']
        assert page.evaluate('cfg().dimUntagged') is False

    def test_own_echo_not_a_conflict(self):
        page = self._opts(_full([_rule('[A]')]), with_bg=True)
        page.evaluate("() => { window.changes = 0; browser.storage.onChanged.addListener(() => { changes++; }); document.querySelector('#rows tr').dataset.mark = '1'; }")
        page.check('#dimUntagged')
        page.wait_for_timeout(800)
        assert page.evaluate('changes') == 1
        assert page.evaluate("document.querySelector('#rows tr').dataset.mark") == '1'
        assert page.is_hidden('#conflict')

    # chrome.storage hands back objects with sorted keys; the plain harness keeps insertion order.
    SORTED_STORAGE = ('const sortKeys = v => v === undefined ? v : JSON.parse(JSON.stringify(v, (k, x) => (x && typeof x === "object" && !Array.isArray(x))'
                      ' ? Object.fromEntries(Object.keys(x).sort().map(key => [key, x[key]])) : x));'
                      ' const get = browser.storage.sync.get; browser.storage.sync.get = async k => sortKeys(await get(k));'
                      ' const realFire = fire; window.fire = (n, ch, area) => realFire(n, n === "changed"'
                      ' ? Object.fromEntries(Object.entries(ch).map(([k, c]) => [k, {oldValue: sortKeys(c.oldValue), newValue: sortKeys(c.newValue)}])) : ch, area);')

    def test_sorted_key_storage_echo_not_a_conflict(self):
        page = self._opts(_full([_rule('[A]')]), with_bg=True, setup=self.SORTED_STORAGE)
        page.check('#dimUntagged')
        page.wait_for_function('() => cfg().dimUntagged === true', timeout=3000)
        page.wait_for_function("() => document.getElementById('toast').textContent === 'Auto-saved ✓'", timeout=3000)
        assert page.is_hidden('#conflict')
        page.uncheck('#showBadge')
        page.wait_for_function('() => cfg().showBadge === false', timeout=3000)
        assert page.is_hidden('#conflict')

    HOLD_REPLY = ('window.releases = []; const real = browser.runtime.sendMessage; let first = true;'
                  ' browser.runtime.sendMessage = m => { if (!first) return real(m); first = false;'
                  ' return real(m).then(r => new Promise(ok => releases.push(() => ok(r)))); };')

    def test_pending_resend_keeps_uncommitted_hex_draft(self):
        page = self._opts(_full([_rule('[A]', '#fabd2f')]), with_bg=True, setup=self.HOLD)
        page.check('#dimUntagged')            # held before dispatch
        page.uncheck('#showBadge')            # queued behind it
        page.fill('#rows .hex', '#12')        # typed, not committed (no blur)
        page.evaluate('releases[0]()')
        page.wait_for_function("() => count('set') === 2", timeout=3000)
        assert page.evaluate('cfg().showBadge') is False
        assert page.evaluate('cfg().rules[0].color') == '#fabd2f', 'a partial hex must not persist the fallback colour'
        self._add(page, '[NEW]')
        self._banner(page)
        assert page.input_value('#rows .hex') == '#12'

    def _drag_first_row_below_second(self, page, mid_drag):
        handle = page.locator('#rows tr').nth(0).locator('.dragHandle').bounding_box()
        second = page.locator('#rows tr').nth(1).bounding_box()
        page.mouse.move(handle['x'] + handle['width'] / 2, handle['y'] + handle['height'] / 2)
        page.mouse.down()
        page.mouse.move(second['x'] + 40, second['y'] + second['height'] * 0.75, steps=8)
        mid_drag()
        second = page.locator('#rows tr').nth(1).bounding_box()  # the banner may have shifted the rows
        page.mouse.move(second['x'] + 42, second['y'] + second['height'] * 0.8, steps=2)
        page.mouse.up()
        page.wait_for_timeout(300)

    def test_external_change_during_drag_shows_banner(self):
        page = self._opts(_full([_rule('[A]'), _rule('[B]', '#fb4934')]), with_bg=True)

        def external_add():
            self._add(page, '[NEW]')
            page.wait_for_timeout(100)

        self._drag_first_row_below_second(page, external_add)
        self._banner(page)
        assert self._row_tags(page) == ['[B]', '[A]']
        assert _tags(page.evaluate('cfg()')) == ['[A]', '[B]', '[NEW]']
        assert page.evaluate("count('set')") == 1

    def test_reload_during_drag_drops_nothing(self):
        page = self._opts(_full([_rule('[A]'), _rule('[B]', '#fb4934')]), with_bg=True)

        def external_add_then_reload():
            self._add(page, '[NEW]')
            page.wait_for_timeout(100)
            page.evaluate("document.getElementById('conflictReload').click()")
            page.wait_for_function("() => document.querySelectorAll('#rows tr').length === 3", timeout=3000)

        self._drag_first_row_below_second(page, external_add_then_reload)
        assert self._row_tags(page) == ['[A]', '[B]', '[NEW]']
        assert _tags(page.evaluate('cfg()')) == ['[A]', '[B]', '[NEW]']
        self._add(page, '[LATER]')            # the drag is over: a clean page simply re-renders
        page.wait_for_function("() => document.querySelectorAll('#rows tr').length === 4", timeout=3000)
        assert self._row_tags(page) == ['[A]', '[B]', '[NEW]', '[LATER]']
        assert page.is_hidden('#conflict')

    def test_ok_reply_with_pending_during_conflict_writes_nothing(self):
        page = self._opts(_full([_rule('[A]')]), with_bg=True, setup=self.HOLD_REPLY)
        page.check('#dimUntagged')            # lands; its ok reply is held
        page.wait_for_function("() => releases.length === 1 && count('set') === 1", timeout=3000)
        page.uncheck('#showBadge')            # pending behind the held reply
        turns = "v => { const c = cfg(); return send({type: 'writeConfig', base: c, next: {...c, maxChatTurns: v}}); }"
        assert page.evaluate(turns, 5)['ok'] is True    # external change
        self._banner(page)
        assert page.evaluate(turns, 0)['ok'] is True    # external restore of the first save's value
        page.evaluate('releases[0]()')
        page.wait_for_timeout(300)
        assert page.evaluate("count('set')") == 3, 'the banner suspends saving'
        assert page.text_content('#toast') != 'Auto-saved ✓'
        self._banner(page)
        assert not page.is_checked('#showBadge')
        assert page.evaluate('cfg().showBadge') is True

    def test_adopted_init_conflict_clears_banner(self):
        raw = {k: v for k, v in _full([_rule('[A]')]).items() if k != 'showQuickTag'}
        page = self._opts(raw, with_bg=True, delay=200, setup=self.HOLD)
        page.wait_for_function('() => releases.length === 1', timeout=3000)   # options' init migration write, held
        page.wait_for_function('() => cfg().showQuickTag === true', timeout=3000)  # background migration landed
        self._add(page, '[NEW]')
        self._banner(page)
        page.evaluate('releases[0]()')
        page.wait_for_function("() => document.querySelectorAll('#rows tr').length === 2", timeout=3000)
        assert self._row_tags(page) == ['[A]', '[NEW]']
        assert page.is_hidden('#conflict')
        page.check('#dimUntagged')
        page.wait_for_function('() => cfg().dimUntagged === true', timeout=3000)
        assert _tags(page.evaluate('cfg()')) == ['[A]', '[NEW]']

    @pytest.mark.parametrize('width', [400, 640])
    def test_narrow_layout_no_horizontal_scroll(self, width):
        page = self._fresh(_full([_rule('[A]'), _rule('[B]', '#fb4934')]))
        page.set_viewport_size({'width': width, 'height': 900})
        page.wait_for_timeout(100)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert page.evaluate("getComputedStyle(document.querySelector('#rows tr')).display") == 'grid'
        assert page.evaluate("getComputedStyle(document.querySelector('#rows tr td:nth-child(3)'), '::before').content") == '"Tag"'
        assert page.evaluate("getComputedStyle(document.querySelector('.header')).flexWrap") == 'wrap'
        page.fill('#debugTitle', 'X' * 80)  # an unbroken title in the rule tester must wrap, not widen the page
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.evaluate('document.documentElement.scrollWidth')
        if width == 400:
            match, color = page.evaluate("""() => ['td:nth-child(4)', 'td:nth-child(5)'].map(s => {
                const r = document.querySelector('#rows tr ' + s).getBoundingClientRect();
                return {top: r.top, left: r.left};
            })""")
            assert match['top'] == color['top'] and match['left'] != color['left']
        page.set_viewport_size({'width': 900, 'height': 900})
        page.wait_for_timeout(100)
        assert page.evaluate("getComputedStyle(document.querySelector('#rows tr')).display") == 'table-row'

    def test_rejected_save_is_not_retried_and_next_edit_saves(self):
        page = self._open_options()
        self._pages.append(page)
        self._set_config(page, _full([_rule('[A]')]))
        page.reload()
        page.wait_for_selector('#rows tr')
        # Too big for one storage.sync item: background.js replies {ok: false, error}.
        page.click('#importCfg')
        page.fill('#importText', json.dumps(_full([_rule('[A]'), _rule('z' * 9000, '#ffffff', 'includes')])))
        page.click('#importApply')
        assert self._poll_toast(page, "Couldn't save:"), page.text_content('#toast')
        assert len(self._get_config(page)['rules']) == 1
        page.click('#rows tr:nth-child(2) .del')
        page.check('#dimUntagged')
        deadline = time.time() + 5
        while time.time() < deadline and not self._get_config(page)['dimUntagged']:
            page.wait_for_timeout(100)
        cfg = self._get_config(page)
        assert cfg['dimUntagged'] is True, 'a corrected draft must save; the rejected payload is not retried'
        assert [r['tag'] for r in cfg['rules']] == ['[A]']

    @staticmethod
    def _poll_toast(page, text, timeout=5000):
        try:
            page.wait_for_function("t => document.getElementById('toast').textContent.includes(t)", arg=text, timeout=timeout)
            return True
        except PlaywrightTimeoutError:
            return False

    def test_show_quick_tag_option_persists(self):
        page = self._fresh(_full([_rule('[A]')], showQuickTag=None))
        assert page.is_checked('#showQuickTag')
        stored = "v => new Promise(r => chrome.storage.sync.get('tagHighlighterConfigV1', d => r(d.tagHighlighterConfigV1.showQuickTag === v)))"
        page.uncheck('#showQuickTag')
        page.wait_for_function(stored, arg=False, timeout=3000)
        page.check('#showQuickTag')
        page.wait_for_function(stored, arg=True, timeout=3000)


# ============================================================
# Background Script Migration Tests
# ============================================================

class TestMigration:
    """Test that background.js properly migrates incomplete configs."""

    @pytest.fixture(autouse=True)
    def setup(self, browser_context, ext_id):
        self.context = browser_context
        self.ext_id = ext_id
        self.options_url = f'chrome-extension://{ext_id}/options.html'

    def _get_config_via_options(self):
        page = self.context.new_page()
        page.goto(self.options_url)
        page.wait_for_timeout(1500)
        cfg = json.loads(page.evaluate(
            f"new Promise(r => chrome.storage.sync.get('{STORAGE_KEY}', "
            f"d => r(JSON.stringify(d['{STORAGE_KEY}']))))"
        ))
        page.close()
        return cfg

    def _set_raw_config(self, config):
        page = self.context.new_page()
        page.goto(f'chrome-extension://{self.ext_id}/options.html')
        page.wait_for_timeout(1500)
        page.evaluate(
            f"new Promise(r => chrome.storage.sync.set("
            f"{{'{STORAGE_KEY}': {json.dumps(config)}}}, r))"
        )
        page.close()

    def test_missing_hideNavBar_gets_added(self, browser_context, ext_id):
        """Config without hideNavBar should get it added by options.js migration."""
        self._set_raw_config({
            'rules': [{'tag': '[X]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False}],
            'maxChatTurns': 0,
            # hideNavBar intentionally missing
        })

        # Opening options page triggers init() which migrates
        cfg = self._get_config_via_options()
        assert 'hideNavBar' in cfg, 'Migration should add hideNavBar'
        assert cfg['hideNavBar'] is True, 'Default hideNavBar should be true'

    def test_missing_hide_field_gets_added(self, browser_context, ext_id):
        """Rules without hide field should get hide:false added."""
        self._set_raw_config({
            'rules': [{'tag': '[Y]', 'match': 'startsWith', 'color': '#fabd2f'}],
            'maxChatTurns': 0,
            'hideNavBar': True,
        })

        cfg = self._get_config_via_options()
        assert cfg['rules'][0]['hide'] is False, 'Missing hide should default to false'

    def test_dim_untagged_persists(self, browser_context, ext_id):
        """dimUntagged checkbox should persist in config."""
        page = self.context.new_page()
        page.goto(self.options_url)
        page.wait_for_timeout(1500)
        page.evaluate(
            f"new Promise(r => chrome.storage.sync.set("
            f"{{'{STORAGE_KEY}': {json.dumps({'rules': [{'tag': '[A]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False}], 'maxChatTurns': 0, 'hideNavBar': True, 'dimUntagged': False})}}}, r))"
        )
        page.reload()
        page.wait_for_timeout(1500)

        page.check('#dimUntagged')
        page.wait_for_timeout(500)

        cfg = json.loads(page.evaluate(
            f"new Promise(r => chrome.storage.sync.get('{STORAGE_KEY}', "
            f"d => r(JSON.stringify(d['{STORAGE_KEY}']))))"
        ))
        page.close()
        assert cfg['dimUntagged'] is True

    def test_show_badge_persists(self, browser_context, ext_id):
        """showBadge checkbox should persist in config."""
        page = self.context.new_page()
        page.goto(self.options_url)
        page.wait_for_timeout(1500)
        page.evaluate(
            f"new Promise(r => chrome.storage.sync.set("
            f"{{'{STORAGE_KEY}': {json.dumps({'rules': [{'tag': '[A]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False}], 'maxChatTurns': 0, 'hideNavBar': True, 'showBadge': True})}}}, r))"
        )
        page.reload()
        page.wait_for_timeout(1500)

        page.uncheck('#showBadge')
        page.wait_for_timeout(500)

        cfg = json.loads(page.evaluate(
            f"new Promise(r => chrome.storage.sync.get('{STORAGE_KEY}', "
            f"d => r(JSON.stringify(d['{STORAGE_KEY}']))))"
        ))
        page.close()
        assert cfg['showBadge'] is False

    def test_show_badge_defaults_true(self, browser_context, ext_id):
        """showBadge should default to true when missing."""
        page = self.context.new_page()
        page.goto(self.options_url)
        page.wait_for_timeout(1500)
        page.evaluate(
            f"new Promise(r => chrome.storage.sync.set("
            f"{{'{STORAGE_KEY}': {json.dumps({'rules': [{'tag': '[A]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False}], 'maxChatTurns': 0, 'hideNavBar': True})}}}, r))"
        )
        page.reload()
        page.wait_for_timeout(1500)

        cfg = json.loads(page.evaluate(
            f"new Promise(r => chrome.storage.sync.get('{STORAGE_KEY}', "
            f"d => r(JSON.stringify(d['{STORAGE_KEY}']))))"
        ))
        page.close()
        assert cfg.get('showBadge') is True

    def test_missing_all_new_fields_gets_migrated(self, browser_context, ext_id):
        """Config missing all new fields should get them added."""
        self._set_raw_config({
            'rules': [{'tag': '[Z]', 'match': 'startsWith', 'color': '#fabd2f'}],
            'maxChatTurns': 0,
            # hideNavBar, dimUntagged, showBadge, overlay all missing
        })

        cfg = self._get_config_via_options()
        assert cfg['rules'][0].get('overlay') is True
        assert cfg['rules'][0].get('hide') is False
        assert 'hideNavBar' in cfg
        assert 'dimUntagged' in cfg
        assert 'showBadge' in cfg
        assert cfg.get('lazyRenderTurns') is True, 'lazyRenderTurns should default to true'
        assert cfg.get('showDeleteUntagged') is False, 'showDeleteUntagged must default to false'

    def test_show_delete_untagged_defaults_off_and_persists(self, browser_context, ext_id):
        """The 'Delete untagged chats' button is opt-in and its checkbox persists."""
        self._set_raw_config({
            'rules': [{'tag': '[A]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False}],
            'maxChatTurns': 0, 'hideNavBar': True,
        })
        page = self.context.new_page()
        page.goto(self.options_url)
        page.wait_for_timeout(1500)
        assert page.evaluate("document.getElementById('showDeleteUntagged').checked") is False
        page.check('#showDeleteUntagged')
        page.wait_for_timeout(500)
        read = (f"new Promise(r => chrome.storage.sync.get('{STORAGE_KEY}', "
                f"d => r(JSON.stringify(d['{STORAGE_KEY}']))))")
        assert json.loads(page.evaluate(read))['showDeleteUntagged'] is True
        page.reload()
        page.wait_for_timeout(1500)
        assert page.evaluate("document.getElementById('showDeleteUntagged').checked") is True, \
            'options init migration must keep the setting'
        assert json.loads(page.evaluate(read))['showDeleteUntagged'] is True
        page.close()

    def test_lazy_render_turns_persists(self, browser_context, ext_id):
        """The 'Speed up long chats' checkbox should persist in config."""
        self._set_raw_config({
            'rules': [{'tag': '[A]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False}],
            'maxChatTurns': 0, 'hideNavBar': True,
        })
        page = self.context.new_page()
        page.goto(self.options_url)
        page.wait_for_timeout(1500)
        assert page.evaluate("document.getElementById('lazyRenderTurns').checked") is True
        page.uncheck('#lazyRenderTurns')
        page.wait_for_timeout(500)
        cfg = json.loads(page.evaluate(
            f"new Promise(r => chrome.storage.sync.get('{STORAGE_KEY}', "
            f"d => r(JSON.stringify(d['{STORAGE_KEY}']))))"
        ))
        page.close()
        assert cfg['lazyRenderTurns'] is False


    def test_explicit_show_quick_tag_false_survives_migration(self, browser_context, ext_id):
        self._set_raw_config({'rules': [{'tag': '[Q]', 'match': 'startsWith', 'color': '#fabd2f'}], 'maxChatTurns': 0, 'showQuickTag': False})
        cfg = self._get_config_via_options()  # options init migrates the missing fields
        assert cfg['hideNavBar'] is True and cfg['rules'][0]['hide'] is False
        assert cfg['showQuickTag'] is False
        page = self.context.new_page()
        page.goto(self.options_url)
        page.wait_for_selector('#rows tr')
        page.wait_for_timeout(300)
        assert page.is_checked('#showQuickTag') is False
        page.close()

    def test_background_migration_preserves_intentionally_empty_rules(self, browser_context):
        page = browser_context.new_page()
        try:
            page.set_content('<html><body></body></html>')
            page.evaluate("""() => {
                window.__store = {tagHighlighterConfigV1: {rules: [], maxChatTurns: 0}};
                const ev = {addListener() {}};
                window.browser = {runtime: {onInstalled: ev, onStartup: ev, onMessage: ev},
                    storage: {sync: {
                        get: async k => ({[k]: window.__store[k]}),
                        set: async o => {Object.assign(window.__store, o);window.migrated=true;},
                    }}};
            }""")
            page.add_script_tag(content=(Path(EXT_PATH) / 'background.js').read_text())
            page.wait_for_function('() => window.migrated === true')
            assert page.evaluate('window.__store.tagHighlighterConfigV1.rules') == []
        finally:
            page.close()

    def test_background_migration_writes_hex_for_missing_color(self, browser_context, ext_id):
        """background.js must never persist a non-hex color (e.g. the name 'Green')."""
        page = browser_context.new_page()
        page.set_content('<html><body></body></html>')
        page.evaluate("""() => {
            window.__store = {tagHighlighterConfigV1: {rules: [{tag: '[X]', match: 'startsWith'}], maxChatTurns: 0}};
            const ev = {addListener() {}};
            // background.js prefers `browser` over `chrome`; window.chrome can't be redefined.
            window.browser = ({
                runtime: {onInstalled: ev, onStartup: ev, onMessage: ev},
                storage: {sync: {
                    get(k, cb) { const v = {[k]: window.__store[k]}; return cb ? cb(v) : Promise.resolve(v); },
                    set(o, cb) { Object.assign(window.__store, o); return cb ? cb() : Promise.resolve(); },
                }},
            });
        }""")
        page.add_script_tag(content=(Path(EXT_PATH) / 'background.js').read_text())
        page.wait_for_function("() => window.__store.tagHighlighterConfigV1.rules[0].hide === false", timeout=5000)
        color = page.evaluate("window.__store.tagHighlighterConfigV1.rules[0].color")
        show_delete = page.evaluate("window.__store.tagHighlighterConfigV1.showDeleteUntagged")
        page.close()
        assert show_delete is False, 'background migration must add showDeleteUntagged=false'
        assert re.fullmatch(r'#[0-9a-f]{6}', color or ''), f'migration stored non-hex color {color!r}'


# ============================================================
# Background config writer — background.js run in a plain page against an
# in-memory browser.* harness (no extension, no network).
# ============================================================

_BG_HARNESS = """([store, delay]) => {
    window.__store = store;
    window.__calls = [];
    const L = [];
    const ev = n => ({addListener: f => L.push([n, f])});
    const wait = () => new Promise(r => setTimeout(r, delay));
    const rec = n => (...a) => { __calls.push([n, a]); return Promise.resolve({id: 7}); };
    window.browser = {
        runtime: {
            onInstalled: ev('i'), onStartup: ev('s'), onMessage: ev('m'),
            getURL: p => 'ext://' + p,
            openOptionsPage: rec('openOptionsPage'),
            sendMessage: m => window.down ? Promise.reject(new Error('down')) : send(m),
        },
        windows: {create: rec('create'), update: rec('update'), get: rec('get'), onRemoved: ev('removed')},
        action: {onClicked: ev('clicked'), setBadgeText() {}, setBadgeBackgroundColor() {}},
        storage: {
            onChanged: ev('changed'),
            session: {
                get: async k => ({[k]: (window.__session ||= {})[k]}),
                set: async o => { Object.assign(window.__session ||= {}, o); },
            },
            sync: {
                get: async k => { await wait(); return {[k]: structuredClone(__store[k])}; },
                set: async o => {
                    await wait();
                    const ch = Object.fromEntries(Object.keys(o).map(k => [k, {oldValue: structuredClone(__store[k]), newValue: structuredClone(o[k])}]));
                    Object.assign(__store, structuredClone(o));
                    __calls.push(['set', o]);
                    fire('changed', ch, 'sync');
                },
            },
        },
    };
    // A message nobody answers fails after 5 s instead of hanging the test.
    window.send = m => new Promise((r, j) => {
        for (const [n, f] of L) if (n === 'm') f(m, {}, r);
        setTimeout(() => j(new Error('Timeout: no reply to ' + m?.type)), 5000);
    });
    window.fire = (n, ...a) => { for (const [k, f] of L) if (k === n) f(...a); };
    window.cfg = () => __store.tagHighlighterConfigV1;
    window.count = n => __calls.filter(c => c[0] === n).length;
}"""


def _rule(tag, color='#fabd2f', match='startsWith', **kw):
    return {'tag': tag, 'match': match, 'color': color, 'hide': False, 'overlay': True, **kw}


def _full(rules, **kw):
    return {'rules': rules, 'maxChatTurns': 0, 'hideNavBar': True, 'dimUntagged': False, 'showBadge': True,
            'lazyRenderTurns': True, 'showDeleteUntagged': False, 'showQuickTag': True, **kw}


def _tjs(cid):
    return f"document.querySelector('#row-{cid} [data-thread-title] span[dir=auto]').textContent"


class _BgPages:
    @pytest.fixture(autouse=True)
    def _ctx(self, browser_context):
        self.context, self._bg_pages = browser_context, []
        yield
        for p in self._bg_pages:
            p.close()

    def bg(self, rules=None, delay=0, setup='', **kw):
        store = {STORAGE_KEY: _full([_rule('[A]'), _rule('[B]', '#fb4934')] if rules is None else rules, **kw)}
        page = self.context.new_page()
        self._bg_pages.append(page)
        page.set_content('<html><body></body></html>')
        page.evaluate(_BG_HARNESS, [store, delay])
        if setup:
            page.evaluate(f'() => {{ {setup} }}')  # statement body, never an auto-invoked expression
        page.add_script_tag(content=(Path(EXT_PATH) / 'background.js').read_text())
        return page


def _tags(cfg):
    return [r['tag'] for r in cfg['rules']]


class TestConfigWriter(_BgPages):
    """background.js is the only config writer: compare-and-set writes and addRule on one chain."""

    def test_cas_writes_when_base_matches(self):
        page = self.bg()
        res = page.evaluate("async () => { const b = cfg(); return send({type: 'writeConfig', base: b, next: {...b, dimUntagged: true}}); }")
        assert res['ok'] is True and res['value']['dimUntagged'] is True
        assert page.evaluate('cfg().dimUntagged') is True
        assert page.evaluate("count('set')") == 1
        # Same content, different key order: still the same base.
        res = page.evaluate("""async () => {
            const b = cfg();
            const reordered = Object.fromEntries(Object.entries(b).reverse());
            reordered.rules = b.rules.map(r => Object.fromEntries(Object.entries(r).reverse()));
            return send({type: 'writeConfig', base: reordered, next: {...b, maxChatTurns: 4}});
        }""")
        assert res['ok'] is True
        assert page.evaluate('cfg().maxChatTurns') == 4
        assert page.evaluate("count('set')") == 2

    def test_cas_conflict_writes_nothing(self):
        page = self.bg()
        res = page.evaluate("""async () => {
            const b = cfg();
            await send({type: 'addRule', tag: '[NEW]'});
            return send({type: 'writeConfig', base: b, next: {...b, dimUntagged: true}});
        }""")
        assert res['ok'] is False and res['conflict'] is True
        assert _tags(res['value']) == ['[A]', '[B]', '[NEW]']
        assert _tags(page.evaluate('cfg()')) == ['[A]', '[B]', '[NEW]']
        assert page.evaluate('cfg().dimUntagged') is False
        assert page.evaluate("count('set')") == 1

    def test_retry_after_landed_write_is_ok(self):
        page = self.bg()
        res = page.evaluate("""async () => {
            const b = cfg(), n = {...b, maxChatTurns: 3};
            return [await send({type: 'writeConfig', base: b, next: n}), await send({type: 'writeConfig', base: b, next: n})];
        }""")
        assert res[0]['ok'] is True and res[1]['ok'] is True
        assert page.evaluate('cfg().maxChatTurns') == 3
        assert page.evaluate("count('set')") == 1

    def test_interleaved_add_rule_then_stale_write_conflicts(self):
        page = self.bg(delay=20)
        res = page.evaluate("""async () => {
            const b = cfg();
            return Promise.all([send({type: 'addRule', tag: '[NEW]'}), send({type: 'writeConfig', base: b, next: {...b, dimUntagged: true}})]);
        }""")
        assert res[1]['conflict'] is True
        assert _tags(page.evaluate('cfg()')) == ['[A]', '[B]', '[NEW]']
        assert page.evaluate('cfg().dimUntagged') is False

    def test_add_rule_trims_and_dedupes(self):
        page = self.bg(rules=[_rule('[A]'), _rule('code', '#83a598', 'includes')], showQuickTag=False, maxChatTurns=7, dimUntagged=True)
        general = lambda: {k: v for k, v in page.evaluate('cfg()').items() if k != 'rules'}
        before = general()
        assert before['showQuickTag'] is False and before['maxChatTurns'] == 7
        res = page.evaluate("() => send({type: 'addRule', tag: '  [NEW]  '})")
        assert res['ok'] is True and res['created'] is True
        assert res['rule']['tag'] == '[NEW]' and res['rule']['match'] == 'startsWith'
        for tag in ('[A]', 'code', '[NEW]'):
            res = page.evaluate('t => send({type: "addRule", tag: t})', tag)
            assert res['ok'] is True and res['created'] is False, tag
        assert len(page.evaluate('cfg().rules')) == 3
        assert general() == before, 'appending a rule must keep every other setting'

    def test_add_rule_length_bounds(self):
        page = self.bg()
        for tag in ('', '   ', 'x' * 41):
            assert page.evaluate('t => send({type: "addRule", tag: t})', tag) == {'ok': False, 'error': 'Tags are 1–40 characters.'}
        assert page.evaluate('t => send({type: "addRule", tag: t})', 'x' * 40)['ok'] is True
        assert page.evaluate("count('set')") == 1

    def test_add_rule_palette_first_unused_then_gray(self):
        page = self.bg(rules=[_rule('[R]', '#fb4934'), _rule('[Y]', '#fabd2f')])
        assert page.evaluate("() => send({type: 'addRule', tag: '[N]'})")['rule']['color'] == '#b8bb26'
        palette = ['#fb4934', '#b8bb26', '#fabd2f', '#83a598', '#d3869b', '#8ec07c', '#fe8019', '#928374', '#a7a7a7', '#ffffff']
        page = self.bg(rules=[_rule(f'[{i}]', c) for i, c in enumerate(palette)])
        assert page.evaluate("() => send({type: 'addRule', tag: '[N]'})")['rule']['color'] == '#a7a7a7'

    def test_queue_serializes_concurrent_add_rules(self):
        page = self.bg(delay=15)
        res = page.evaluate("() => Promise.all(['[1]', '[2]', '[3]', '[4]', '[5]'].map(tag => send({type: 'addRule', tag})))")
        assert all(r['created'] for r in res)
        assert len(page.evaluate('cfg().rules')) == 7

    def test_migration_shares_writer_chain(self):
        setup = 'delete __store.tagHighlighterConfigV1.showQuickTag; window.raw = structuredClone(__store.tagHighlighterConfigV1);'
        page = self.bg(delay=100, setup=setup)  # migration is reading/writing while these arrive
        assert page.evaluate("() => send({type: 'addRule', tag: '[NEW]'})")['created'] is True
        page.wait_for_timeout(400)
        assert page.evaluate('cfg().showQuickTag') is True, 'addRule overwrote the migration'
        assert _tags(page.evaluate('cfg()')) == ['[A]', '[B]', '[NEW]']
        page = self.bg(delay=100, setup=setup)
        res = page.evaluate("() => send({type: 'writeConfig', base: raw, next: {...raw, dimUntagged: true}})")
        page.wait_for_timeout(400)
        assert res['conflict'] is True
        assert page.evaluate('cfg().showQuickTag') is True, 'a write against the pre-migration value overwrote the migration'
        assert page.evaluate('cfg().dimUntagged') is False

    def test_migration_keeps_explicit_show_quick_tag_false(self):
        page = self.bg(showQuickTag=False, setup='delete __store.tagHighlighterConfigV1.showBadge')
        page.wait_for_function('() => cfg().showBadge === true', timeout=3000)
        assert page.evaluate('cfg().showQuickTag') is False

    def test_seed_on_fresh_install(self):
        page = self.bg(setup='delete __store.tagHighlighterConfigV1')
        page.wait_for_function('() => Array.isArray(cfg()?.rules)', timeout=3000)
        assert page.evaluate('cfg().showQuickTag') is True
        assert _tags(page.evaluate('cfg()')) == ['[TODO]', '[BUG]', 'code', 'help']

    def test_migration_adds_show_quick_tag(self):
        page = self.bg(setup='delete __store.tagHighlighterConfigV1.showQuickTag')
        page.wait_for_function('() => cfg().showQuickTag === true', timeout=3000)
        assert list(page.evaluate('cfg()'))[-1] == 'showQuickTag'


class TestOpenSettings(_BgPages):
    """The toolbar button and content.js open settings in one floating popup window."""

    OPEN = "() => send({type: 'openSettings'})"

    def _args(self, page, name):
        return page.evaluate('n => __calls.filter(c => c[0] === n).map(c => c[1])', name)

    def test_popup_args_and_refocus(self):
        page = self.bg()
        page.evaluate(self.OPEN)
        assert self._args(page, 'create') == [[{'url': 'ext://options.html', 'type': 'popup', 'width': 560, 'height': 720, 'focused': True}]]
        page.evaluate(self.OPEN)
        assert page.evaluate("count('create')") == 1
        assert self._args(page, 'update') == [[7, {'focused': True}]]
        page.evaluate("fire('removed', 7)")
        page.evaluate(self.OPEN)
        assert page.evaluate("count('create')") == 2

    def test_refocus_after_worker_restart(self):
        page = self.bg(setup='window.__session = {cthSettingsWindowId: 7};')
        page.evaluate(self.OPEN)
        assert page.evaluate("count('create')") == 0
        assert self._args(page, 'update') == [[7, {'focused': True}]]
        page = self.bg(setup="window.__session = {cthSettingsWindowId: 7}; browser.windows.get = () => Promise.reject(new Error('No window with id: 7'));")
        page.evaluate(self.OPEN)
        assert page.evaluate("count('create')") == 1

    def test_concurrent_opens_create_one_window(self):
        page = self.bg()
        page.evaluate(f'() => Promise.all([({self.OPEN})(), ({self.OPEN})()])')
        assert page.evaluate("count('create')") == 1

    def test_fallback_when_windows_missing(self):
        page = self.bg(setup='delete browser.windows;')
        page.evaluate(self.OPEN)
        assert page.evaluate("count('openOptionsPage')") == 1

    def test_fallback_when_create_rejects(self):
        page = self.bg(setup="browser.windows.create = () => Promise.reject(new Error('blocked'));")
        page.evaluate(self.OPEN)
        assert page.evaluate("count('openOptionsPage')") == 1

    def test_toolbar_click_with_zero_rules(self):
        page = self.bg(rules=[])
        page.evaluate("fire('clicked', {id: 1})")
        page.wait_for_function("() => count('create') === 1", timeout=3000)


class TestStatic:
    """Source-level invariants that need no browser."""

    def test_manifests_have_action_without_popup(self):
        for name in ('manifest.chrome.json', 'manifest.firefox.json'):
            m = json.loads((ROOT / 'src' / name).read_text())
            assert 'action' in m and 'default_popup' not in m['action'], name

    @staticmethod
    def _fn(text, name):  # function source with indentation stripped, by brace matching
        start, depth = text.index(f'function {name}('), 0
        for i in range(text.index('{', start), len(text)):
            depth += {'{': 1, '}': -1}.get(text[i], 0)
            if depth == 0:
                return '\n'.join(line.strip() for line in text[start:i + 1].splitlines())

    def test_apply_tag_never_reads_menu_state(self):
        src = (ROOT / 'src' / 'content.js').read_text()
        assert 'qtBound' not in self._fn(src, 'applyTag')
        t = self._fn(src, 'startNewTag')
        assert t.index('const bound = qtBound') < t.index('await'), 'capture the chat before any await'
        assert 'finishNewTag(bound, res)' in t, 'the captured chat, not the menu, is renamed after addRule'
        assert 'qtBound' not in self._fn(src, 'finishNewTag')

    def test_unit_copies_match_source(self):
        src = (ROOT / 'src' / 'content.js').read_text()
        unit = Path(UNIT_TEST_PATH).read_text()
        for name in ('currentPrefixTag', 'computeTaggedTitle'):
            assert self._fn(unit, name) == self._fn(src, name), f'{name}: tests/unit_test.html copy differs from content.js'

    def test_only_background_writes_config(self):
        options = (ROOT / 'src' / 'options.js').read_text()
        content = (ROOT / 'src' / 'content.js').read_text()
        assert not re.search(r'\bstore\.set\(', options), 'options.js must write through background.js'
        for pattern in ('storageSet(storeSync', 'storeSync.set(', 'storage.sync.set('):
            assert pattern not in content, pattern



# ============================================================
# Content Script Tests — the packaged content.js against synthetic
# ChatGPT markup served at https://chatgpt.com/ via request routing.
# Fixtures mirror the DOM hooks observed on the live site (Sep 2026):
# #history > a[data-sidebar-item], .truncate span[dir=auto],
# empty-string data-active, form[data-type=unified-composer], and
# <section data-testid="conversation-turn-N"> inside an overflow-auto
# scroll root above <main>. No real account data is used.
# ============================================================

import html as _html

CONTENT_RULES = [
    {'tag': '[TODO]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False, 'overlay': True},
    {'tag': '[BUG]', 'match': 'startsWith', 'color': '#fb4934', 'hide': False, 'overlay': True},
    {'tag': '[ARCHIVE]', 'match': 'startsWith', 'color': '#928374', 'hide': True, 'overlay': True},
    {'tag': 'code', 'match': 'includes', 'color': '#83a598', 'hide': False, 'overlay': True},
]

OK = '{"success": true}'
TOKEN = '{"accessToken": "test-token"}'

DEFAULT_CHATS = [
    ('c1', '[TODO] ship release'),
    ('c2', '[BUG] code crash'),   # first match wins: [BUG], not "code"
    ('c3', 'refactor code path'),
    ('c4', '[ARCHIVE] old notes'),
    ('c5', 'plain chat'),
]


def _api_chat(cid, title, **flags):
    """A conversation-list item shaped like ChatGPT's (Sep 2026), with made-up data."""
    item = {'id': cid, 'title': title, 'is_archived': False, 'pinned_time': None,
            'is_starred': False, 'snippet': 'not used', 'mapping': None}
    item.update(flags)
    return item


# 5 tagged, 3 untagged-but-kept (pinned / starred / archived), 3 untagged to delete.
API_CHATS = [
    _api_chat('a1', '[TODO] ship'),
    _api_chat('a2', 'plain chat'),
    _api_chat('a3', '[ARCHIVE] old notes'),          # rule-hidden chats are tagged too
    _api_chat('a4', 'pinned plain', pinned_time='2026-09-01T00:00:00Z'),
    _api_chat('a5', 'starred plain', is_starred=True),
    _api_chat('a6', 'archived plain', is_archived=True),
    _api_chat('a7', None),                            # untitled
    _api_chat('a8', '[BUG] crash'),
    _api_chat('a9', '<img src=x onerror="window.__xss=1">'),
    _api_chat('a10', 'refactor code path'),           # "code" includes-rule
    _api_chat('a11', '[TODO] second'),
]


def _chat_fixture(chats=DEFAULT_CHATS, active=None, composer='current',
                  turn_tag='section', turns=6):
    """Build a minimal ChatGPT-shaped page.

    active: None, a chat id (empty-string data-active, as on live), or a
            dict {chat_id: data-active value}.
    composer: 'current' (unified-composer form), 'legacy'
              (div.bg-token-bg-primary), or 'none'.
    """
    if isinstance(active, str):
        active = {active: ''}
    active = active or {}

    links = []
    for cid, title in chats:
        attr = f' data-active="{_html.escape(active[cid])}"' if cid in active else ''
        links.append(
            f'<a href="/c/{cid}" data-sidebar-item="true"{attr}>'
            f'<div class="flex min-w-0 grow items-center"><div class="truncate">'
            f'<span dir="auto">{_html.escape(title)}</span></div></div></a>'
        )

    turn_html = ''.join(
        f'<{turn_tag} data-testid="conversation-turn-{i}" class="turn">turn {i}'
        f'<button data-testid="copy-turn-action-button">copy</button></{turn_tag}>'
        for i in range(1, turns + 1)
    )

    if composer == 'current':
        composer_html = (
            '<form id="composer" class="group/composer w-full relative z-1" data-type="unified-composer">'
            '<div class="relative"><div class="surface">'
            '<div id="prompt-textarea" contenteditable="true" role="textbox"></div>'
            '</div></div></form>'
        )
    elif composer == 'legacy':
        composer_html = (
            '<div id="composer" class="bg-token-bg-primary">'
            '<div id="prompt-textarea" contenteditable="true"></div></div>'
        )
    else:
        composer_html = ''

    return f'''<!doctype html>
<html class="dark"><head><meta charset="utf-8"><title>ChatGPT fixture</title>
<style>
  html, body {{ margin: 0; height: 100%; }}
  body {{ display: flex; }}
  #sidebar {{ width: 260px; height: 100vh; overflow-y: auto; }}
  #history a {{ display: block; padding: 8px 12px; }}
  #stage {{ flex: 1; display: flex; flex-direction: column; height: 100vh; }}
  #scroll-root {{ flex: 1; min-height: 0; overflow-y: auto; position: relative; }}
  #main {{ display: block; }}
  .turn {{ display: block; height: 300px; }}
  #composer {{ display: block; margin: 12px auto; width: 600px; min-height: 52px; }}
  #native-scroll {{ position: fixed; right: 40px; bottom: 120px; }}
</style></head>
<body>
  <aside id="sidebar"><nav aria-label="Sidebar"><div id="history">{''.join(links)}</div></nav></aside>
  <div id="stage">
    <div id="scroll-root" class="overflow-y-auto">
      <main id="main"><div id="thread">{turn_html}
        <button id="native-scroll" aria-label="Scroll to bottom">down</button>
        <div class="flex h-0 items-end justify-center group-[:not([data-scroll-from-end])]/scroll-root:scale-0">
          <button id="native-scroll-current" aria-hidden="true" tabindex="-1" class="rounded-full btn-secondary">v</button>
        </div>
      </div></main>
    </div>
    {composer_html}
  </div>
</body></html>'''


class TestContentScript:
    """Exercise the real packaged content.js on synthetic ChatGPT pages."""

    @pytest.fixture(autouse=True)
    def setup(self, browser_context, ext_id):
        self.context = browser_context
        self.ext_id = ext_id
        self._pages = []
        yield
        for p in self._pages:
            try:
                p.close()
            except Exception:
                pass

    def _configure(self, rules=None, active_filters=None, **overrides):
        cfg = {
            'rules': rules if rules is not None else CONTENT_RULES,
            'maxChatTurns': 0, 'hideNavBar': True,
            'dimUntagged': False, 'showBadge': True,
        }
        cfg.update(overrides)
        page = self.context.new_page()
        page.goto(f'chrome-extension://{self.ext_id}/options.html')
        page.wait_for_timeout(800)  # let options.js init/migration settle
        page.evaluate(
            """([key, cfg, uiKey, filters]) => Promise.all([
                new Promise(r => chrome.storage.sync.set({[key]: cfg}, r)),
                new Promise(r => chrome.storage.local.set({[uiKey]: {activeFilters: filters}}, r)),
            ])""",
            [STORAGE_KEY, cfg, 'tagHighlighterUiStateV1', active_filters or []],
        )
        page.close()

    def _open_chat(self, path='/c/c1', **fixture_kwargs):
        body = _chat_fixture(**fixture_kwargs)
        page = self.context.new_page()
        self._pages.append(page)
        page.route('https://chatgpt.com/**', lambda route: route.fulfill(
            status=200, content_type='text/html', body=body))
        page.goto(f'https://chatgpt.com{path}')
        # Proves the packaged content script injected before we assert anything.
        page.wait_for_selector('#cth-style', state='attached', timeout=10_000)
        page.wait_for_selector('#history a[data-cth="1"]', state='attached', timeout=10_000)
        return page

    @staticmethod
    def _poll(page, expression, arg=None, timeout=3000):
        try:
            page.wait_for_function(expression, arg=arg, timeout=timeout)
            return True
        except PlaywrightTimeoutError:
            return False

    def _overlay_visible(self, page, timeout=3000):
        return self._poll(page, """() => {
            const o = document.getElementById('cth-overlay');
            return !!o && getComputedStyle(o).display !== 'none';
        }""", timeout=timeout)

    def _overlay_hidden(self, page, timeout=3000):
        return self._poll(page, """() => {
            const o = document.getElementById('cth-overlay');
            return !o || getComputedStyle(o).display === 'none';
        }""", timeout=timeout)

    def _sidebar_state(self, page):
        return page.evaluate("""() => Object.fromEntries(
            [...document.querySelectorAll('#history a[data-sidebar-item]')].map(a => [
                a.getAttribute('href').slice(3),
                {cth: a.dataset.cth || null, hidden: a.dataset.cthHidden || null,
                 color: a.style.getPropertyValue('--cth-color') || null,
                 display: getComputedStyle(a).display},
            ]))""")

    # ---- Highlighting ----

    def test_highlights_with_first_match_and_hides_rule_hidden(self):
        self._configure()
        page = self._open_chat()
        s = self._sidebar_state(page)
        assert s['c1']['cth'] == '1' and s['c1']['color'] == '#fabd2f'
        assert s['c2']['color'] == '#fb4934', 'first matching rule ([BUG]) must win over "code"'
        assert s['c3']['color'] == '#83a598'
        assert s['c4']['hidden'] == '1' and s['c4']['display'] == 'none'
        assert s['c5']['cth'] is None and s['c5']['display'] != 'none'

    def test_dim_untagged_and_badge_count(self):
        self._configure(dimUntagged=True)
        page = self._open_chat()
        opacity = page.evaluate(
            "getComputedStyle(document.querySelector('#history a[href=\"/c/c5\"]')).opacity")
        assert float(opacity) < 1, 'untagged chat should be dimmed'
        opts = self.context.new_page()
        self._pages.append(opts)
        opts.goto(f'chrome-extension://{self.ext_id}/options.html')
        # Tagged, non-hidden chats: c1, c2, c3.
        assert self._poll(opts, "async () => (await chrome.action.getBadgeText({})) === '3'",
                          timeout=5000), 'badge should count 3 visible tagged chats'

    # ---- Overlay ----

    def test_overlay_positions_above_current_composer(self):
        self._configure()
        page = self._open_chat(active='c1', composer='current')
        assert self._overlay_visible(page), 'overlay must appear above the unified-composer form'
        geo = page.evaluate("""() => {
            const o = document.getElementById('cth-overlay').getBoundingClientRect();
            const c = document.getElementById('composer').getBoundingClientRect();
            return {oBottom: o.bottom, cTop: c.top, oLeft: o.left, cLeft: c.left,
                    oWidth: o.width, cWidth: c.width,
                    title: document.querySelector('#cth-overlay .cth-title').textContent,
                    z: getComputedStyle(document.getElementById('cth-overlay')).zIndex};
        }""")
        assert abs(geo['oBottom'] - geo['cTop']) <= 2
        assert abs(geo['oLeft'] - geo['cLeft']) <= 2 and abs(geo['oWidth'] - geo['cWidth']) <= 2
        assert geo['title'] == '[TODO] ship release'
        assert geo['z'] == '30', 'overlay must stay below ChatGPT popovers'

    def test_overlay_positions_above_legacy_composer(self):
        self._configure()
        page = self._open_chat(active='c1', composer='legacy')
        assert self._overlay_visible(page)

    def test_overlay_recovers_after_composer_remount(self):
        self._configure()
        page = self._open_chat(active='c1', composer='legacy')
        assert self._overlay_visible(page)
        page.evaluate("window.__composer = document.getElementById('composer'); window.__composer.remove()")
        assert self._overlay_hidden(page), 'overlay must hide while composer is absent'
        page.evaluate("document.getElementById('stage').append(window.__composer)")
        assert self._overlay_visible(page), 'overlay must return when composer is re-mounted'

    def test_overlay_skips_literal_false_active_marker(self):
        self._configure()
        page = self._open_chat(active={'c1': 'false', 'c2': ''}, composer='legacy')
        assert self._overlay_visible(page)
        title = page.evaluate("document.querySelector('#cth-overlay .cth-title').textContent")
        assert title == '[BUG] code crash', f'data-active="false" must not count as selected, got {title!r}'

    @pytest.mark.parametrize('turn_tag', ['section', 'article'])
    def test_overlay_click_scrolls_conversation_to_bottom(self, turn_tag):
        self._configure()
        page = self._open_chat(active='c1', composer='legacy', turn_tag=turn_tag)
        assert self._overlay_visible(page)
        page.click('#cth-overlay .cth-arrow')
        assert self._poll(page, """() => {
            const s = document.getElementById('scroll-root');
            return s.scrollTop > 0 && s.scrollTop + s.clientHeight >= s.scrollHeight - 5;
        }""", timeout=4000), f'chevron click must scroll the real scroller ({turn_tag} turns)'

    def test_overlay_click_finishes_when_page_interrupts_smooth_scroll(self):
        """If the smooth scroll is cut short (another scroll write, growing
        content), the chevron must still land at the bottom."""
        self._configure()
        page = self._open_chat(active='c1', composer='legacy')
        assert self._overlay_visible(page)
        page.evaluate("document.getElementById('scroll-root').scrollTop = 0")
        page.wait_for_timeout(300)
        # Simulate the page nudging scrollTop once, which aborts a smooth scroll.
        page.evaluate("""() => {
            const s = document.getElementById('scroll-root');
            let fired = false;
            s.addEventListener('scroll', () => {
                if (fired) return;
                fired = true;
                s.scrollTop = s.scrollTop + 1;
            });
        }""")
        page.click('#cth-overlay .cth-arrow')
        assert self._poll(page, """() => {
            const s = document.getElementById('scroll-root');
            return s.scrollTop + s.clientHeight >= s.scrollHeight - 5;
        }""", timeout=4000), 'chevron must finish at the bottom even if the smooth scroll is interrupted'

    def test_overlay_click_respects_user_scroll_after_interruption(self):
        """If the user scrolls while the chevron's scroll is stalled, the
        fallback must not yank them to the bottom afterwards."""
        self._configure()
        page = self._open_chat(active='c1', composer='legacy')
        assert self._overlay_visible(page)
        page.evaluate("document.getElementById('scroll-root').scrollTop = 0")
        page.wait_for_timeout(300)
        # Observe the actual interruption before testing cancellation. Otherwise
        # an unstarted first scroll could leave this listener armed for click #2.
        page.evaluate("""() => {
            const s = document.getElementById('scroll-root');
            window.interruptions = 0;
            window.interruptScroll = () => {
                window.interruptions++;
                s.removeEventListener('scroll', window.interruptScroll);
                s.scrollTop = s.scrollTop + 1;
                s.dispatchEvent(new WheelEvent('wheel', {bubbles: true, deltaY: -10}));
            };
            s.addEventListener('scroll', window.interruptScroll);
        }""")
        page.click('#cth-overlay .cth-arrow')
        assert self._poll(page, '() => window.interruptions === 1'), 'first click must actually reach the interruption'
        page.wait_for_timeout(2200)  # past the 1.5 s fallback deadline
        top, max_top = page.evaluate("""() => { const s = document.getElementById('scroll-root');
            return [s.scrollTop, s.scrollHeight - s.clientHeight]; }""")
        assert top < max_top - 50, f'user input must cancel the fallback jump (scrollTop={top}, max={max_top})'

        # A later click still works normally.
        page.click('#cth-overlay .cth-arrow')
        assert self._poll(page, """() => { const s = document.getElementById('scroll-root');
            return s.scrollTop + s.clientHeight >= s.scrollHeight - 5; }""", timeout=4000)

    def test_overlay_click_keeps_composer_focus(self):
        self._configure()
        page = self._open_chat(active='c1', composer='legacy')
        assert self._overlay_visible(page)
        page.focus('#prompt-textarea')
        page.click('#cth-overlay .cth-arrow')
        page.wait_for_timeout(200)
        assert page.evaluate("document.activeElement?.id") == 'prompt-textarea', \
            'clicking the chevron should not steal focus from the composer'

    def test_native_scroll_button_only_hidden_while_overlay_replaces_it(self):
        self._configure()
        page = self._open_chat(active='c5', composer='legacy')  # untagged -> no overlay
        assert self._overlay_hidden(page)
        page.wait_for_timeout(300)
        assert page.evaluate("getComputedStyle(document.getElementById('native-scroll')).display") != 'none', \
            'native scroll control must stay usable when no overlay replaces it'
        assert page.evaluate("getComputedStyle(document.getElementById('native-scroll-current')).display") != 'none', \
            'current (unlabelled) native scroll control must stay usable when no overlay replaces it'

        page2 = self._open_chat(active='c1', composer='legacy')
        assert self._overlay_visible(page2)
        assert self._poll(page2, "() => getComputedStyle(document.getElementById('native-scroll')).display === 'none'"), \
            'native scroll control should be de-duplicated while the overlay is shown'
        assert self._poll(page2, "() => getComputedStyle(document.getElementById('native-scroll-current')).display === 'none'"), \
            'current ChatGPT scroll button (no aria-label, data-scroll-from-end wrapper) must be de-duplicated too'

    # ---- First run + keyboard ----

    def test_config_arriving_after_boot_binds_sidebar(self):
        """On first install the page can load before any settings exist."""
        opts = self.context.new_page()
        opts.goto(f'chrome-extension://{self.ext_id}/options.html')
        opts.wait_for_timeout(800)
        opts.evaluate("k => new Promise(r => chrome.storage.sync.remove(k, r))", STORAGE_KEY)
        opts.close()
        body = _chat_fixture()
        page = self.context.new_page()
        self._pages.append(page)
        page.route('https://chatgpt.com/**', lambda route: route.fulfill(
            status=200, content_type='text/html', body=body))
        page.goto('https://chatgpt.com/c/c1')
        page.wait_for_selector('#cth-style', state='attached', timeout=10_000)
        page.wait_for_timeout(500)
        assert page.evaluate("document.querySelectorAll('#history a[data-cth=\"1\"]').length") == 0

        self._configure()
        assert self._poll(page, "() => document.querySelectorAll('#history a[data-cth=\"1\"]').length > 0"), \
            'existing chats must be styled once settings arrive'
        page.evaluate("""() => document.getElementById('history').insertAdjacentHTML('beforeend',
            '<a href="/c/new" data-sidebar-item="true"><div class="truncate"><span dir="auto">[TODO] added later</span></div></a>')""")
        assert self._poll(page, "() => document.querySelector('#history a[href=\"/c/new\"]')?.dataset.cth === '1'"), \
            'chats added after late settings must be styled (sidebar observer attached)'
        assert self._poll(page, "() => !!document.querySelector('#history #cth-filter-bar.cth-visible')"), \
            'filter bar must appear once settings arrive'

    def test_filter_pills_work_from_keyboard(self):
        self._configure()
        page = self._open_chat()
        page.wait_for_selector('#cth-filter-bar.cth-visible')
        active = "() => [...document.querySelectorAll('#cth-filter-bar .cth-pill.active')].map(p => p.textContent).join()"
        page.keyboard.press('Alt+KeyF')
        page.keyboard.press('Tab')
        page.keyboard.press('Enter')
        assert self._poll(page, active + " === '[TODO]'"), 'Enter must toggle the focused pill'
        assert page.evaluate("document.activeElement?.textContent") == '[TODO]', \
            'focus must stay on the pill after it re-renders'
        page.keyboard.press('Space')
        assert self._poll(page, active + " === 'All'"), 'Space must toggle it back off'
        roles = page.evaluate("[...document.querySelectorAll('#cth-filter-bar .cth-pill')]"
                              ".map(p => [p.getAttribute('role'), p.getAttribute('aria-pressed')])")
        assert all(r == 'button' and ap in ('true', 'false') for r, ap in roles), roles

    # ---- Long-chat rendering ----

    LAZY_STATE = """() => [...document.querySelectorAll('[data-testid^="conversation-turn-"]')]
        .filter(e => /^conversation-turn-\\d+$/.test(e.dataset.testid))
        .map(e => ({lazy: e.dataset.cthLazy === '1', cv: getComputedStyle(e).contentVisibility,
                    size: e.style.getPropertyValue('--cth-turn-h')}))"""

    def _lazy_count(self, page):
        return page.evaluate(f"({self.LAZY_STATE})().filter(t => t.lazy).length")

    def test_long_chat_skips_rendering_offscreen_turns(self):
        self._configure()
        page = self._open_chat(active='c1', composer='legacy', turns=30)
        assert self._poll(page, f"() => ({self.LAZY_STATE})().filter(t => t.lazy).length === 26", timeout=4000), \
            f'expected 26 older turns marked lazy, got {self._lazy_count(page)}'
        state = page.evaluate(self.LAZY_STATE)
        assert all(t['cv'] == 'auto' and t['size'] == '300px' for t in state[:26]), \
            'lazy turns must use content-visibility:auto with their measured height as placeholder'
        assert all(not t['lazy'] and t['cv'] == 'visible' for t in state[26:]), \
            'the most recent turns must always render normally'

        # A new message shifts the window: turn 27 becomes lazy, the newest 4 stay rendered.
        page.evaluate("""() => { const t = document.createElement('section');
            t.dataset.testid = 'conversation-turn-31'; t.className = 'turn'; t.textContent = 'turn 31';
            document.getElementById('thread').append(t); }""")
        assert self._poll(page, f"() => ({self.LAZY_STATE})().filter(t => t.lazy).length === 27", timeout=4000)
        assert [t['lazy'] for t in page.evaluate(self.LAZY_STATE)[-4:]] == [False] * 4

    def test_short_chat_is_not_lazy(self):
        self._configure()
        page = self._open_chat(active='c1', composer='legacy', turns=10)
        page.wait_for_timeout(600)
        assert self._lazy_count(page) == 0, 'chats under the threshold must render normally'

    def test_disabling_long_chat_rendering_applies_live(self):
        self._configure()
        page = self._open_chat(active='c1', composer='legacy', turns=30)
        assert self._poll(page, f"() => ({self.LAZY_STATE})().filter(t => t.lazy).length === 26", timeout=4000)
        self._configure(lazyRenderTurns=False)
        assert self._poll(page, f"""() => ({self.LAZY_STATE})().every(t => !t.lazy && t.cv === 'visible' && !t.size)""",
                          timeout=4000), 'turning the option off must restore normal rendering without reload'

    # ---- Pruning ----

    @pytest.mark.parametrize('turn_tag', ['section', 'article'])
    def test_prunes_oldest_turns(self, turn_tag):
        self._configure(maxChatTurns=2)
        page = self._open_chat(active='c1', composer='legacy', turn_tag=turn_tag, turns=5)
        assert self._poll(page, """() =>
            document.querySelectorAll('[data-testid^="conversation-turn-"]').length === 2""",
            timeout=4000), f'expected 2 remaining {turn_tag} turns'
        remaining = page.evaluate("""() => [...document.querySelectorAll('[data-testid^="conversation-turn-"]')]
            .map(e => e.dataset.testid)""")
        assert remaining == ['conversation-turn-4', 'conversation-turn-5']
        assert page.evaluate("document.querySelectorAll('[data-testid=\"copy-turn-action-button\"]').length") == 2

    # ---- Keyboard ----

    def test_alt_h_toggles_rule_hidden_chats(self):
        self._configure()
        page = self._open_chat()
        disp = "() => getComputedStyle(document.querySelector('#history a[href=\"/c/c4\"]')).display"
        assert page.evaluate(disp) == 'none'
        page.keyboard.press('Alt+KeyH')
        assert self._poll(page, disp + " !== 'none'"), 'Alt+H must reveal rule-hidden chats'
        page.keyboard.press('Alt+KeyH')
        assert self._poll(page, disp + " === 'none'"), 'second Alt+H must hide them again'

    # ---- Dynamic sidebar ----

    def test_title_text_edit_restyles_chat(self):
        self._configure()
        page = self._open_chat()
        page.evaluate("""() => {
            document.querySelector('#history a[href="/c/c5"] span[dir="auto"]').firstChild.data = '[TODO] renamed';
        }""")
        assert self._poll(page, """() =>
            document.querySelector('#history a[href="/c/c5"]').dataset.cth === '1'"""), \
            'in-place title text edits must be re-evaluated'

    def test_replaced_history_root_is_rebound(self):
        self._configure()
        page = self._open_chat()
        page.evaluate("""() => {
            const old = document.getElementById('history');
            const fresh = document.createElement('div');
            fresh.id = 'history';
            fresh.innerHTML = '<a href="/c/n1" data-sidebar-item="true"><div class="truncate">' +
                '<span dir="auto">[BUG] after remount</span></div></a>';
            old.replaceWith(fresh);
        }""")
        assert self._poll(page, """() =>
            document.querySelector('#history a[href="/c/n1"]')?.dataset.cth === '1'"""), \
            'replacement #history must be observed and styled'
        page.evaluate("""() => document.getElementById('history').insertAdjacentHTML('beforeend',
            '<a href="/c/n2" data-sidebar-item="true"><div class="truncate"><span dir="auto">[TODO] later</span></div></a>')""")
        assert self._poll(page, """() =>
            document.querySelector('#history a[href="/c/n2"]')?.dataset.cth === '1'"""), \
            'chats added after remount must be styled'

    def test_overlay_clears_and_recovers_when_sidebar_unmounts(self):
        self._configure()
        page = self._open_chat(active='c1', composer='legacy')
        assert self._overlay_visible(page)
        assert self._poll(page, "() => getComputedStyle(document.getElementById('native-scroll')).display === 'none'")

        page.evaluate("window.__history = document.getElementById('history'); window.__history.remove()")
        assert self._overlay_hidden(page), 'overlay must not describe a detached sidebar'
        assert self._poll(page, "() => getComputedStyle(document.getElementById('native-scroll')).display !== 'none'"), \
            'native scroll control must return while the sidebar is gone'

        page.evaluate("document.querySelector('nav[aria-label=\"Sidebar\"]').append(window.__history)")
        assert self._overlay_visible(page), 'overlay must return when the sidebar re-mounts'
        assert self._poll(page, "() => getComputedStyle(document.getElementById('native-scroll')).display === 'none'")

    # ---- Filters + live config ----

    def test_multiselect_filter_persists_across_reload(self):
        self._configure()
        page = self._open_chat()
        page.wait_for_selector('#cth-filter-bar.cth-visible')
        page.click('#cth-filter-bar .cth-pill:has-text("[TODO]")')
        page.click('#cth-filter-bar .cth-pill:has-text("[BUG]")')
        visible = """() => [...document.querySelectorAll('#history a[data-sidebar-item]')]
            .filter(a => getComputedStyle(a).display !== 'none').map(a => a.getAttribute('href'))"""
        assert page.evaluate(visible) == ['/c/c1', '/c/c2']
        page.wait_for_timeout(700)  # > 400ms save debounce
        page.reload()
        page.wait_for_selector('#history a[data-cth="1"]', state='attached')
        assert self._poll(page, visible + ".join() === '/c/c1,/c/c2'", timeout=4000), \
            'filter selection must survive reload'

    def test_live_config_change_restyles_without_reload(self):
        self._configure()
        page = self._open_chat()
        assert self._sidebar_state(page)['c5']['cth'] is None
        self._configure(rules=CONTENT_RULES + [
            {'tag': 'plain', 'match': 'includes', 'color': '#d3869b', 'hide': False, 'overlay': True}])
        assert self._poll(page, """() =>
            document.querySelector('#history a[href="/c/c5"]').dataset.cth === '1'"""), \
            'saved rule changes must apply live'

    def test_legacy_quick_tag_pick_and_undo(self):
        self._configure()
        page = self._open_chat()
        calls, _ = self._mock_chat_api(page)
        link = '#history a[href="/c/c5"]'
        span = f"document.querySelector('{link} .truncate span[dir=auto]')"
        page.hover(link)
        page.wait_for_selector('#cth-qt-btn', state='visible')
        # Legacy rows have no native menu button: align to the anchor's own right edge.
        gap = page.evaluate(f"""() => document.querySelector('{link}').getBoundingClientRect().right - 8
            - document.getElementById('cth-qt-btn').getBoundingClientRect().right""")
        assert abs(gap) <= 4, gap
        page.evaluate(f"window.__node = {span}.firstChild")
        page.click('#cth-qt-btn')
        page.click('#cth-qt-menu [data-tag="[BUG]"]')
        assert self._poll(page, f"() => {span}.textContent === '[BUG] plain chat'")
        assert page.evaluate(f"{span}.firstChild === window.__node && {span}.childNodes.length === 1")
        patches = self._patches(calls)
        assert len(patches) == 1 and patches[0]['url'].endswith('/c5')
        assert patches[0]['auth'] == 'Bearer test-token'
        page.click('#cth-qt-toast .cth-qt-undo')
        assert self._poll(page, f"() => {span}.textContent === 'plain chat'")
        assert len(self._patches(calls)) == 2
        assert [c['method'] for c in calls if '/backend-api/conversation/' in c['url']] == ['PATCH', 'GET', 'PATCH']

    # ---- Delete untagged chats (ChatGPT's private API is mocked; never live) ----

    def _mock_chat_api(self, page, chats=None, session_token='test-token',
                       server_limit=None, patch_status=None, hold_first_patch=False,
                       hold_list_pass=None, patch_body=None, patch_abort=False,
                       patch_statuses=None, hold_session=False, hold_session_at=None,
                       hold_patch_at=None, session_abort=False, titles=None, get_status=None):
        """Mock /api/auth/session, the conversation list, and per-chat PATCH.

        Records every API request in the returned list. `server_limit` caps
        the page size the mock server returns, like a real server might.
        `hold_list_pass` holds the first page of that listing pass (0 = preview,
        1 = the re-check at confirm time) until the test fulfills it.
        `hold_session` holds the first session request; `patch_statuses`
        answers the Nth PATCH with the Nth status; `hold_session_at` /
        `hold_patch_at` hold the Nth session / PATCH request (1-based);
        `session_abort` fails session requests at the network level;
        `titles` is a chat id -> title store (pass one dict to several pages to
        share server state): a successful PATCH {title} updates it and
        GET /backend-api/conversation/{id} returns it (`get_status` overrides);
        `patch_abort` fails PATCHes
        at the network level.
        """
        chats = API_CHATS if chats is None else chats
        calls = []
        held = []
        passes = {'n': -1}  # listing passes started (a pass begins at offset=0)
        pn = {'n': 0}  # PATCHes answered so far
        arrived = {'session': 0, 'patch': 0}
        titles = {} if titles is None else titles

        def record(route):
            req = route.request
            calls.append({'method': req.method, 'url': req.url,
                          'auth': req.all_headers().get('authorization'),
                          'body': req.post_data})

        def session(route):
            record(route)
            arrived['session'] += 1
            if (hold_session and not held) or hold_session_at == arrived['session']:
                held.append(route)  # fulfilled later by the test
                return
            if session_abort:
                return route.abort()
            body = {'accessToken': session_token} if session_token else {}
            route.fulfill(status=200, content_type='application/json', body=json.dumps(body))

        def listing(route):
            record(route)
            q = dict(p.split('=', 1) for p in route.request.url.split('?', 1)[1].split('&'))
            offset, limit = int(q.get('offset', 0)), int(q.get('limit', 28))
            if server_limit:
                limit = min(limit, server_limit)
            if offset == 0:
                passes['n'] += 1
            data = chats(passes['n']) if callable(chats) else chats
            items = data[offset:offset + limit]
            body = json.dumps({'items': items, 'total': len(data), 'limit': limit, 'offset': offset})
            if offset == 0 and passes['n'] == hold_list_pass:
                held.append((route, body))  # fulfilled later by the test
                return
            route.fulfill(status=200, content_type='application/json', body=body)

        def conversation(route):
            if route.request.method == 'GET':
                record(route)
                cid = route.request.url.rsplit('/', 1)[1]
                status = get_status or (200 if cid in titles else 404)
                body = {'id': cid, 'title': titles[cid]} if status == 200 else {'detail': 'conversation_not_found'}
                return route.fulfill(status=status, content_type='application/json', body=json.dumps(body))
            return patch(route)

        def patch(route):
            record(route)
            arrived['patch'] += 1
            if (hold_first_patch and not held) or hold_patch_at == arrived['patch']:
                held.append(route)  # fulfilled later by the test
                return
            pn['n'] += 1
            if patch_abort:
                return route.abort()
            status = patch_statuses[pn['n'] - 1] if patch_statuses else (patch_status or 200)
            body = patch_body if patch_body is not None else {'success': status == 200}
            sent = json.loads(route.request.post_data or '{}')
            if status == 200 and body.get('success') is not False and 'title' in sent:
                titles[route.request.url.rsplit('/', 1)[1]] = sent['title']
            route.fulfill(status=status, content_type='application/json', body=json.dumps(body))

        page.route('https://chatgpt.com/api/auth/session', session)
        page.route('https://chatgpt.com/backend-api/conversations?*', listing)
        page.route('https://chatgpt.com/backend-api/conversation/*', conversation)
        return calls, held

    def _open_delete_page(self, **mock_kwargs):
        self._configure(showDeleteUntagged=True)
        page = self._open_chat(chats=[('a1', '[TODO] ship'), ('a2', 'plain chat'), ('a8', '[BUG] crash')])
        calls, held = self._mock_chat_api(page, **mock_kwargs)
        page.wait_for_selector('#cth-delete-untagged', state='visible')
        return page, calls, held

    @staticmethod
    def _patches(calls):
        return [c for c in calls if c['method'] == 'PATCH']

    def test_delete_untagged_button_is_opt_in(self):
        self._configure()
        page = self._open_chat()
        page.wait_for_selector('#cth-filter-bar.cth-visible')
        page.wait_for_timeout(300)
        assert page.query_selector('#cth-delete-untagged') is None, 'button must be off by default'
        self._configure(showDeleteUntagged=True)
        assert self._poll(page, "() => !!document.querySelector('#cth-filter-bar.cth-visible #cth-delete-untagged')"), \
            'enabling the option must add the button live'
        # With a single visible rule there are no pills, but the button still needs a home.
        self._configure(showDeleteUntagged=True, rules=[CONTENT_RULES[0]])
        assert self._poll(page, """() => {
            const bar = document.querySelector('#cth-filter-bar.cth-visible');
            return !!bar && !bar.querySelector('.cth-pill') && !!bar.querySelector('#cth-delete-untagged');
        }"""), 'the bar must show just the button when there are too few rules for pills'

    def test_delete_untagged_previews_then_deletes_only_untagged(self):
        page, calls, _ = self._open_delete_page(server_limit=4)
        page.click('#cth-delete-untagged')
        page.wait_for_selector('#cth-delete-dialog .cth-del-list li', timeout=5000)
        titles = page.evaluate("[...document.querySelectorAll('#cth-delete-dialog .cth-del-list li')].map(li => li.textContent)")
        assert titles == ['plain chat', 'Untitled chat', '<img src=x onerror="window.__xss=1">'], titles
        assert page.evaluate("!window.__xss && !document.querySelector('#cth-delete-dialog img')"), \
            'titles must render as text'
        status = page.text_content('#cth-delete-dialog .cth-del-status')
        assert '3 untagged chats' in status and '5 tagged' in status and '3 pinned, starred or archived' in status, status

        gets = [c for c in calls if c['method'] == 'GET' and '/backend-api/' in c['url']]
        assert [re.search(r'offset=(\d+)', c['url']).group(1) for c in gets] == ['0', '4', '8', '11'], \
            'must page by items received until an empty page, even when the server caps the page size'
        assert all(c['auth'] == 'Bearer test-token' for c in gets)
        assert self._patches(calls) == [], 'nothing may be deleted before confirmation'

        confirm = '#cth-delete-dialog .cth-del-confirm-btn'
        assert page.is_disabled(confirm)
        page.fill('#cth-delete-dialog .cth-del-input', 'Delete it')
        assert page.is_disabled(confirm), 'only the exact word enables deletion'
        page.fill('#cth-delete-dialog .cth-del-input', 'delete')
        assert page.is_enabled(confirm)
        page.click(confirm)

        assert self._poll(page, "() => /Deleted 3 of 3 chats/.test(document.querySelector('#cth-delete-dialog .cth-del-status').textContent)",
                          timeout=8000), page.text_content('#cth-delete-dialog .cth-del-status')
        patches = self._patches(calls)
        assert [c['url'].rsplit('/', 1)[1] for c in patches] == ['a2', 'a7', 'a9']
        assert all(json.loads(c['body']) == {'is_visible': False} for c in patches)
        assert all(c['auth'] == 'Bearer test-token' for c in patches)
        s = self._sidebar_state(page)
        assert s['a2']['display'] == 'none', 'deleted chats leave the sidebar right away'
        assert s['a1']['display'] != 'none' and s['a8']['display'] != 'none'
        assert page.is_visible('#cth-delete-dialog .cth-del-reload')

    def test_delete_untagged_cancel_and_escape_delete_nothing(self):
        page, calls, _ = self._open_delete_page()
        page.click('#cth-delete-untagged')
        page.wait_for_selector('#cth-delete-dialog .cth-del-list li', timeout=5000)
        page.fill('#cth-delete-dialog .cth-del-input', 'delete')
        page.click('#cth-delete-dialog .cth-del-cancel')
        assert self._poll(page, "() => !document.getElementById('cth-delete-dialog')")
        assert page.evaluate("document.activeElement?.id") == 'cth-delete-untagged', \
            'focus returns to the button'

        page.click('#cth-delete-untagged')
        page.wait_for_selector('#cth-delete-dialog .cth-del-list li', timeout=5000)
        page.fill('#cth-delete-dialog .cth-del-input', 'delete')
        page.keyboard.press('Escape')
        assert self._poll(page, "() => !document.getElementById('cth-delete-dialog')")
        page.wait_for_timeout(300)
        assert self._patches(calls) == []

    def test_delete_untagged_stops_at_first_error(self):
        page, calls, _ = self._open_delete_page(patch_status=500)
        page.click('#cth-delete-untagged')
        page.wait_for_selector('#cth-delete-dialog .cth-del-list li', timeout=5000)
        page.fill('#cth-delete-dialog .cth-del-input', 'delete')
        page.click('#cth-delete-dialog .cth-del-confirm-btn')
        assert self._poll(page, "() => /HTTP 500/.test(document.querySelector('#cth-delete-dialog .cth-del-status').textContent)",
                          timeout=5000), page.text_content('#cth-delete-dialog .cth-del-status')
        page.wait_for_timeout(800)
        assert len(self._patches(calls)) == 1, 'must not keep deleting after a failure'
        assert self._sidebar_state(page)['a2']['display'] != 'none', 'a failed delete stays in the sidebar'

    def test_delete_untagged_stops_when_ok_response_reports_failure(self):
        page, calls, _ = self._open_delete_page(patch_body={'success': False})
        page.click('#cth-delete-untagged')
        page.wait_for_selector('#cth-delete-dialog .cth-del-list li', timeout=5000)
        page.fill('#cth-delete-dialog .cth-del-input', 'delete')
        page.click('#cth-delete-dialog .cth-del-confirm-btn')
        assert self._poll(page, "() => /didn't go through/.test(document.querySelector('#cth-delete-dialog .cth-del-status').textContent)",
                          timeout=5000), page.text_content('#cth-delete-dialog .cth-del-status')
        page.wait_for_timeout(800)
        assert len(self._patches(calls)) == 1, 'an explicit {"success": false} must stop the run'
        assert 'Deleted 0 of 3 chats' in page.text_content('#cth-delete-dialog .cth-del-status')
        assert self._sidebar_state(page)['a2']['display'] != 'none', 'a failed delete stays in the sidebar'
        assert not page.is_visible('#cth-delete-dialog .cth-del-reload'), 'nothing was deleted, so no reload prompt'

    def test_delete_untagged_stop_finishes_current_chat_only(self):
        page, calls, held = self._open_delete_page(hold_first_patch=True)
        try:
            page.click('#cth-delete-untagged')
            page.wait_for_selector('#cth-delete-dialog .cth-del-list li', timeout=5000)
            page.fill('#cth-delete-dialog .cth-del-input', 'delete')
            page.click('#cth-delete-dialog .cth-del-confirm-btn')
            deadline = time.time() + 5
            while not held and time.time() < deadline:
                page.wait_for_timeout(50)
            assert held, 'first delete request never arrived'
            page.click('#cth-delete-dialog .cth-del-cancel')  # labelled Stop while running
            assert page.query_selector('#cth-delete-dialog'), 'Stop must not close the dialog mid-request'
            held[0].fulfill(status=200, content_type='application/json', body='{"success":true}')
            held.clear()
            assert self._poll(page, "() => /Stopped/.test(document.querySelector('#cth-delete-dialog .cth-del-status').textContent)",
                              timeout=5000), page.text_content('#cth-delete-dialog .cth-del-status')
            page.wait_for_timeout(800)
            assert len(self._patches(calls)) == 1, 'Stop must prevent any further deletes'
            assert 'Deleted 1 of 3' in page.text_content('#cth-delete-dialog .cth-del-status')
        finally:
            for r in held:
                try:
                    r.fulfill(status=200, body='{}')
                except Exception:
                    pass

    def test_delete_untagged_merges_duplicate_records_conservatively(self):
        # The list shifted while paging: x1 first shows up plain, then tagged and pinned.
        overlapping = [
            _api_chat('x1', 'plain'), _api_chat('y1', 'plain two'),
            _api_chat('x1', '[TODO] now tagged', pinned_time='2026-09-02T00:00:00Z'), _api_chat('z1', 'plain three'),
        ]
        page, calls, _ = self._open_delete_page(chats=overlapping, server_limit=2)
        page.click('#cth-delete-untagged')
        page.wait_for_selector('#cth-delete-dialog .cth-del-list li', timeout=5000)
        ids = page.evaluate("[...document.querySelectorAll('#cth-delete-dialog .cth-del-list li')].map(li => li.dataset.id)")
        assert ids == ['y1', 'z1'], f'a chat seen tagged or pinned in any copy must be kept, got {ids}'

    def test_delete_untagged_rechecks_before_deleting(self):
        renamed = [dict(c, title='[TODO] tagged meanwhile') if c['id'] == 'a2' else c
                   for c in API_CHATS if c['id'] != 'a7']  # a2 renamed, a7 deleted elsewhere
        page, calls, _ = self._open_delete_page(chats=lambda n: API_CHATS if n == 0 else renamed)
        page.click('#cth-delete-untagged')
        page.wait_for_selector('#cth-delete-dialog .cth-del-list li', timeout=5000)
        assert page.evaluate("document.querySelectorAll('#cth-delete-dialog .cth-del-list li').length") == 3
        page.fill('#cth-delete-dialog .cth-del-input', 'delete')
        page.click('#cth-delete-dialog .cth-del-confirm-btn')
        assert self._poll(page, "() => /Deleted 1 of 1 chat/.test(document.querySelector('#cth-delete-dialog .cth-del-status').textContent)",
                          timeout=8000), page.text_content('#cth-delete-dialog .cth-del-status')
        assert [c['url'].rsplit('/', 1)[1] for c in self._patches(calls)] == ['a9'], \
            'chats that changed after the preview must not be deleted'
        assert 'Skipped 2 chats that changed since the preview' in page.text_content('#cth-delete-dialog .cth-del-status')

    def test_delete_untagged_cancel_during_recheck_closes_and_stops_listing(self):
        page, calls, held = self._open_delete_page(server_limit=4, hold_list_pass=1)
        try:
            page.click('#cth-delete-untagged')
            page.wait_for_selector('#cth-delete-dialog .cth-del-list li', timeout=5000)
            page.fill('#cth-delete-dialog .cth-del-input', 'delete')
            page.click('#cth-delete-dialog .cth-del-confirm-btn')
            deadline = time.time() + 5
            while not held and time.time() < deadline:
                page.wait_for_timeout(50)
            assert held, 're-check request never arrived'
            assert page.text_content('#cth-delete-dialog .cth-del-cancel') == 'Cancel'
            page.keyboard.press('Escape')
            assert self._poll(page, "() => !document.getElementById('cth-delete-dialog')"), \
                'nothing is deleted yet, so the dialog must close even while the re-check is stalled'
            route, body = held.pop()
            route.fulfill(status=200, content_type='application/json', body=body)
            page.wait_for_timeout(800)
            lists = [c for c in calls if c['method'] == 'GET' and '/backend-api/conversations' in c['url']]
            assert len(lists) == 5, f'the re-check must stop paging once closed (4 preview pages + 1), got {len(lists)}'
            assert self._patches(calls) == []
        finally:
            for route, body in held:
                try:
                    route.fulfill(status=200, body=body)
                except Exception:
                    pass

    def test_delete_untagged_signed_out_makes_no_api_calls(self):
        page, calls, _ = self._open_delete_page(session_token=None)
        page.click('#cth-delete-untagged')
        assert self._poll(page, "() => /Sign in/i.test(document.querySelector('#cth-delete-dialog .cth-del-status')?.textContent || '')",
                          timeout=5000)
        assert [c for c in calls if '/backend-api/' in c['url']] == [], 'no list or delete calls without a session'
        assert not page.is_visible('#cth-delete-dialog .cth-del-input')

    # ---- Choosing which untagged chats to delete (#70) ----

    CHECKBOXES = '#cth-delete-dialog .cth-del-list input[type="checkbox"]'
    SEL_COUNT = '#cth-delete-dialog .cth-del-count'
    CONFIRM = '#cth-delete-dialog .cth-del-confirm-btn'

    def _checked_ids(self, page):
        return page.evaluate(f"[...document.querySelectorAll('{self.CHECKBOXES}')].filter(c => c.checked).map(c => c.dataset.id)")

    def test_delete_untagged_rows_start_selected(self):
        page, calls, _ = self._open_delete_page()
        page.click('#cth-delete-untagged')
        page.wait_for_selector(self.CHECKBOXES, timeout=5000)
        assert self._checked_ids(page) == ['a2', 'a7', 'a9'], 'every listed chat starts selected'
        assert page.text_content(self.SEL_COUNT) == '3 of 3 selected'
        assert page.text_content(self.CONFIRM) == 'Delete 3 chats'
        assert page.evaluate("!window.__xss && !document.querySelector('#cth-delete-dialog img')"), \
            'titles must still render as text next to the checkboxes'

    def test_delete_untagged_deletes_only_selected_chats(self):
        page, calls, _ = self._open_delete_page()
        page.click('#cth-delete-untagged')
        page.wait_for_selector(self.CHECKBOXES, timeout=5000)
        page.uncheck(f'{self.CHECKBOXES}[data-id="a2"]')
        page.click('#cth-delete-dialog .cth-del-list li[data-id="a9"] label')  # the title toggles too
        assert self._checked_ids(page) == ['a7']
        assert page.text_content(self.SEL_COUNT) == '1 of 3 selected'
        assert page.text_content(self.CONFIRM) == 'Delete 1 chat'
        page.fill('#cth-delete-dialog .cth-del-input', 'delete')
        page.click(self.CONFIRM)
        assert self._poll(page, "() => /Deleted 1 of 1 chat\\./.test(document.querySelector('#cth-delete-dialog .cth-del-status').textContent)",
                          timeout=8000), page.text_content('#cth-delete-dialog .cth-del-status')
        assert [c['url'].rsplit('/', 1)[1] for c in self._patches(calls)] == ['a7'], 'unselected chats must never be deleted'
        assert 'Skipped' not in page.text_content('#cth-delete-dialog .cth-del-status'), \
            'unselected chats are kept by choice, not skipped'
        assert self._sidebar_state(page)['a2']['display'] != 'none'
        assert page.evaluate(f"[...document.querySelectorAll('{self.CHECKBOXES}')].every(c => c.disabled)"), \
            'the selection is frozen once deleting starts'

    def test_delete_untagged_select_none_and_all(self):
        page, calls, _ = self._open_delete_page()
        page.click('#cth-delete-untagged')
        page.wait_for_selector(self.CHECKBOXES, timeout=5000)
        page.fill('#cth-delete-dialog .cth-del-input', 'delete')
        assert page.is_enabled(self.CONFIRM)
        page.click('#cth-delete-dialog .cth-del-none')
        assert self._checked_ids(page) == []
        assert page.text_content(self.SEL_COUNT) == '0 of 3 selected'
        assert page.is_disabled(self.CONFIRM), 'nothing selected, nothing to delete'
        page.focus('#cth-delete-dialog .cth-del-input')
        page.keyboard.press('Enter')
        page.wait_for_timeout(200)
        assert page.is_enabled('#cth-delete-dialog .cth-del-input'), \
            'Enter in the confirm box must not bypass the empty selection'
        page.focus(f'{self.CHECKBOXES}[data-id="a9"]')
        page.keyboard.press('Space')
        assert self._checked_ids(page) == ['a9'], 'Space toggles a focused checkbox'
        assert page.is_enabled(self.CONFIRM)
        page.keyboard.press('Enter')
        assert page.query_selector('#cth-delete-dialog .cth-del-input:not([disabled])'), \
            'Enter on a checkbox must not start deleting'
        page.click('#cth-delete-dialog .cth-del-all')
        assert self._checked_ids(page) == ['a2', 'a7', 'a9']
        assert page.text_content(self.CONFIRM) == 'Delete 3 chats'
        for cid in ('a2', 'a7', 'a9'):
            page.uncheck(f'{self.CHECKBOXES}[data-id="{cid}"]')
        assert page.is_disabled(self.CONFIRM), 'unchecking the last chat disables deletion too'
        page.click('#cth-delete-dialog .cth-del-all')
        page.fill('#cth-delete-dialog .cth-del-input', 'nope')
        assert page.is_disabled(self.CONFIRM), 'selecting chats never bypasses the confirmation word'
        page.focus('#cth-delete-dialog .cth-del-input')
        page.keyboard.press('Enter')
        page.wait_for_timeout(300)
        assert self._patches(calls) == [], 'changing the selection never deletes anything'

        page.uncheck(f'{self.CHECKBOXES}[data-id="a2"]')
        page.fill('#cth-delete-dialog .cth-del-input', 'delete')
        page.keyboard.press('Enter')  # focus is in the confirm box
        assert self._poll(page, "() => /Deleted 2 of 2 chats/.test(document.querySelector('#cth-delete-dialog .cth-del-status').textContent)",
                          timeout=8000), page.text_content('#cth-delete-dialog .cth-del-status')
        assert [c['url'].rsplit('/', 1)[1] for c in self._patches(calls)] == ['a7', 'a9'], \
            'Enter in the confirm box deletes exactly the checked chats'

    def test_delete_untagged_focus_trap_includes_checkboxes(self):
        page, _, _ = self._open_delete_page()
        page.click('#cth-delete-untagged')
        page.wait_for_selector(self.CHECKBOXES, timeout=5000)
        focusables = """() => [...document.querySelectorAll('#cth-delete-dialog .cth-del-box button, #cth-delete-dialog .cth-del-box input')]
            .filter(n => !n.disabled && !n.closest('[hidden]'))"""
        # Walk real Tab presses from Select none: each checkbox must take focus in order.
        page.focus('#cth-delete-dialog .cth-del-none')
        forward = []
        for _ in range(3):
            page.keyboard.press('Tab')
            forward.append(page.evaluate("document.activeElement.dataset.id || null"))
        assert forward == ['a2', 'a7', 'a9'], f'Tab must step through every checkbox, got {forward}'
        backward = []
        for _ in range(2):
            page.keyboard.press('Shift+Tab')
            backward.append(page.evaluate("document.activeElement.dataset.id || null"))
        assert backward == ['a7', 'a2'], f'Shift+Tab must step back through the checkboxes, got {backward}'
        page.evaluate(f"({focusables})().at(-1).focus()")
        page.keyboard.press('Tab')
        assert page.evaluate(f"document.activeElement === ({focusables})()[0]"), 'Tab from the last control wraps to the first'
        page.keyboard.press('Shift+Tab')
        assert page.evaluate(f"document.activeElement === ({focusables})().at(-1)"), 'Shift+Tab from the first wraps to the last'

    def test_delete_untagged_recheck_respects_selection(self):
        renamed = [dict(c, title='[TODO] tagged meanwhile') if c['id'] == 'a2' else c
                   for c in API_CHATS] + [_api_chat('n1', 'brand new plain chat')]  # a2 tagged, n1 new since the preview
        page, calls, held = self._open_delete_page(chats=lambda n: API_CHATS if n == 0 else renamed,
                                                   hold_list_pass=1)
        try:
            page.click('#cth-delete-untagged')
            page.wait_for_selector(self.CHECKBOXES, timeout=5000)
            page.uncheck(f'{self.CHECKBOXES}[data-id="a9"]')
            page.fill('#cth-delete-dialog .cth-del-input', 'delete')
            page.click(self.CONFIRM)
            deadline = time.time() + 5
            while not held and time.time() < deadline:
                page.wait_for_timeout(50)
            assert held, 're-check request never arrived'
            assert page.evaluate("""() => [...document.querySelectorAll('#cth-delete-dialog .cth-del-list input, #cth-delete-dialog .cth-del-all, #cth-delete-dialog .cth-del-none')]
                .every(n => n.disabled)"""), 'the selection is frozen from confirm onward, including the re-check'
            route, body = held.pop()
            route.fulfill(status=200, content_type='application/json', body=body)
            assert self._poll(page, "() => /Deleted 1 of 1 chat\\./.test(document.querySelector('#cth-delete-dialog .cth-del-status').textContent)",
                              timeout=8000), page.text_content('#cth-delete-dialog .cth-del-status')
            assert [c['url'].rsplit('/', 1)[1] for c in self._patches(calls)] == ['a7'], \
                'only selected chats that are still untagged are deleted; new chats never are'
            status = page.text_content('#cth-delete-dialog .cth-del-status')
            assert 'Skipped 1 chat that changed since the preview' in status, status
            assert page.evaluate("[...document.querySelectorAll('#cth-delete-dialog .cth-del-list li.cth-done')].map(li => li.dataset.id)") == ['a7']
        finally:
            for route, body in held:
                try:
                    route.fulfill(status=200, body=body)
                except Exception:
                    pass


# App-shell layout inspected live on 2026-09-28. No legacy discovery hooks:
# fixture-only IDs let tests inspect rows without coupling to extension markers.
def _app_shell_fixture(chats=DEFAULT_CHATS, active='c1', turns=6, sidebar_height=None):
    rows = []
    for i, (cid, title) in enumerate(chats):
        selected = ' aria-current="page"' if cid == active else ''
        row = (f'<div role="group" id="row-{cid}"{selected}>'
               f'<div data-thread-title-trigger><a data-interactive-row-link="true" '
               f'href="/c/{cid}"{selected}><span data-thread-title="true">'
               f'<span data-marquee-content><span dir="auto">{_html.escape(title)}</span>'
               f'</span></span></a></div><button class="menu">menu</button></div>')
        rows.append(f'<div role="listitem" id="item-{cid}">{row}</div>' if i < 2 else row)
    groups = ''.join(
        f'<div data-turn-key="t{i}" class="turn"><div data-content-search-turn-key="t{i}">'
        f'<div data-user-message-bubble>User {i}</div>'
        f'<div data-conversation-role="assistant">Reply {i}</div></div></div>'
        for i in range(turns))
    return f'''<!doctype html><html class="dark"><head><meta charset="utf-8">
    <title>App-shell fixture</title><style>
    body {{margin:0;display:flex;height:100vh}} #app-shell-sidebar {{width:260px;flex-shrink:0}}
    [data-app-action-sidebar-scroll] {{height:{f'{sidebar_height}px' if sidebar_height else '100%'};overflow:auto}}
    [role=group] {{display:flex;background:rgb(30,30,30);padding:8px;position:relative}}
    [data-thread-title-trigger] {{flex:1}} a {{display:block}}
    [role=listitem] {{padding-bottom:4px}} main {{flex:1;min-width:0}}
    [data-app-action-timeline-scroll] {{height:100vh;overflow:auto;position:relative}}
    .turn {{height:300px}} #composer {{position:sticky;bottom:0;margin:12px auto;width:80%;height:60px;background:white}}
    #editor {{height:40px}} #native {{position:fixed;right:30px;bottom:95px}}
    </style></head><body><aside id="app-shell-sidebar"><nav>
    <div data-app-action-sidebar-scroll><section data-app-action-sidebar-section>
    <div role="list">{''.join(rows[:2])}</div></section>
    <section data-app-action-sidebar-section>{''.join(rows[2:])}</section>
    <a id="other-nav" href="/c/not-a-row">Not a chat row</a></div></nav></aside>
    <main><div data-app-action-timeline-scroll><div id="thread">{groups}</div>
    <button id="native" class="group/scroll-to-bottom" aria-label="Scroll to bottom">down</button>
    <form id="composer" data-chatgpt-composer data-composer-placement="thread">
    <div id="editor" contenteditable="true" data-composer-markdown></div></form></div></main>
    </body></html>'''


class TestAppShellContentScript:
    setup = TestContentScript.setup
    _configure = TestContentScript._configure
    _poll = staticmethod(TestContentScript._poll)
    _overlay_visible = TestContentScript._overlay_visible
    _overlay_hidden = TestContentScript._overlay_hidden
    _mock_chat_api = TestContentScript._mock_chat_api
    _patches = staticmethod(TestContentScript._patches)

    def _open_chat(self, **kwargs):
        body = _app_shell_fixture(**kwargs)
        page = self.context.new_page()
        self._pages.append(page)
        page.route('https://chatgpt.com/**', lambda r: r.fulfill(
            status=200, content_type='text/html', body=body))
        page.goto('https://chatgpt.com/c/c1')
        page.wait_for_selector('#cth-style', state='attached')
        return page

    def _ready(self, page):
        assert self._poll(page, "() => !!document.querySelector('#cth-filter-bar.cth-visible')"), \
            'current sidebar must be discovered without #history'

    def test_full_row_highlight_hide_filter_badge_and_theme(self):
        self._configure(dimUntagged=True)
        page = self._open_chat()
        self._ready(page)
        assert not page.locator('#history, #prompt-textarea, [data-sidebar-item]').count()
        assert page.eval_on_selector('#row-c1', "e => getComputedStyle(e).backgroundColor") == 'rgba(250, 189, 47, 0.2)'
        assert page.eval_on_selector('#row-c2', "e => getComputedStyle(e).backgroundColor") == 'rgba(251, 73, 52, 0.12)'
        assert page.eval_on_selector('#row-c1', "e => getComputedStyle(e, '::before').width") == '6px'
        ring = page.eval_on_selector('#row-c1', "e => getComputedStyle(e).boxShadow")
        assert 'inset' in ring and 'rgba(250, 189, 47, 0.55)' in ring and '1px' in ring, ring
        assert not page.is_visible('#row-c4 .menu')
        assert page.eval_on_selector('#row-c5', "e => getComputedStyle(e).opacity") == '0.45'
        assert page.eval_on_selector('#other-nav', "e => [...e.attributes].every(a => !a.name.startsWith('data-cth'))")
        opts = self.context.new_page()
        self._pages.append(opts)
        opts.goto(f'chrome-extension://{self.ext_id}/options.html')
        assert self._poll(opts, "async () => (await chrome.action.getBadgeText({})) === '3'")
        page.locator('.cth-pill', has_text='[BUG]').click()
        assert not page.is_visible('#item-c1') and not page.is_visible('#row-c1 .menu')
        assert page.is_visible('#item-c2')
        page.locator('.cth-pill', has_text='All').click()
        page.keyboard.press('Alt+h')
        assert page.is_visible('#row-c4 .menu')
        page.keyboard.press('Alt+h')
        assert not page.is_visible('#row-c4')
        page.evaluate("document.documentElement.classList.replace('dark', 'light')")
        assert self._poll(page, "() => getComputedStyle(document.querySelector('#row-c1')).backgroundColor === 'rgba(250, 189, 47, 0.16)'")

    def test_selected_untagged_row_is_visible_and_selection_moves(self):
        self._configure(dimUntagged=True)
        page = self._open_chat(active='c5')
        self._ready(page)
        assert page.eval_on_selector('#row-c5', "e => getComputedStyle(e).opacity") == '1'
        assert 'inset' in page.eval_on_selector('#row-c5', "e => getComputedStyle(e).boxShadow")
        # Default neutral highlight with a hollow stripe: selected, but visibly untagged.
        assert page.eval_on_selector('#row-c5', "e => getComputedStyle(e).backgroundColor") == 'rgba(255, 255, 255, 0.08)'
        stripe = page.eval_on_selector('#row-c5', """e => {
            const s = getComputedStyle(e, '::before');
            return {content: s.content, bg: s.backgroundColor, border: s.borderLeftWidth, width: s.width};
        }""")
        assert stripe['content'] != 'none' and stripe['bg'] == 'rgba(0, 0, 0, 0)', stripe
        assert stripe['border'] != '0px' and stripe['width'] == '6px', stripe
        page.evaluate("""() => {
            document.querySelectorAll('[aria-current]').forEach(e=>e.removeAttribute('aria-current'));
            document.querySelector('#row-c2 a').setAttribute('aria-current','page');
        }""")
        assert self._poll(page, "() => getComputedStyle(document.querySelector('#row-c5')).opacity === '0.45'")
        assert 'inset' in page.eval_on_selector('#row-c2', "e => getComputedStyle(e).boxShadow")
        assert page.eval_on_selector('#row-c5', "e => getComputedStyle(e).boxShadow") == 'none'
        assert page.eval_on_selector('#row-c5', "e => getComputedStyle(e, '::before').content") == 'none'

    def test_overlay_nested_scroll_focus_and_composer_remount(self):
        self._configure()
        page = self._open_chat()
        assert self._overlay_visible(page)
        aligned = """() => {
            const o = document.querySelector('#cth-overlay').getBoundingClientRect();
            const c = document.querySelector('#composer').getBoundingClientRect();
            return Math.abs(o.bottom-c.top) <= 2 && Math.abs(o.left-c.left) <= 2 && Math.abs(o.width-c.width) <= 2;
        }"""
        assert self._poll(page, aligned)
        assert not page.is_visible('#native')
        page.evaluate("document.querySelector('[data-app-action-timeline-scroll]').scrollTop = 300")
        assert self._poll(page, aligned)
        page.focus('#editor')
        page.click('#cth-overlay .cth-arrow')
        assert page.evaluate("document.activeElement.id") == 'editor'
        assert self._poll(page, """() => { const s = document.querySelector('[data-app-action-timeline-scroll]');
            return s.scrollTop+s.clientHeight >= s.scrollHeight-2; }""")
        page.evaluate("window.savedComposer=document.querySelector('#composer'); savedComposer.remove()")
        assert self._overlay_hidden(page) and page.is_visible('#native')
        page.evaluate("document.querySelector('[data-app-action-timeline-scroll]').append(savedComposer)")
        assert self._overlay_visible(page)
        page.evaluate("document.querySelectorAll('[aria-current]').forEach(e=>e.removeAttribute('aria-current')); document.querySelector('#row-c5 a').setAttribute('aria-current','page')")
        assert self._overlay_hidden(page) and page.is_visible('#native')

    def test_title_change_row_reuse_root_replacement_and_bar_repair(self):
        self._configure()
        page = self._open_chat()
        self._ready(page)
        page.evaluate("document.querySelector('#row-c5 span[dir=auto]').firstChild.data='[TODO] renamed'")
        assert self._poll(page, "() => getComputedStyle(document.querySelector('#row-c5')).backgroundColor === 'rgba(250, 189, 47, 0.12)'")
        page.evaluate("""() => {
            const old = document.querySelector('#row-c3'); const row = document.createElement('div');
            row.id='row-c3'; row.setAttribute('role','group'); row.append(old.querySelector('a'));
            old.replaceWith(row);
        }""")
        assert self._poll(page, "() => getComputedStyle(document.querySelector('#row-c3')).backgroundColor === 'rgba(131, 165, 152, 0.12)'")
        page.evaluate("document.querySelector('#cth-filter-bar').remove()")
        self._ready(page)
        page.evaluate("""() => {
            const root=document.querySelector('[data-app-action-sidebar-scroll]');
            const copy=root.cloneNode(true); root.replaceWith(copy);
        }""")
        self._ready(page)
        page.locator('.cth-pill', has_text='[BUG]').click()
        assert not page.is_visible('#row-c1') and page.is_visible('#row-c2')
        assert page.locator('#cth-filter-bar').count() == 1
        # Extension writes must settle, not keep triggering the history observer.
        page.evaluate("window.mutations=0; window.mo=new MutationObserver(ms=>mutations+=ms.length); mo.observe(document.querySelector('[data-app-action-sidebar-scroll]'),{attributes:true,subtree:true,childList:true})")
        page.wait_for_timeout(300)
        count = page.evaluate('mutations')
        page.wait_for_timeout(300)
        assert page.evaluate('mutations') == count

    def test_links_swapping_rows_keep_styles_and_hidden_state(self):
        self._configure()
        page = self._open_chat()
        self._ready(page)
        page.evaluate("""() => {
            const a=document.querySelector('#row-c1 a');
            const b=document.querySelector('#row-c4 a');
            const holder=document.createTextNode('');
            a.replaceWith(holder); b.replaceWith(a); holder.replaceWith(b);
        }""")
        assert self._poll(page, """() => {
            const hidden=document.querySelector('#item-c1');
            const painted=document.querySelector('#row-c4');
            return !hidden.getClientRects().length
                && painted.getClientRects().length > 0
                && getComputedStyle(painted).backgroundColor === 'rgba(250, 189, 47, 0.2)';
        }"""), 'one moved link must not erase the row just painted for another link'

    def test_temporary_multi_link_row_does_not_leave_anchor_hidden(self):
        self._configure()
        page = self._open_chat()
        self._ready(page)
        page.locator('.cth-pill', has_text='[BUG]').click()
        page.evaluate("""() => {
            const extra=document.querySelector('#row-c1 a').cloneNode(true);
            extra.id='extra-link'; extra.setAttribute('href','/c/extra');
            document.querySelector('#row-c1').append(extra);
        }""")
        assert self._poll(page, "() => document.querySelector('#row-c1 a').hasAttribute('data-cth-filtered')")
        page.evaluate("document.querySelector('#extra-link').remove()")
        assert self._poll(page, "() => !document.querySelector('#row-c1 a').hasAttribute('data-cth-row')")
        page.locator('.cth-pill', has_text='All').click()
        assert page.is_visible('#row-c1 a'), 'fallback anchor filtering must clear when its row returns'
        assert not page.locator('#row-c1 a[data-cth-row]').count(), 'paint the row only, not two stripes'

    def test_reversed_timeline_scrolls_to_zero(self):
        self._configure()
        page = self._open_chat()
        assert self._overlay_visible(page)
        page.evaluate("""() => {
            const s=document.querySelector('[data-app-action-timeline-scroll]');
            s.style.display='flex'; s.style.flexDirection='column-reverse';
            document.querySelector('#thread').style.flexShrink='0';
            document.querySelector('#composer').style.position='fixed';
            s.scrollTop=-400;
        }""")
        assert page.eval_on_selector('[data-app-action-timeline-scroll]', 'e => e.scrollTop') < 0
        page.click('#cth-overlay .cth-arrow')
        assert self._poll(page, "() => Math.abs(document.querySelector('[data-app-action-timeline-scroll]').scrollTop) < 2")

    def test_current_turn_groups_lazy_and_atomic_pruning(self):
        self._configure(lazyRenderTurns=True)
        page = self._open_chat(turns=24)
        assert self._poll(page, "() => document.querySelectorAll('[data-cth-lazy]').length === 20")
        assert page.eval_on_selector('[data-turn-key]', "e => getComputedStyle(e).contentVisibility") == 'auto'
        self._configure(maxChatTurns=3, lazyRenderTurns=False)
        assert self._poll(page, "() => document.querySelectorAll('[data-turn-key]').length === 3")
        assert page.locator('[data-user-message-bubble]').count() == 3
        assert page.locator('[data-conversation-role=assistant]').count() == 3
        assert page.locator('[data-cth-lazy]').count() == 0

    def test_rule_removal_clears_stale_filter_and_hidden_rows(self):
        self._configure()
        page = self._open_chat()
        self._ready(page)
        page.locator('.cth-pill', has_text='[BUG]').click()
        assert not page.is_visible('#item-c1')
        self._configure(rules=[CONTENT_RULES[0]])
        assert self._poll(page, "() => document.querySelectorAll('[data-cth-filtered]').length === 0")
        assert page.is_visible('#item-c1') and page.is_visible('#row-c4')
        self._configure(rules=[])
        assert self._poll(page, "() => document.querySelectorAll('[data-cth], [data-cth-hidden], [data-cth-filtered]').length === 0")
        assert page.is_visible('#item-c2') and self._overlay_hidden(page)

    def test_current_layout_mocked_delete_hides_complete_row(self):
        self._configure(showDeleteUntagged=True)
        page = self._open_chat(chats=[('a1', '[TODO] ship'), ('a2', 'plain chat'), ('a8', '[BUG] crash')])
        self._ready(page)
        calls, _ = self._mock_chat_api(page)
        page.click('#cth-delete-untagged')
        page.wait_for_selector('.cth-del-list li')
        assert not self._patches(calls)
        page.fill('.cth-del-input', 'delete')
        page.click('.cth-del-confirm-btn')
        assert self._poll(page, "() => /Deleted 3 of 3/.test(document.querySelector('.cth-del-status').textContent)", timeout=8000)
        assert not page.is_visible('#item-a2') and not page.is_visible('#row-a2 .menu')
        assert page.is_visible('#item-a1') and page.is_visible('#row-a8')
        assert [c['url'].rsplit('/', 1)[1] for c in self._patches(calls)] == ['a2', 'a7', 'a9']
        self._configure(showDeleteUntagged=True, dimUntagged=True)
        page.evaluate("""() => {
            const root=document.querySelector('[data-app-action-sidebar-scroll]');
            const clone=root.cloneNode(true);
            clone.querySelector('#row-a2 a').setAttribute('href','/c/surviving-chat');
            root.replaceWith(clone);
        }""")
        assert self._poll(page, "() => document.querySelector('#item-a2').getClientRects().length > 0"), \
            'a recycled link must not inherit another chat\'s deleted marker after a config change'

    # ---- Settings gear (#76) ----

    BAR_IDS = "() => [...(document.querySelector('#cth-filter-bar.cth-visible')?.children || [])].map(e => e.id || e.className)"

    def test_settings_gear_thresholds_and_label(self):
        self._configure(rules=[CONTENT_RULES[0]])
        page = self._open_chat()
        self._poll(page, "() => !!document.querySelector('#cth-filter-bar.cth-visible')")
        assert page.evaluate(self.BAR_IDS) == ['cth-settings']
        gear = page.locator('#cth-settings')
        assert gear.get_attribute('aria-label') == 'Tag Highlighter settings'
        assert gear.get_attribute('title') == 'Tag Highlighter settings'
        assert gear.text_content() == ''
        page.keyboard.press('Alt+f')
        assert page.evaluate('document.activeElement.id') == 'cth-settings'
        self._configure(showDeleteUntagged=True)
        assert self._poll(page, "() => !!document.querySelector('#cth-filter-bar.cth-visible .cth-pill')")
        ids = page.evaluate(self.BAR_IDS)
        assert ids[0].startswith('cth-pill'), ids
        assert ids[-2:] == ['cth-delete-untagged', 'cth-settings'], ids

    def test_settings_gear_opens_one_settings_page(self):
        self._configure()
        page = self._open_chat()
        self._ready(page)
        with self.context.expect_page() as info:
            page.click('#cth-settings')
        opened = info.value
        self._pages.append(opened)
        opened.wait_for_load_state()
        assert opened.url.endswith('/options.html'), opened.url
        page.click('#cth-settings')
        page.wait_for_timeout(800)
        options = [p for p in self.context.pages if p.url.endswith('/options.html')]
        assert len(options) == 1, [p.url for p in self.context.pages]

    # ---- Quick tag (#73) ----

    QT_ITEMS = """() => [...document.querySelectorAll('#cth-qt-menu .cth-qt-list [role=menuitemradio]')].map(n => [
        n.dataset.tag, n.getAttribute('aria-checked'), getComputedStyle(n.querySelector('.cth-qt-swatch')).backgroundColor])"""
    QT_FOCUS = "() => document.activeElement.dataset.tag || document.activeElement.dataset.action || document.activeElement.id"

    def _qt_page(self, chats=None, rules=None, fixture=None, **mock):
        self._configure(rules=rules)
        page = self._open_chat(**({'chats': chats} if chats is not None else {}), **(fixture or {}))
        self._ready(page)
        calls, held = self._mock_chat_api(page, **mock)
        return page, calls, held

    def _open_qt(self, page, cid):
        page.hover(f'#row-{cid}')
        page.click('#cth-qt-btn')
        page.wait_for_selector(f'#cth-qt-menu[data-cth-chat="{cid}"]')

    def _qt_shown(self, page, shown=True):
        """Poll briefly until the tag button's visibility equals `shown`."""
        want = 'true' if shown else 'false'
        return self._poll(page, f"() => {{ const b = document.getElementById('cth-qt-btn'); return (!!b && !b.hidden && b.getClientRects().length > 0) === {want}; }}",
                          timeout=1500)

    def test_quick_tag_button_only_on_valid_chat_rows(self):
        page, _, _ = self._qt_page(chats=DEFAULT_CHATS + [('bad id!', '[TODO] x')])
        page.hover('#row-c3')
        assert self._qt_shown(page)
        assert page.get_attribute('#cth-qt-btn', 'aria-label') == 'Tag chat'
        page.hover('[id="row-bad id!"]')
        assert self._qt_shown(page, False), 'chat ids outside [\\w-] never get a button'
        page.hover('#other-nav')
        assert self._qt_shown(page, False), 'non-row links never get a button'
        page.focus('#row-c2 a')
        assert self._qt_shown(page), 'keyboard focus on a row shows the button too'

    def test_quick_tag_menu_lists_prefix_rules_in_order(self):
        page, _, _ = self._qt_page()
        self._open_qt(page, 'c2')
        assert page.evaluate(self.QT_ITEMS) == [
            ['[TODO]', 'false', 'rgb(250, 189, 47)'],
            ['[BUG]', 'true', 'rgb(251, 73, 52)'],
            ['[ARCHIVE]', 'false', 'rgb(146, 131, 116)'],
        ]
        assert page.is_visible('#cth-qt-menu [data-action=remove]')
        assert page.is_visible('#cth-qt-menu [data-action=new]')
        page.keyboard.press('Escape')
        self._open_qt(page, 'c5')
        assert page.locator('#cth-qt-menu [data-action=remove]').count() == 0, 'untagged chats have nothing to remove'
        page.keyboard.press('Escape')
        self._configure(rules=[CONTENT_RULES[3]])
        assert self._poll(page, "() => !document.querySelector('#row-c1[data-cth]')")
        self._open_qt(page, 'c5')
        assert page.text_content('#cth-qt-menu .cth-qt-empty') == 'No prefix tags yet'

    def test_quick_tag_menu_keyboard(self):
        page, _, _ = self._qt_page()
        self._open_qt(page, 'c1')
        assert page.is_visible('#cth-qt-btn')
        assert page.get_attribute('#cth-qt-btn', 'aria-expanded') == 'true'
        assert page.evaluate(self.QT_FOCUS) == '[TODO]'
        seen = []
        for key in ('ArrowUp', 'ArrowDown', 'End', 'Home'):
            page.keyboard.press(key)
            seen.append(page.evaluate(self.QT_FOCUS))
        assert seen == ['new', '[TODO]', 'new', '[TODO]']
        page.keyboard.press('Escape')
        assert page.locator('#cth-qt-menu').count() == 0
        assert page.evaluate('document.activeElement.id') == 'cth-qt-btn'
        assert page.get_attribute('#cth-qt-btn', 'aria-expanded') == 'false'
        self._open_qt(page, 'c1')
        page.keyboard.press('Tab')
        assert page.locator('#cth-qt-menu').count() == 0

    def test_quick_tag_hides_for_native_row_menu(self):
        page, _, _ = self._qt_page()
        page.evaluate("""() => {
            const b = document.querySelector('#row-c3 .menu');
            b.addEventListener('click', () => setTimeout(() => b.setAttribute('aria-expanded', 'true'), 0));
        }""")
        page.hover('#row-c3')
        assert self._qt_shown(page)
        page.click('#row-c3 .menu')
        page.wait_for_timeout(700)
        page.hover('#row-c3')
        assert self._qt_shown(page, False), 'stay out of the way while the native row menu is open'
        page.evaluate("document.querySelector('#row-c3 .menu').setAttribute('aria-expanded', 'false')")
        page.hover('#row-c2')
        page.hover('#row-c3')
        assert self._qt_shown(page)
        page.focus('#row-c2 .menu')
        page.keyboard.press('Enter')
        assert self._qt_shown(page, False), 'opening a native menu from the keyboard hides the button'

    def test_alt_t_focused_row_vs_active_chat(self):
        page, _, _ = self._qt_page()
        page.focus('#row-c3 a')
        page.keyboard.press('Alt+t')
        page.wait_for_selector('#cth-qt-menu')
        assert page.get_attribute('#cth-qt-menu', 'data-cth-chat') == 'c3'
        page.keyboard.press('Escape')
        page.evaluate('document.activeElement.blur()')
        page.keyboard.press('Alt+t')
        page.wait_for_selector('#cth-qt-menu')
        assert page.get_attribute('#cth-qt-menu', 'data-cth-chat') == 'c1'

    def test_quick_tag_default_on_and_option_off(self):
        page, _, _ = self._qt_page()
        page.hover('#row-c3')
        assert self._qt_shown(page)
        self._configure(showQuickTag=False)
        assert self._qt_shown(page, False)
        page.wait_for_timeout(300)
        page.hover('#row-c2')
        page.hover('#row-c3')
        page.wait_for_timeout(200)
        assert page.locator('#cth-qt-btn:not([hidden])').count() == 0
        page.focus('#row-c3 a')
        page.keyboard.press('Alt+t')
        page.wait_for_timeout(300)
        assert page.locator('#cth-qt-menu').count() == 0

    # ---- Renaming from the quick tag menu (#73) ----

    def _pick(self, page, cid, tag):
        self._open_qt(page, cid)
        page.click(f'#cth-qt-menu [data-tag="{tag}"]')

    def _title_is(self, page, cid, title, timeout=3000):
        return self._poll(page, f'([t]) => {_tjs(cid)} === t', arg=[title], timeout=timeout)

    def _alert(self, page, text):
        assert self._poll(page, """([t]) => {
            const n = document.querySelector('#cth-qt-toast[role=alert]');
            return !!n && n.textContent.includes(t);
        }""", arg=[text], timeout=5000), page.evaluate("document.getElementById('cth-qt-toast')?.textContent")

    @staticmethod
    def _wait_held(page, held):
        deadline = time.time() + 5
        while not held and time.time() < deadline:
            page.wait_for_timeout(50)
        assert held, 'held request never arrived'

    def test_pick_tag_patches_exact_chat_with_bearer(self):
        page, calls, _ = self._qt_page()
        self._pick(page, 'c5', '[BUG]')
        assert self._title_is(page, 'c5', '[BUG] plain chat')
        patches = self._patches(calls)
        assert len(patches) == 1
        assert patches[0]['url'].endswith('/backend-api/conversation/c5')
        assert patches[0]['auth'] == 'Bearer test-token'
        assert json.loads(patches[0]['body']) == {'title': '[BUG] plain chat'}
        assert self._poll(page, "() => getComputedStyle(document.querySelector('#row-c5')).backgroundColor === 'rgba(251, 73, 52, 0.12)'")

    def test_pick_replaces_longest_prefix_and_spaces(self):
        rules = [_rule('[A]'), _rule('[A][B]', '#fb4934'), _rule('[C]', '#83a598')]
        page, calls, _ = self._qt_page(chats=[('c2', '[A][B]   two'), ('c3', '[C] three')], rules=rules)
        self._pick(page, 'c2', '[C]')
        assert self._title_is(page, 'c2', '[C] two')
        self._open_qt(page, 'c3')
        page.click('#cth-qt-menu [data-action=remove]')
        assert self._title_is(page, 'c3', 'three')
        self._pick(page, 'c2', '[C]')
        page.wait_for_timeout(300)
        assert len(self._patches(calls)) == 2, 'picking the current tag changes nothing'

    def test_rename_keeps_title_text_node(self):
        page, _, _ = self._qt_page()
        page.evaluate("window.__node = document.querySelector('#row-c5 [data-thread-title] span[dir=auto]').firstChild")
        self._pick(page, 'c5', '[BUG]')
        assert self._title_is(page, 'c5', '[BUG] plain chat')
        assert page.evaluate("""() => {
            const s = document.querySelector('#row-c5 [data-thread-title] span[dir=auto]');
            return s.firstChild === window.__node && s.childNodes.length === 1;
        }""")

    @pytest.mark.parametrize('mock, message', [
        ({'patch_abort': True}, "Couldn't reach ChatGPT. Nothing changed."),
        ({'patch_status': 401}, 'Sign in to ChatGPT first. Nothing changed.'),
        ({'patch_status': 403}, 'Sign in to ChatGPT first. Nothing changed.'),
        ({'patch_status': 429}, 'ChatGPT is rate-limiting requests (HTTP 429). Wait a minute and try again.'),
        ({'patch_status': 500}, 'ChatGPT refused the rename (HTTP 500). Nothing changed.'),
        ({'patch_body': {'success': False}}, "ChatGPT said the rename didn't go through. Nothing changed."),
    ], ids=['abort', '401', '403', '429', '500', 'success-false'])
    def test_rename_errors_change_nothing(self, mock, message):
        page, _, _ = self._qt_page(**mock)
        self._pick(page, 'c5', '[BUG]')
        self._alert(page, message)
        assert page.evaluate(_tjs('c5')) == 'plain chat'
        assert page.get_attribute('#row-c5', 'data-cth') is None

    def test_override_survives_remount_and_yields_to_third_title(self):
        page, _, _ = self._qt_page()
        span = "document.querySelector('#row-c5 [data-thread-title] span[dir=auto]')"
        self._pick(page, 'c5', '[BUG]')
        assert self._title_is(page, 'c5', '[BUG] plain chat')
        page.evaluate(f"{span}.textContent = 'plain chat'")  # a stale remount
        assert self._title_is(page, 'c5', '[BUG] plain chat'), 'the confirmed title wins over a stale copy'
        page.evaluate(f"""() => {{
            window.__cd = 0;
            new MutationObserver(ms => {{ window.__cd += ms.filter(m => m.type === 'characterData').length; }})
                .observe({span}, {{characterData: true, subtree: true, childList: true}});
            {span}.textContent = '[BUG] plain chat';
        }}""")
        page.wait_for_timeout(300)
        assert page.evaluate('window.__cd') == 0, 'the new title needs no rewrite'
        page.evaluate(f"{span}.textContent = 'renamed elsewhere'")
        assert self._poll(page, "() => !document.querySelector('#row-c5').hasAttribute('data-cth')")
        page.evaluate(f"{span}.textContent = 'plain chat'")
        page.wait_for_timeout(300)
        assert page.evaluate(_tjs('c5')) == 'plain chat', 'a third title ends the override'

    def test_title_changed_before_pick_aborts(self):
        page, calls, _ = self._qt_page()
        self._open_qt(page, 'c5')
        page.evaluate("document.querySelector('#row-c5 [data-thread-title] span[dir=auto]').textContent = 'other'")
        page.click('#cth-qt-menu [data-tag="[BUG]"]')
        self._alert(page, 'Title changed — try again')
        assert self._patches(calls) == []

    def test_recycled_anchor_other_id_aborts(self):
        page, calls, _ = self._qt_page()
        self._open_qt(page, 'c5')
        page.evaluate("document.querySelector('#row-c5 a').setAttribute('href', '/c/c9')")
        page.click('#cth-qt-menu [data-tag="[BUG]"]')
        self._alert(page, 'Title changed — try again')
        assert self._patches(calls) == []

    def test_title_change_while_token_pending_aborts(self):
        page, calls, held = self._qt_page(hold_session=True)
        self._pick(page, 'c5', '[BUG]')
        self._wait_held(page, held)
        page.evaluate("document.querySelector('#row-c5 [data-thread-title] span[dir=auto]').textContent = 'other'")
        held[0].fulfill(status=200, content_type='application/json', body=TOKEN)
        self._alert(page, 'Title changed — try again')
        assert self._patches(calls) == []
        assert page.evaluate(_tjs('c5')) == 'other'

    @pytest.mark.parametrize('change', ['title', 'href'])
    def test_post_request_change_aborts_dom_write(self, change):
        page, calls, held = self._qt_page(hold_first_patch=True)
        self._pick(page, 'c5', '[BUG]')
        self._wait_held(page, held)
        if change == 'title':
            page.evaluate("document.querySelector('#row-c5 [data-thread-title] span[dir=auto]').textContent = 'other'")
        else:
            page.evaluate("document.querySelector('#row-c5 a').setAttribute('href', '/c/c9')")
        held[0].fulfill(status=200, content_type='application/json', body=OK)
        self._alert(page, 'Title changed — try again')
        assert page.evaluate(_tjs('c5')) == ('other' if change == 'title' else 'plain chat')
        assert page.get_attribute('#row-c5', 'data-cth') is None
        if change == 'title':
            page.evaluate("document.querySelector('#row-c5 [data-thread-title] span[dir=auto]').textContent = 'plain chat'")
            page.wait_for_timeout(300)
            assert page.evaluate(_tjs('c5')) == 'plain chat', 'an aborted write leaves no override behind'

    def test_overlapping_rename_same_chat_refused(self):
        page, calls, held = self._qt_page(hold_first_patch=True)
        self._pick(page, 'c5', '[BUG]')
        self._wait_held(page, held)
        page.mouse.click(640, 400)
        self._pick(page, 'c5', '[TODO]')
        self._alert(page, 'Still saving this chat — try again')
        assert len(self._patches(calls)) == 1
        held[0].fulfill(status=200, content_type='application/json', body=OK)
        assert self._title_is(page, 'c5', '[BUG] plain chat')

    def test_toast_above_overlay_auto_hides_and_pauses(self):
        page, _, _ = self._qt_page()
        assert self._overlay_visible(page)
        self._pick(page, 'c5', '[BUG]')
        page.wait_for_selector('#cth-qt-toast[role=status]')
        gap = page.evaluate("""() => document.querySelector('#cth-overlay').getBoundingClientRect().top - 12
            - document.querySelector('#cth-qt-toast').getBoundingClientRect().bottom""")
        assert gap >= -0.5, gap
        page.hover('#cth-qt-toast')
        page.wait_for_timeout(7000)
        assert page.is_visible('#cth-qt-toast'), 'hovering pauses the auto-hide'
        page.mouse.move(640, 5)
        page.wait_for_timeout(6500)
        assert page.locator('#cth-qt-toast').count() == 0

    # ---- New tag from the quick tag menu (#73) ----

    def _stored_rules(self):
        page = self.context.new_page()
        try:
            page.goto(f'chrome-extension://{self.ext_id}/options.html')
            return page.evaluate("k => new Promise(r => chrome.storage.sync.get(k, d => r(d[k].rules)))", STORAGE_KEY)
        finally:
            page.close()

    def _new_tag(self, page, cid, text):
        self._open_qt(page, cid)
        page.click('#cth-qt-menu [data-action=new]')
        page.fill('#cth-qt-menu input', text)
        page.keyboard.press('Enter')

    def test_new_tag_trims_creates_rule_and_renames(self):
        page, _, _ = self._qt_page()
        self._open_qt(page, 'c5')
        page.click('#cth-qt-menu [data-action=new]')
        page.wait_for_selector('#cth-qt-menu input')
        assert page.get_attribute('#cth-qt-menu input', 'placeholder') == '[TAG]'
        # A menu may only own items, separators or groups: the textbox sits in a labelled group.
        assert page.evaluate("() => { const g = document.querySelector('#cth-qt-menu input').parentElement; return [g.getAttribute('role'), g.getAttribute('aria-label'), g.parentElement.id]; }") == ['group', 'New tag', 'cth-qt-menu']
        page.keyboard.press('Escape')
        assert page.locator('#cth-qt-menu [data-action=new]').count() == 1
        assert page.locator('#cth-qt-menu input').count() == 0
        page.click('#cth-qt-menu [data-action=new]')
        page.wait_for_selector('#cth-qt-menu input')
        page.keyboard.press('Tab')
        assert page.locator('#cth-qt-menu').count() == 0
        self._new_tag(page, 'c5', '  [NEW]  ')
        assert self._title_is(page, 'c5', '[NEW] plain chat')
        assert self._stored_rules()[-1] == _rule('[NEW]', '#b8bb26')

    @pytest.mark.parametrize('text', ['', 'x' * 41, 'x' * 40], ids=['empty', '41', '40'])
    def test_new_tag_length_bounds(self, text):
        page, calls, _ = self._qt_page()
        self._new_tag(page, 'c5', text)
        if len(text) == 40:
            assert self._title_is(page, 'c5', 'x' * 40 + ' plain chat')
            assert len(self._stored_rules()) == len(CONTENT_RULES) + 1
        else:
            self._alert(page, 'Tags are 1–40 characters.')
            page.wait_for_timeout(300)
            assert self._patches(calls) == []
            assert len(self._stored_rules()) == len(CONTENT_RULES)

    @pytest.mark.parametrize('tag, title', [('[BUG]', '[BUG] plain chat'), ('code', 'code plain chat')])
    def test_new_tag_reuses_existing(self, tag, title):
        page, _, _ = self._qt_page()
        self._new_tag(page, 'c5', tag)
        assert self._title_is(page, 'c5', title)
        assert len(self._stored_rules()) == len(CONTENT_RULES)

    def test_new_tag_rename_failure_keeps_rule(self):
        page, _, _ = self._qt_page(patch_status=500)
        self._new_tag(page, 'c5', '[NEW]')
        self._alert(page, 'ChatGPT refused the rename (HTTP 500). Nothing changed.')
        assert page.evaluate(_tjs('c5')) == 'plain chat'
        assert self._stored_rules()[-1]['tag'] == '[NEW]'

    def test_new_tag_keeps_original_chat_across_await(self):
        page, calls, held = self._qt_page(hold_first_patch=True)
        self._new_tag(page, 'c1', '[NEW]')
        self._wait_held(page, held)
        page.mouse.click(640, 400)
        self._open_qt(page, 'c2')
        held[0].fulfill(status=200, content_type='application/json', body=OK)
        assert self._title_is(page, 'c1', '[NEW] ship release')
        patches = self._patches(calls)
        assert len(patches) == 1 and patches[0]['url'].endswith('/c1')
        assert page.locator('#cth-qt-menu[data-cth-chat="c2"]').count() == 1, 'a later menu stays open'
        assert page.evaluate(_tjs('c2')) == '[BUG] code crash'

    # ---- Undo (#73) ----

    def test_undo_restores_title(self):
        page, calls, _ = self._qt_page()
        self._pick(page, 'c5', '[BUG]')
        page.wait_for_selector('#cth-qt-toast[role=status]')
        assert page.evaluate("[...document.getElementById('cth-qt-toast').children].map(c => c.textContent)") == ['Tagged', '·', 'Undo']
        page.click('#cth-qt-toast .cth-qt-undo')
        assert self._title_is(page, 'c5', 'plain chat')
        patches = self._patches(calls)
        assert [json.loads(c['body'])['title'] for c in patches] == ['[BUG] plain chat', 'plain chat']
        assert patches[1]['url'].endswith('/backend-api/conversation/c5'), 'Undo renames the same chat'
        assert patches[1]['auth'] == 'Bearer test-token'
        chat_calls = [c for c in calls if '/backend-api/conversation/' in c['url']]
        assert [(c['method'], c['url'].rsplit('/', 1)[1], c['auth']) for c in chat_calls] == [
            ('PATCH', 'c5', 'Bearer test-token'), ('GET', 'c5', 'Bearer test-token'), ('PATCH', 'c5', 'Bearer test-token')], \
            'Undo reads the server title right before its PATCH'

    def test_undo_failure_keeps_tag(self):
        page, _, _ = self._qt_page(patch_statuses=[200, 500])
        self._pick(page, 'c5', '[BUG]')
        page.click('#cth-qt-toast .cth-qt-undo')
        self._alert(page, 'ChatGPT refused the rename (HTTP 500). Nothing changed.')
        assert page.evaluate(_tjs('c5')) == '[BUG] plain chat'

    def test_undo_refused_after_intervening_rename(self):
        page, calls, _ = self._qt_page()
        self._pick(page, 'c5', '[BUG]')
        page.wait_for_selector('#cth-qt-toast .cth-qt-undo')
        page.evaluate("document.querySelector('#row-c5 [data-thread-title] span[dir=auto]').textContent = 'renamed elsewhere'")
        page.click('#cth-qt-toast .cth-qt-undo')
        self._alert(page, 'Title changed — not undone')
        assert len(self._patches(calls)) == 1

    # ---- QA fixes: scrolling, undo history, Option+T ----

    def test_quick_tag_follows_sidebar_scroll_and_resize(self):
        chats = DEFAULT_CHATS + [(f'n{i}', f'note {i}') for i in range(20)]
        page, calls, _ = self._qt_page(chats=chats, fixture={'sidebar_height': 300})
        self._open_qt(page, 'c5')
        box = page.locator('#cth-qt-btn').bounding_box()
        x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
        page.evaluate("document.querySelector('[data-app-action-sidebar-scroll]').scrollTop = 150")
        assert self._poll(page, "() => !document.getElementById('cth-qt-menu')"), 'a sidebar scroll closes the menu'
        assert self._qt_shown(page, False), 'and hides the button, which no longer sits on its row'
        page.keyboard.press('Escape')
        assert self._qt_shown(page, False)
        # Whatever row sits under the old spot now must be the one that gets tagged.
        page.mouse.move(x - 120, y)
        cid = page.evaluate("([x, y]) => document.elementFromPoint(x, y).closest('[role=group]').id.slice(4)", [x - 120, y])
        assert cid != 'c5'
        page.click('#cth-qt-btn')
        page.wait_for_selector(f'#cth-qt-menu[data-cth-chat="{cid}"]')
        page.click('#cth-qt-menu [data-tag="[BUG]"]')
        assert self._poll(page, '() => !!document.querySelector("#cth-qt-toast")', timeout=5000)
        assert [c['url'].rsplit('/', 1)[1] for c in self._patches(calls)] == [cid]
        page.hover(f'#row-{cid}')
        page.click('#cth-qt-btn')
        page.wait_for_selector('#cth-qt-menu')
        page.set_viewport_size({'width': 1200, 'height': 860})
        assert self._poll(page, "() => !document.getElementById('cth-qt-menu')"), 'a resize closes the menu'
        assert self._qt_shown(page, False)

    def test_closing_menu_without_refocus_clears_button(self):
        page, _, _ = self._qt_page()
        self._open_qt(page, 'c5')
        page.evaluate("document.getElementById('cth-qt-menu').dispatchEvent(new KeyboardEvent('keydown', {key: 'Tab', bubbles: true}))")
        assert page.locator('#cth-qt-menu').count() == 0
        assert self._qt_shown(page, False), 'closing the menu must not leave a button bound to an old row'

    def test_consecutive_tags_keep_undo_history(self):
        page, calls, _ = self._qt_page()
        span = "document.querySelector('#row-c5 [data-thread-title] span[dir=auto]')"
        self._pick(page, 'c5', '[BUG]')
        assert self._title_is(page, 'c5', '[BUG] plain chat')
        page.mouse.move(640, 5)
        self._pick(page, 'c5', '[TODO]')
        assert self._title_is(page, 'c5', '[TODO] plain chat')
        page.evaluate(f"{span}.textContent = 'plain chat'")  # remount of the ORIGINAL title
        assert self._title_is(page, 'c5', '[TODO] plain chat'), 'any title we replaced is a stale remount'
        page.click('#cth-qt-toast .cth-qt-undo')
        assert self._title_is(page, 'c5', '[BUG] plain chat')
        assert [json.loads(c['body'])['title'] for c in self._patches(calls)] == [
            '[BUG] plain chat', '[TODO] plain chat', '[BUG] plain chat']

    def test_hidden_tag_survives_original_title_remount(self):
        page, calls, _ = self._qt_page()
        span = "document.querySelector('#row-c5 [data-thread-title] span[dir=auto]')"
        self._pick(page, 'c5', '[BUG]')
        assert self._title_is(page, 'c5', '[BUG] plain chat')
        page.mouse.move(640, 5)
        self._pick(page, 'c5', '[ARCHIVE]')
        assert self._title_is(page, 'c5', '[ARCHIVE] plain chat')
        assert self._poll(page, "() => !document.querySelector('#row-c5').getClientRects().length")
        page.evaluate(f"{span}.textContent = 'plain chat'")
        page.wait_for_timeout(300)
        assert page.evaluate(_tjs('c5')) == '[ARCHIVE] plain chat'
        assert not page.is_visible('#row-c5'), 'a stale remount must not unhide the chat'
        page.click('#cth-qt-toast .cth-qt-undo')
        assert self._title_is(page, 'c5', '[BUG] plain chat')
        assert json.loads(self._patches(calls)[-1]['body'])['title'] == '[BUG] plain chat'
        page.evaluate(f"{span}.textContent = 'plain chat'")
        assert self._title_is(page, 'c5', '[BUG] plain chat'), 'the undone title still wins over the original'

    OPTION_T = """() => {
        const ed = document.getElementById('editor');
        ed.focus();
        const e = new KeyboardEvent('keydown', {key: '†', code: 'KeyT', altKey: true, bubbles: true, cancelable: true});
        ed.dispatchEvent(e);
        return e.defaultPrevented;
    }"""

    def test_option_t_types_in_composer(self):
        self._configure(showQuickTag=False)
        page = self._open_chat()
        self._ready(page)
        assert page.evaluate(self.OPTION_T) is False, 'feature off: Option+T is left alone'
        self._configure()
        assert self._poll(page, "() => document.getElementById('cth-settings') && true")
        page.wait_for_timeout(300)
        assert page.evaluate(self.OPTION_T) is False, 'editable fields keep Option+T'
        assert page.locator('#cth-qt-menu').count() == 0
        page.focus('#row-c3 a')
        page.keyboard.press('Alt+t')
        page.wait_for_selector('#cth-qt-menu[data-cth-chat="c3"]')

    # ---- Tests-as-spec additions ----

    SPAN5 = "document.querySelector('#row-c5 [data-thread-title] span[dir=auto]')"

    def _stale_clone_row(self, page, cid, title):
        """Replace the whole row with a clone showing `title`, like a React remount."""
        page.evaluate("""([cid, title]) => {
            const row = document.getElementById('row-' + cid);
            const copy = row.cloneNode(true);
            copy.querySelector('[data-thread-title] span[dir=auto]').textContent = title;
            row.replaceWith(copy);
        }""", [cid, title])

    def test_undo_with_held_session_rechecks_title(self):
        page, calls, held = self._qt_page(hold_session_at=2)
        self._pick(page, 'c5', '[BUG]')
        page.click('#cth-qt-toast .cth-qt-undo')
        self._wait_held(page, held)
        page.evaluate(f"{self.SPAN5}.textContent = 'other'")
        held[0].fulfill(status=200, content_type='application/json', body=TOKEN)
        self._alert(page, 'Title changed — not undone')
        assert len(self._patches(calls)) == 1, 'no Undo PATCH once the title changed'
        assert page.evaluate(_tjs('c5')) == 'other'

    def test_undo_with_held_patch_skips_dom_write(self):
        page, calls, held = self._qt_page(hold_patch_at=2)
        self._pick(page, 'c5', '[BUG]')
        page.click('#cth-qt-toast .cth-qt-undo')
        self._wait_held(page, held)
        page.evaluate(f"{self.SPAN5}.textContent = 'other'")
        held[0].fulfill(status=200, content_type='application/json', body=OK)
        self._alert(page, 'Title changed — not undone')
        assert page.evaluate(_tjs('c5')) == 'other', 'a title changed meanwhile is never overwritten'

    def test_undo_while_same_chat_rename_pending_is_refused(self):
        page, calls, held = self._qt_page(hold_patch_at=2)
        self._pick(page, 'c5', '[BUG]')
        page.wait_for_selector('#cth-qt-toast .cth-qt-undo')
        page.mouse.move(640, 5)
        self._pick(page, 'c5', '[TODO]')
        self._wait_held(page, held)
        page.click('#cth-qt-toast .cth-qt-undo')
        self._alert(page, 'Still saving this chat — try again')
        assert len(self._patches(calls)) == 2
        held[0].fulfill(status=200, content_type='application/json', body=OK)
        assert self._title_is(page, 'c5', '[TODO] plain chat')

    def test_pending_rename_does_not_block_other_chats(self):
        page, calls, held = self._qt_page(hold_first_patch=True)
        self._pick(page, 'c5', '[BUG]')
        self._wait_held(page, held)
        page.mouse.click(640, 400)
        self._pick(page, 'c3', '[TODO]')
        assert self._title_is(page, 'c3', '[TODO] refactor code path')
        held[0].fulfill(status=200, content_type='application/json', body=OK)
        assert self._title_is(page, 'c5', '[BUG] plain chat')

    def test_override_survives_stale_row_clone(self):
        page, _, _ = self._qt_page()
        self._pick(page, 'c5', '[BUG]')
        assert self._title_is(page, 'c5', '[BUG] plain chat')
        self._stale_clone_row(page, 'c5', 'plain chat')
        assert self._title_is(page, 'c5', '[BUG] plain chat'), 'overrides are keyed by chat id, not by element'

    def test_failed_rename_leaves_nothing_after_remount(self):
        page, _, _ = self._qt_page(patch_status=500)
        self._pick(page, 'c5', '[BUG]')
        self._alert(page, 'ChatGPT refused the rename (HTTP 500). Nothing changed.')
        self._stale_clone_row(page, 'c5', 'plain chat')
        page.wait_for_timeout(300)
        assert page.evaluate(_tjs('c5')) == 'plain chat'
        assert page.get_attribute('#row-c5', 'data-cth') is None

    QUOTA_RULES = CONTENT_RULES + [_rule('zzzz' + 'y' * 7620, '#ffffff', 'includes', hide=True)]

    @pytest.mark.parametrize('case', ['session-abort', 'no-token', 'add-rule-fails'])
    def test_setup_failures_show_error_and_patch_nothing(self, case):
        if case == 'add-rule-fails':
            # Close to storage.sync's 8 KB per-item quota, so adding one rule is refused.
            page, calls, _ = self._qt_page(rules=self.QUOTA_RULES)
            opts = self.context.new_page()
            opts.goto(f'chrome-extension://{self.ext_id}/options.html')
            used = opts.evaluate("k => new Promise(r => chrome.storage.sync.getBytesInUse(k, r))", STORAGE_KEY)
            opts.close()
            assert 8100 < used < 8192, used
            self._new_tag(page, 'c5', '[' + 'Q' * 38 + ']')
            assert self._poll(page, "() => !!document.querySelector('#cth-qt-toast[role=alert]')", timeout=5000)
            assert len(self._stored_rules()) == len(self.QUOTA_RULES)
        else:
            mock = {'session_abort': True} if case == 'session-abort' else {'session_token': None}
            page, calls, _ = self._qt_page(**mock)
            self._pick(page, 'c5', '[BUG]')
            self._alert(page, "Couldn't reach ChatGPT. Nothing changed." if case == 'session-abort'
                        else 'Sign in to ChatGPT first. Nothing changed.')
        page.wait_for_timeout(200)
        assert self._patches(calls) == []
        assert page.evaluate(_tjs('c5')) == 'plain chat'

    @pytest.mark.parametrize('key', ['Enter', ' '], ids=['enter', 'space'])
    def test_keyboard_activates_menu_item(self, key):
        page, calls, _ = self._qt_page()
        self._open_qt(page, 'c5')
        page.keyboard.press('ArrowDown')
        assert page.evaluate(self.QT_FOCUS) == '[BUG]'
        page.keyboard.press(key)
        assert self._title_is(page, 'c5', '[BUG] plain chat')
        assert [json.loads(c['body']) for c in self._patches(calls)] == [{'title': '[BUG] plain chat'}]

    def test_new_tag_one_character(self):
        page, _, _ = self._qt_page()
        self._new_tag(page, 'c5', 'x')
        assert self._title_is(page, 'c5', 'x plain chat')
        assert self._stored_rules()[-1]['tag'] == 'x'

    def test_toast_auto_hides_after_six_seconds(self):
        page, _, _ = self._qt_page()
        self._pick(page, 'c5', '[BUG]')
        page.wait_for_selector('#cth-qt-toast[role=status]')
        page.mouse.move(130, 5)
        page.wait_for_timeout(5500)
        assert page.locator('#cth-qt-toast').count() == 1, 'still there at 5.5 s'
        page.wait_for_timeout(1000)
        assert page.locator('#cth-qt-toast').count() == 0, 'gone by 6.5 s'

    def test_toast_stays_while_focus_is_inside(self):
        page, _, _ = self._qt_page()
        self._pick(page, 'c5', '[BUG]')
        page.wait_for_selector('#cth-qt-toast .cth-qt-undo')
        page.hover('#cth-qt-toast')
        page.focus('#cth-qt-toast .cth-qt-undo')
        page.mouse.move(640, 5)
        page.wait_for_timeout(7000)
        assert page.locator('#cth-qt-toast').count() == 1, 'keyboard focus keeps the toast open'

    def test_bar_with_only_hidden_rules_shows_gear_only(self):
        self._configure(rules=[dict(r, hide=True) for r in CONTENT_RULES])
        page = self._open_chat()
        self._ready(page)
        assert page.evaluate(self.BAR_IDS) == ['cth-settings']

    def test_bar_with_two_visible_rules_shows_pills(self):
        self._configure(rules=CONTENT_RULES[:2])
        page = self._open_chat()
        self._ready(page)
        assert page.evaluate("[...document.querySelectorAll('#cth-filter-bar .cth-pill')].map(p => p.textContent)") == ['All', '[TODO]', '[BUG]']
        assert page.evaluate(self.BAR_IDS)[-1] == 'cth-settings'

    def test_settings_gear_has_icon(self):
        self._configure()
        page = self._open_chat()
        self._ready(page)
        assert page.locator('#cth-settings svg').count() == 1
        icon = page.evaluate("""() => [...document.querySelectorAll('#cth-settings svg, #cth-settings svg *')]
            .map(n => [n.namespaceURI, n.localName, n.getAttribute('viewBox') || n.getAttribute('d') || n.getAttribute('r')])""")
        svg_ns = 'http://www.w3.org/2000/svg'
        assert icon == [[svg_ns, 'svg', '0 0 24 24'], [svg_ns, 'circle', '3'],
                        [svg_ns, 'path', 'M10.3 2h3.4l.5 2.6 1.9.8 2.2-1.5 2.4 2.4-1.5 2.2.8 1.9 2.6.5v3.4l-2.6.5-.8 1.9 1.5 2.2-2.4 2.4-2.2-1.5-1.9.8-.5 2.6h-3.4l-.5-2.6-1.9-.8-2.2 1.5-2.4-2.4 1.5-2.2-.8-1.9L2 13.7v-3.4l2.6-.5.8-1.9-1.5-2.2 2.4-2.4 2.2 1.5 1.9-.8z']], icon
        assert page.eval_on_selector('#cth-settings svg', 'e => e.getBoundingClientRect().width') == 14
        page.hover('#row-c3')
        assert page.eval_on_selector('#cth-qt-btn svg', "e => [e.namespaceURI, e.children.length, e.getBoundingClientRect().width]") == [svg_ns, 2, 14]

    # ---- Designer screenshots (T12; skipped unless CTH_SCREENSHOTS names an output dir) ----

    # The fixture page is unstyled (white body, blue links) and our row tints are translucent,
    # so give each theme a ChatGPT-like page behind our UI.
    THEME_FIXTURE_CSS = {
        'dark': 'body{background:#181818;color:#ececec} a{color:inherit;text-decoration:none} [role=group]{background:#181818} #composer{background:#303030}',
        'light': 'body{background:#fff;color:#0d0d0d} a{color:inherit;text-decoration:none} [role=group]{background:#f9f9f9} #composer{background:#f4f4f4}',
    }

    @staticmethod
    def _clip(page, selectors, pad=12):
        """A viewport clip covering every selector's box, padded and clamped."""
        return page.evaluate("""([sels, pad]) => {
            const rs = sels.map(s => document.querySelector(s).getBoundingClientRect());
            const x = Math.max(0, Math.min(...rs.map(r => r.left)) - pad), y = Math.max(0, Math.min(...rs.map(r => r.top)) - pad);
            const right = Math.min(innerWidth, Math.max(...rs.map(r => r.right)) + pad);
            const bottom = Math.min(innerHeight, Math.max(...rs.map(r => r.bottom)) + pad);
            return {x, y, width: right - x, height: bottom - y};
        }""", [selectors, pad])

    @pytest.mark.skipif(not os.environ.get('CTH_SCREENSHOTS'), reason='designer capture only')
    def test_capture_ui_screenshots(self):
        out = Path(os.environ['CTH_SCREENSHOTS'])
        out.mkdir(parents=True, exist_ok=True)
        for theme in ('dark', 'light'):
            page, _, _ = self._qt_page()
            page.set_viewport_size({'width': 1100, 'height': 760})
            page.evaluate("([theme, css]) => { document.documentElement.classList.replace('dark', theme); "
                          "document.head.append(Object.assign(document.createElement('style'), {textContent: css})); }",
                          [theme, self.THEME_FIXTURE_CSS[theme]])
            assert self._poll(page, f"() => document.documentElement.classList.contains('cth-light') === {str(theme == 'light').lower()}")
            page.locator('#cth-filter-bar').screenshot(path=str(out / f'gear-{theme}.png'))
            page.hover('#row-c3')
            assert self._qt_shown(page)
            page.screenshot(path=str(out / f'button-{theme}.png'), clip=self._clip(page, ['#row-c3', '#cth-qt-btn']))
            self._open_qt(page, 'c2')
            page.screenshot(path=str(out / f'menu-{theme}.png'), clip=self._clip(page, ['#cth-qt-menu', '#cth-qt-btn']))
            page.keyboard.press('Escape')
            self._pick(page, 'c5', '[TODO]')
            page.wait_for_selector('#cth-qt-toast[role=status]')
            page.mouse.move(1, 1)  # no hover styling in the shot
            page.screenshot(path=str(out / f'toast-{theme}.png'), clip=self._clip(page, ['#cth-qt-toast'], pad=24))
        opts = self.context.new_page()
        self._pages.append(opts)
        opts.goto(f'chrome-extension://{self.ext_id}/options.html')
        opts.wait_for_selector('#rows tr')
        for width in (400, 900):
            opts.set_viewport_size({'width': width, 'height': 900})
            opts.wait_for_timeout(150)
            opts.screenshot(path=str(out / f'options-{width}.png'), full_page=True)

    # ---- Tech lead review: rows moving under the button, cross-tab Undo ----

    def test_quick_tag_click_checks_its_row_is_still_under_it(self):
        page, calls, _ = self._qt_page()
        page.mouse.move(640, 5)  # keep the pointer out of the sidebar: no synthetic re-hover
        page.focus('#row-c5 a')
        assert self._qt_shown(page)
        # Layout moves the rows without touching the sidebar's DOM, scrolling or resizing.
        page.evaluate("document.querySelector('#app-shell-sidebar nav').style.paddingTop = '120px'")
        page.focus('#cth-qt-btn')
        page.keyboard.press('Enter')
        page.wait_for_timeout(200)
        assert page.locator('#cth-qt-menu').count() == 0, 'the button no longer sits on its row'
        assert self._qt_shown(page, False)
        assert self._patches(calls) == []

    def test_quick_tag_button_follows_rows_reordered_in_the_dom(self):
        page, calls, _ = self._qt_page()
        page.hover('#row-c5')
        assert self._qt_shown(page)
        box = page.locator('#cth-qt-btn').bounding_box()
        x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
        page.mouse.move(x, y)  # the pointer rests on the button itself
        page.evaluate("() => { const c3 = document.getElementById('row-c3'); c3.before(document.getElementById('row-c5')); }")
        assert page.evaluate("([x, y]) => document.elementsFromPoint(x, y).some(e => e.id === 'row-c3')", [x, y]), 'c3 now sits there'
        page.wait_for_timeout(100)
        page.mouse.click(x, y)
        page.wait_for_timeout(200)
        assert page.locator('#cth-qt-menu[data-cth-chat="c5"]').count() == 0, 'never bind the row that moved away'
        if page.locator('#cth-qt-menu').count():
            assert page.get_attribute('#cth-qt-menu', 'data-cth-chat') == 'c3'
            page.click('#cth-qt-menu [data-tag="[BUG]"]')
            assert self._title_is(page, 'c3', '[BUG] refactor code path')
        assert all(not c['url'].endswith('/c5') for c in self._patches(calls))

    def test_undo_refuses_when_server_title_is_unknown(self):
        page, calls, _ = self._qt_page(get_status=500)
        self._pick(page, 'c5', '[BUG]')
        page.click('#cth-qt-toast .cth-qt-undo')
        self._alert(page, "Couldn't check the chat. Nothing changed.")
        assert len(self._patches(calls)) == 1
        assert page.evaluate(_tjs('c5')) == '[BUG] plain chat'

    def test_cross_tab_undo_refuses_newer_rename(self):
        titles = {}  # one server, two tabs
        self._configure()
        tab_a = self._open_chat()
        self._ready(tab_a)
        calls_a, _ = self._mock_chat_api(tab_a, titles=titles)
        tab_b = self._open_chat()
        self._ready(tab_b)
        calls_b, _ = self._mock_chat_api(tab_b, titles=titles)
        tab_a.bring_to_front()
        self._pick(tab_a, 'c5', '[BUG]')
        tab_a.wait_for_selector('#cth-qt-toast .cth-qt-undo')
        tab_a.hover('#cth-qt-toast')  # keep tab A's Undo toast open meanwhile
        tab_b.bring_to_front()
        self._pick(tab_b, 'c5', '[TODO]')
        assert self._title_is(tab_b, 'c5', '[TODO] plain chat')
        assert titles['c5'] == '[TODO] plain chat'
        tab_a.bring_to_front()
        tab_a.click('#cth-qt-toast .cth-qt-undo')
        self._alert(tab_a, 'Title changed — not undone')
        sent = [json.loads(c['body'])['title'] for c in self._patches(calls_a) + self._patches(calls_b)]
        assert sent == ['[BUG] plain chat', '[TODO] plain chat'], 'Undo must not overwrite the newer rename'
        assert titles['c5'] == '[TODO] plain chat'
