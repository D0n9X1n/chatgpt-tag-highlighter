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
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EXT_PATH = str(ROOT / 'dist' / 'chrome')
UNIT_TEST_PATH = str(ROOT / 'tests' / 'unit_test.html')
STORAGE_KEY = 'tagHighlighterConfigV1'

# CI detection — GitHub Actions and most CI providers set CI=true.
# In CI we use a throwaway profile dir under tempfile so each run is clean.
# Locally we keep the persistent .test-profile so contributors can reuse
# extension state (and, for live ChatGPT tests, login cookies).
IS_CI = os.environ.get('CI', '').lower() in ('1', 'true', 'yes')


def _profile_dir():
    if IS_CI:
        # tmp_path_factory would also work, but we want a stable per-session
        # path so a single browser_context is reused across the whole run.
        return tempfile.mkdtemp(prefix='cth-ci-profile-')
    return str(Path(__file__).parent / '.test-profile')


@pytest.fixture(scope='session')
def browser_context():
    """Launch Chromium with the extension loaded.

    Local dev: persistent profile at tests/.test-profile, headed window.
    CI: throwaway temp profile, headed-via-Xvfb (extensions still don't
    load reliably in --headless=new across all Chromium builds, so we keep
    headless=False and rely on Xvfb in CI — see .github/workflows/test.yml).
    """
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        _profile_dir(),
        headless=False,
        args=[
            f'--disable-extensions-except={EXT_PATH}',
            f'--load-extension={EXT_PATH}',
            '--disable-blink-features=AutomationControlled',
            # Make the headed window deterministic in CI/Xvfb.
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
        except Exception:
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
        # Abort the smooth scroll and, at the same moment, simulate a user wheel.
        page.evaluate("""() => {
            const s = document.getElementById('scroll-root');
            let fired = false;
            s.addEventListener('scroll', () => {
                if (fired) return;
                fired = true;
                s.scrollTop = s.scrollTop + 1;
                s.dispatchEvent(new WheelEvent('wheel', {bubbles: true, deltaY: -10}));
            });
        }""")
        page.click('#cth-overlay .cth-arrow')
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

    # ---- Delete untagged chats (ChatGPT's private API is mocked; never live) ----

    def _mock_chat_api(self, page, chats=None, session_token='test-token',
                       server_limit=None, patch_status=None, hold_first_patch=False,
                       hold_list_pass=None, patch_body=None):
        """Mock /api/auth/session, the conversation list, and per-chat PATCH.

        Records every API request in the returned list. `server_limit` caps
        the page size the mock server returns, like a real server might.
        `hold_list_pass` holds the first page of that listing pass (0 = preview,
        1 = the re-check at confirm time) until the test fulfills it.
        """
        chats = API_CHATS if chats is None else chats
        calls = []
        held = []
        passes = {'n': -1}  # listing passes started (a pass begins at offset=0)

        def record(route):
            req = route.request
            calls.append({'method': req.method, 'url': req.url,
                          'auth': req.all_headers().get('authorization'),
                          'body': req.post_data})

        def session(route):
            record(route)
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

        def patch(route):
            record(route)
            if hold_first_patch and not held:
                held.append(route)  # fulfilled later by the test
                return
            status = patch_status or 200
            route.fulfill(status=status, content_type='application/json',
                          body=json.dumps(patch_body if patch_body is not None else {'success': status == 200}))

        page.route('https://chatgpt.com/api/auth/session', session)
        page.route('https://chatgpt.com/backend-api/conversations?*', listing)
        page.route('https://chatgpt.com/backend-api/conversation/*', patch)
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
