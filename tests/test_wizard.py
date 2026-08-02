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
        assert result == (item, "ok"), f"Expected {(item, 'ok')}, got {result}"

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

        assert result == (item, "ok")

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

        assert result == (item, "ok")

    def test_not_found_retry_returns_retry_status(self):
        """When not found and user picks retry, return (item, 'retry')."""
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

        assert result == (item, "retry")

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

        assert result == (item, "ok")

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
                    assert result == (item, "ok")
                except Exception as e:
                    pytest.fail(f"Unexpected exception: {e}")


class TestWizardDrawingHelpers:
    """Behavioral tests for the wizard drawing helpers."""

    def test_draw_centered_box_no_nameerror(self):
        """draw_centered_box should not crash with NameError for 'r'."""
        stdscr = Mock()
        # This would crash before the r→row fix
        wizard.draw_centered_box(stdscr, 0, 0, 5, 20)
        # If we reach here, no NameError occurred

    def test_wizard_yes_no_returns_bool(self):
        """_wizard_yes_no returns True for 'y' and False for Enter/'n'/Esc."""
        for ch in (ord('y'), ord('Y')):
            stdscr = Mock()
            stdscr.getch.side_effect = [ch]
            assert wizard._wizard_yes_no(stdscr, 0, 0, 20, "Prompt? (y/N): ") is True
        for ch in (10, 13, ord('n'), ord('N'), 27):
            stdscr = Mock()
            stdscr.getch.side_effect = [ch]
            assert wizard._wizard_yes_no(stdscr, 0, 0, 20, "Prompt? (y/N): ") is False

    def test_wizard_prompt_box_draws_title(self):
        """_wizard_prompt_box clears the box and writes the title at box_y+1."""
        stdscr = Mock()
        title = "Item: AK-47 | Redline"
        wizard._wizard_prompt_box(stdscr, 5, 10, 5, 40, title)
        draws = [c.args for c in stdscr.addstr.call_args_list
                 if c.args and c.args[0] == 6 and c.args[1] == 12 and c.args[2] == title]
        assert draws, "title not drawn at (box_y+1, box_x+2)"
