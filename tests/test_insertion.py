"""Tests for text insertion module."""
from unittest.mock import MagicMock, patch

import pytest

from src.insertion.paste import insert_text, _simulate_paste


class TestSimulatePaste:
    @patch("subprocess.run")
    def test_returns_true_on_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = _simulate_paste()
        assert result is True

    @patch("subprocess.run")
    def test_returns_false_on_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="not allowed assistive access")
        result = _simulate_paste()
        assert result is False

    @patch("subprocess.run")
    def test_passes_correct_osascript_command(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        _simulate_paste()
        args = mock_run.call_args[0][0]
        assert "osascript" in args
        assert "keystroke" in " ".join(args)


class TestInsertText:
    @patch("src.insertion.paste._simulate_paste", return_value=True)
    @patch("pyperclip.paste", return_value="original clipboard")
    @patch("pyperclip.copy")
    def test_saves_and_restores_clipboard(self, mock_copy, mock_paste, mock_sim):
        insert_text("hello world", restore_clipboard=True)
        # First copy should set the new text
        first_call = mock_copy.call_args_list[0][0][0]
        assert first_call == "hello world"
        # Second copy should restore original
        second_call = mock_copy.call_args_list[-1][0][0]
        assert second_call == "original clipboard"

    @patch("src.insertion.paste._simulate_paste", return_value=True)
    @patch("pyperclip.paste", return_value="original")
    @patch("pyperclip.copy")
    def test_no_restore_when_disabled(self, mock_copy, mock_paste, mock_sim):
        insert_text("hello", restore_clipboard=False)
        # Should only call copy once (to set new text), not to restore
        assert mock_copy.call_count == 1

    def test_empty_text_returns_false(self):
        result = insert_text("", restore_clipboard=False)
        assert result is False

    @patch("src.insertion.paste._simulate_paste", return_value=False)
    @patch("pyperclip.paste", return_value="")
    @patch("pyperclip.copy")
    def test_returns_false_when_paste_fails(self, mock_copy, mock_paste, mock_sim):
        result = insert_text("some text")
        assert result is False
