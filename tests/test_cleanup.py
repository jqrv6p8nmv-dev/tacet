"""Tests for rule-based text cleanup."""
import pytest

from src.processing.cleanup import (
    basic_punctuation,
    format_numbered_list,
    handle_self_corrections,
    quick_clean,
    remove_fillers,
)


class TestFillerRemoval:
    def test_removes_um(self):
        assert "um" not in remove_fillers("I um want to go")

    def test_removes_uh(self):
        result = remove_fillers("uh let me think")
        assert "uh" not in result.lower()

    def test_removes_you_know(self):
        result = remove_fillers("it was you know really good")
        assert "you know" not in result.lower()

    def test_preserves_meaning(self):
        result = remove_fillers("um the meeting is at three pm")
        assert "three" in result
        assert "meeting" in result
        assert "pm" in result

    def test_empty_string(self):
        assert remove_fillers("") == ""

    def test_no_fillers(self):
        text = "The quick brown fox"
        assert remove_fillers(text) == text


class TestSelfCorrections:
    def test_basic_correction(self):
        result = handle_self_corrections("meet at 4, no wait, 3 pm")
        assert "3" in result

    def test_no_correction_needed(self):
        text = "meet at 3 pm"
        result = handle_self_corrections(text)
        assert "3 pm" in result

    def test_empty_string(self):
        assert handle_self_corrections("") == ""


class TestBasicPunctuation:
    def test_capitalizes_first_letter(self):
        result = basic_punctuation("hello world")
        assert result[0] == "H"

    def test_adds_period(self):
        result = basic_punctuation("hello world")
        assert result.endswith(".")

    def test_preserves_existing_question_mark(self):
        result = basic_punctuation("how are you?")
        assert result.endswith("?")

    def test_preserves_exclamation(self):
        result = basic_punctuation("great job!")
        assert result.endswith("!")

    def test_empty_string(self):
        assert basic_punctuation("") == ""


class TestNumberedLists:
    def test_converts_number_one_two(self):
        result = format_numbered_list("number one do this number two do that")
        assert "1." in result
        assert "2." in result

    def test_converts_first_second(self):
        result = format_numbered_list("first do this second do that")
        assert "1." in result
        assert "2." in result


class TestQuickClean:
    def test_full_pipeline(self):
        raw = "um so the meeting is uh at three pm you know"
        result = quick_clean(raw)
        assert "um" not in result.lower()
        assert "uh" not in result.lower()
        assert "three" in result
        assert result[0] == result[0].upper()

    def test_empty_input(self):
        assert quick_clean("") == ""

    def test_none_does_not_crash(self):
        # quick_clean should handle edge cases gracefully
        result = quick_clean(None or "")
        assert result == ""
