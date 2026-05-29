"""Tests for wizard.py: flushinp fix and row/r variable bug fix."""

import pytest
from unittest.mock import Mock, patch

import wizard
from utils import ValidationResult


class TestWizardValidateStep:
    """Tests for _wizard_validate_step flushinp call and correctness."""

    def test_flushinp_called_after_validate(self):
        """_wizard_validate_step should call curses.flushinp() after validate_item."""
        stdscr = Mock()
        stdscr.getmaxyx.return_value = (40, 120)
        stdscr.getch.side_effect = [10]  # Enter key to exit found=True loop
        item = {"name": "AK-47 | Redline", "wear": "Field-Tested", "stattrak": False}

        with patch('wizard.validate_item') as mock_validate:
            mock_validate.return_value = ValidationResult("found", {'buff163': 50.0}, {})
            with patch('wizard.curses.flushinp') as mock_flushinp:
                result = wizard._wizard_validate_step(
                    stdscr, 120, 40, item, "test_key", None, None
                )

        mock_flushinp.assert_called_once()
        mock_validate.assert_called_once()
        assert result == item, f"Expected {item}, got {result}"

    def test_flushinp_called_not_found_path(self):
        """flushinp should also be called in the 'not found' path."""
        stdscr = Mock()
        stdscr.getmaxyx.return_value = (40, 120)
        stdscr.getch.side_effect = [ord('c')]  # Cancel
        item = {"name": "AK-47 | Redline", "wear": "Field-Tested", "stattrak": False}

        with patch('wizard.validate_item') as mock_validate:
            mock_validate.return_value = ValidationResult("not_found", ['AK-47 | Redline (Field-Tested)'], {})
            with patch('wizard.curses.flushinp') as mock_flushinp:
                result = wizard._wizard_validate_step(
                    stdscr, 120, 40, item, "test_key", None, None
                )

        mock_flushinp.assert_called_once()
        mock_validate.assert_called_once()
        assert result is None  # Cancelled

    def test_flushinp_called_api_error_path(self):
        """flushinp should also be called in the API error path."""
        stdscr = Mock()
        stdscr.getmaxyx.return_value = (40, 120)
        stdscr.getch.side_effect = [ord('c')]  # Cancel
        item = {"name": "AK-47 | Redline", "wear": "Field-Tested", "stattrak": False}

        with patch('wizard.validate_item') as mock_validate:
            mock_validate.return_value = ValidationResult("error", "API error", None)
            with patch('wizard.curses.flushinp') as mock_flushinp:
                result = wizard._wizard_validate_step(
                    stdscr, 120, 40, item, "test_key", None, None
                )

        mock_flushinp.assert_called_once()
        mock_validate.assert_called_once()
        assert result is None  # Cancelled

    def test_found_path_returns_item(self):
        """When item is found, the function should return the validated item."""
        stdscr = Mock()
        stdscr.getmaxyx.return_value = (40, 120)
        stdscr.getch.side_effect = [10]  # Enter
        item = {"name": "M4A1-S | Printstream", "wear": None, "stattrak": True}

        with patch('wizard.validate_item') as mock_validate:
            mock_validate.return_value = ValidationResult("found", {'buff163': 320.50}, {})
            with patch('wizard.curses.flushinp'):
                result = wizard._wizard_validate_step(
                    stdscr, 120, 40, item, "test_key", None, None
                )

        assert result == item

    def test_not_found_proceed_returns_item(self):
        """When not found but user chooses to proceed, return the original item."""
        stdscr = Mock()
        stdscr.getmaxyx.return_value = (40, 120)
        stdscr.getch.side_effect = [ord('p')]  # Proceed anyway
        item = {"name": "AK-47 | Redline", "wear": "Field-Tested", "stattrak": False}

        with patch('wizard.validate_item') as mock_validate:
            mock_validate.return_value = ValidationResult("not_found", [], {})
            with patch('wizard.curses.flushinp'):
                result = wizard._wizard_validate_step(
                    stdscr, 120, 40, item, "test_key", None, None
                )

        assert result == item

    def test_not_found_retry_returns_retry_string(self):
        """When not found and user picks retry, return 'RETRY'."""
        stdscr = Mock()
        stdscr.getmaxyx.return_value = (40, 120)
        stdscr.getch.side_effect = [ord('r')]  # Retry
        item = {"name": "AK-47 | Redline", "wear": "Field-Tested", "stattrak": False}

        with patch('wizard.validate_item') as mock_validate:
            mock_validate.return_value = ValidationResult("not_found", [], {})
            with patch('wizard.curses.flushinp'):
                result = wizard._wizard_validate_step(
                    stdscr, 120, 40, item, "test_key", None, None
                )

        assert result == "RETRY"

    def test_not_found_cancel_returns_none(self):
        """When not found and user cancels, return None."""
        stdscr = Mock()
        stdscr.getmaxyx.return_value = (40, 120)
        stdscr.getch.side_effect = [ord('c')]  # Cancel
        item = {"name": "AK-47 | Redline", "wear": "Field-Tested", "stattrak": False}

        with patch('wizard.validate_item') as mock_validate:
            mock_validate.return_value = ValidationResult("not_found", [], {})
            with patch('wizard.curses.flushinp'):
                result = wizard._wizard_validate_step(
                    stdscr, 120, 40, item, "test_key", None, None
                )

        assert result is None

    def test_api_error_proceed_returns_item(self):
        """When API errors and user proceeds, return the original item."""
        stdscr = Mock()
        stdscr.getmaxyx.return_value = (40, 120)
        stdscr.getch.side_effect = [ord('p')]  # Proceed anyway
        item = {"name": "AK-47 | Redline", "wear": "Field-Tested", "stattrak": False}

        with patch('wizard.validate_item') as mock_validate:
            mock_validate.return_value = ValidationResult("error", "No API key", None)
            with patch('wizard.curses.flushinp'):
                result = wizard._wizard_validate_step(
                    stdscr, 120, 40, item, "test_key", None, None
                )

        assert result == item

    def test_no_crash_without_curses_terminal(self):
        """Function should not crash when called with Mock stdscr (no real terminal)."""
        stdscr = Mock()
        stdscr.getmaxyx.return_value = (40, 120)
        stdscr.getch.side_effect = [10]  # Enter
        item = {"name": "Test | Item", "wear": None, "stattrak": False}

        with patch('wizard.validate_item') as mock_validate:
            mock_validate.return_value = ValidationResult("found", {}, {})
            with patch('wizard.curses.flushinp'):
                try:
                    result = wizard._wizard_validate_step(
                        stdscr, 120, 40, item, None, None, None
                    )
                    assert result == item
                except Exception as e:
                    pytest.fail(f"Unexpected exception: {e}")


class TestWizardRowFix:
    """Verify the row/r variable fix — no NameErrors from undefined 'r'."""

    def test_draw_centered_box_no_nameerror(self):
        """draw_centered_box should not crash with NameError for 'r'."""
        stdscr = Mock()
        # This would crash before the r→row fix
        wizard.draw_centered_box(stdscr, 0, 0, 5, 20)
        # If we reach here, no NameError occurred

    def test_wizard_functions_use_row_not_r(self):
        """Verify _wizard_validate_step no longer references undefined 'r'."""
        import inspect
        import re
        src = inspect.getsource(wizard._wizard_validate_step)
        # Search for 'for row in range' blocks — the body should use 'row', not 'r'
        lines = src.split('\n')
        for i, line in enumerate(lines):
            if 'for row in range(' in line:
                # Check the next line for box_y + r (with word boundary so 'row' doesn't match)
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    assert not re.search(r'box_y\s*\+\s*r\b', next_line), \
                        f"Bug found in _wizard_validate_step at line {i+2}: {next_line}"
