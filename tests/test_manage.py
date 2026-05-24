"""Tests for manage.py: input buffer drain fix and API validation progress."""

import builtins
from unittest.mock import Mock, patch, call

import manage


class TestDrainStdin:
    """Tests for the _drain_stdin helper function."""

    def test_drain_stdin_no_crash(self):
        """_drain_stdin should not raise even without a real TTY."""
        manage._drain_stdin()  # Should be a no-op

    @patch('termios.tcflush')
    @patch('sys.stdin.fileno', return_value=0)
    def test_drain_stdin_calls_tcflush(self, mock_fileno, mock_tcflush):
        """_drain_stdin should call termios.tcflush to discard buffered input."""
        manage._drain_stdin()
        mock_tcflush.assert_called_once()

    @patch('termios.tcflush')
    @patch('sys.stdin.fileno', return_value=0)
    def test_drain_stdin_passes_correct_fd(self, mock_fileno, mock_tcflush):
        """_drain_stdin should pass stdin's fd to tcflush with TCIFLUSH."""
        import termios
        manage._drain_stdin()
        mock_tcflush.assert_called_once_with(0, termios.TCIFLUSH)

    @patch('sys.stdin.fileno', return_value=0)
    def test_drain_stdin_handles_oserror(self, mock_fileno):
        """_drain_stdin should handle OSError/termios.error from tcflush gracefully."""
        import termios
        with patch('termios.tcflush', side_effect=termios.error(25, 'Inappropriate ioctl')):
            manage._drain_stdin()  # Should not raise

    @patch('sys.stdin.fileno', return_value=0)
    def test_drain_stdin_handles_no_fileno(self, mock_fileno):
        """_drain_stdin should handle AttributeError (no fileno) gracefully."""
        mock_fileno.side_effect = AttributeError("stdin has no fileno")
        manage._drain_stdin()  # Should not raise

    def test_drain_stdin_handles_no_termios(self):
        """_drain_stdin should handle ImportError for termios gracefully (non-POSIX)."""
        orig_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == 'termios':
                raise ImportError(f"No module named '{name}'")
            return orig_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=mock_import):
            manage._drain_stdin()  # Should not raise


class TestCmdAddFlow:
    """Tests for cmd_add API validation flow."""

    @patch('manage._drain_stdin')
    @patch('manage.validate_item')
    @patch('manage.load_config', return_value={'api_key': 'test-key'})
    @patch('manage._safe_input')
    @patch('manage._select_weapon')
    def test_checking_api_printed_before_validate(
        self, mock_select_weapon, mock_input, mock_config,
        mock_validate, mock_drain
    ):
        """cmd_add should print 'Checking API...' before calling validate_item."""
        # Mock the full interactive flow for a successful add
        mock_select_weapon.return_value = "AK-47"
        mock_input.side_effect = [
            'Redline',  # Skin
            'ft',       # Wear
            'n',        # StatTrak (no)
            'y',        # Confirm add
        ]
        mock_validate.return_value = (True, {'buff163': 50.0, 'skins': 48.0}, {})

        with patch('manage.print') as mock_print:
            with patch('manage.get_all_items', return_value=[]):
                with patch('manage.save_items'):
                    manage.cmd_add()

        # Verify 'Checking API...' was printed before validate_item was called
        print_calls = [c.args[0] for c in mock_print.call_args_list
                       if c.args and 'Checking API...' in str(c.args[0])]
        assert len(print_calls) == 1, \
            f"Expected 1 'Checking API...' print, got {len(print_calls)}: {print_calls}"

        # Verify validate_item and _drain_stdin were called
        mock_validate.assert_called_once()
        mock_drain.assert_called_once()

    @patch('manage._drain_stdin')
    @patch('manage.validate_item')
    @patch('manage.load_config', return_value={'api_key': 'test-key'})
    @patch('manage._safe_input')
    @patch('manage._select_weapon')
    def test_drain_called_after_each_validate(
        self, mock_select_weapon, mock_input, mock_config,
        mock_validate, mock_drain
    ):
        """_drain_stdin should be called after every validate_item call."""
        mock_select_weapon.return_value = "AK-47"
        mock_input.side_effect = [
            'Redline',     # Skin
            'ft',          # Wear
            'n',           # StatTrak (no)
            'c',           # Cancel on the "not found" prompt
        ]
        # First call: item not found but has suggestions
        # (Second call from retry won't happen since we cancel)
        mock_validate.return_value = (False, ['AK-47 | Redline (Field-Tested)'], {})

        with patch('manage.get_all_items', return_value=[]):
            with patch('manage.save_items'):
                manage.cmd_add()

        # validate_item was called once, _drain_stdin should also be called once
        mock_validate.assert_called_once()
        mock_drain.assert_called_once()

    @patch('manage._drain_stdin')
    @patch('manage.validate_item')
    @patch('manage.load_config', return_value={'api_key': 'test-key'})
    @patch('manage._safe_input')
    @patch('manage._select_weapon')
    def test_drain_called_on_retry_validate(
        self, mock_select_weapon, mock_input, mock_config,
        mock_validate, mock_drain
    ):
        """_drain_stdin should be called after each retry validate_item call."""
        mock_select_weapon.return_value = "AK-47"
        mock_input.side_effect = [
            'Redline',     # Skin (first attempt)
            'ft',          # Wear
            'n',           # StatTrak (no)
            'r',           # Retry
            'New Skin',    # New skin name
            'y',           # Confirm add (after found)
        ]
        # First call: not found, second call: found
        mock_validate.side_effect = [
            (False, ['AK-47 | Redline (Field-Tested)'], {}),
            (True, {'buff163': 50.0}, {}),
        ]

        with patch('manage.print'):
            with patch('manage.get_all_items', return_value=[]):
                with patch('manage.save_items'):
                    manage.cmd_add()

        # validate_item was called twice, _drain_stdin should also be called twice
        assert mock_validate.call_count == 2
        assert mock_drain.call_count == 2
