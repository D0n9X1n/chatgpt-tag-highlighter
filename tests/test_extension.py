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
import time
import pytest
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EXT_PATH = str(ROOT / 'dist' / 'chrome')
UNIT_TEST_PATH = str(ROOT / 'tests' / 'unit_test.html')
STORAGE_KEY = 'tagHighlighterConfigV1'


@pytest.fixture(scope='session')
def browser_context():
    """Launch Chromium with the extension loaded in a temporary profile."""
    pw = sync_playwright().start()
    profile_dir = str(Path(__file__).parent / '.test-profile')
    context = pw.chromium.launch_persistent_context(
        profile_dir,
        headless=False,
        args=[
            f'--disable-extensions-except={EXT_PATH}',
            f'--load-extension={EXT_PATH}',
            '--disable-blink-features=AutomationControlled',
        ],
        ignore_default_args=['--enable-automation'],
    )
    yield context
    context.close()
    pw.stop()


@pytest.fixture(scope='session')
def ext_id(browser_context):
    """Discover the extension ID at runtime."""
    page = browser_context.new_page()
    page.goto('chrome://extensions')
    page.wait_for_timeout(2000)
    eid = page.evaluate(
        'document.querySelector("extensions-manager")'
        '.shadowRoot.querySelector("extensions-item-list")'
        '.shadowRoot.querySelector("extensions-item").id'
    )
    page.close()
    return eid


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
        """Clicking Save should persist the current UI state to storage."""
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
        # Check hideNavBar
        page.check('#hideNavBar')
        # Click Save
        page.click('#save')
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
        after_add = page.evaluate("document.querySelectorAll('#rows tr').length")
        assert after_add == 2, f'Expected 2 rows after add, got {after_add}'

        # Delete the first row
        page.click('#rows tr:first-child .del')
        after_delete = page.evaluate("document.querySelectorAll('#rows tr').length")
        assert after_delete == 1, f'Expected 1 row after delete, got {after_delete}'

        page.close()

    def test_reset_restores_defaults(self, browser_context, ext_id):
        """Reset button should restore default config."""
        page = self._open_options()

        # Set non-default config
        self._set_config(page, {
            'rules': [{'tag': '[CUSTOM]', 'match': 'includes', 'color': '#111111', 'hide': True}],
            'maxChatTurns': 99,
            'hideNavBar': False,
        })
        page.reload()
        page.wait_for_timeout(1500)

        # Click Reset
        page.click('#reset')
        page.wait_for_timeout(500)

        cfg = self._get_config(page)
        page.close()

        assert cfg['rules'][0]['tag'] == '[TODO]', 'Reset should restore [TODO] rule'
        assert cfg['maxChatTurns'] == 0, 'Reset should restore maxChatTurns=0'

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
        """Reordering rows and saving should persist new order."""
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

        # Simulate reorder via JS (drag API is hard in Playwright)
        page.evaluate("""
            const rows = document.getElementById('rows');
            const trs = rows.querySelectorAll('tr');
            rows.insertBefore(trs[1], trs[0]);
        """)

        page.click('#save')
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
        page.click('#save')
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

    def test_import_with_all_fields(self, browser_context, ext_id):
        """Import should handle all config fields including overlay, dimUntagged, showBadge."""
        page = self._open_options()
        page.click('#importCfg')
        page.wait_for_timeout(300)

        new_cfg = {
            'rules': [{'tag': '[X]', 'match': 'startsWith', 'color': '#fabd2f', 'hide': False, 'overlay': False}],
            'maxChatTurns': 5, 'hideNavBar': False, 'dimUntagged': True, 'showBadge': False,
        }
        page.fill('#importText', json.dumps(new_cfg))
        page.click('#importApply')
        page.wait_for_timeout(500)

        cfg = self._get_config(page)
        page.close()
        assert cfg['rules'][0]['overlay'] is False
        assert cfg['dimUntagged'] is True
        assert cfg['showBadge'] is False
        assert cfg['hideNavBar'] is False
        assert cfg['maxChatTurns'] == 5

    def test_reset_has_four_default_rules(self, browser_context, ext_id):
        """Reset should restore 4 default rules including demo rules."""
        page = self._open_options()

        self._set_config(page, {
            'rules': [{'tag': '[CUSTOM]', 'match': 'includes', 'color': '#111111', 'hide': True}],
            'maxChatTurns': 99, 'hideNavBar': False,
        })
        page.reload()
        page.wait_for_timeout(1500)

        page.click('#reset')
        page.wait_for_timeout(500)

        cfg = self._get_config(page)
        page.close()
        assert len(cfg['rules']) == 4, f'Reset should have 4 rules, got {len(cfg["rules"])}'
        assert cfg['rules'][0]['tag'] == '[TODO]'
        assert cfg['rules'][2]['tag'] == 'code'
        assert cfg['rules'][2]['match'] == 'includes'
        assert cfg['rules'][3]['tag'] == 'help'


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
        page.click('#save')
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
        page.click('#save')
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
