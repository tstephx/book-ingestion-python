"""Tests for enhanced text cleaning"""

import pytest
from unittest.mock import MagicMock
from src.processors.text_cleaner import TextCleaner, CleaningStats


@pytest.fixture
def cleaner():
    """Create a cleaner with all options enabled"""
    config = MagicMock()
    config.text_cleaning = {
        'strip_markup': True,
        'normalize_unicode': True,
        'normalize_quotes': True,
        'normalize_dashes': True,
        'remove_control_chars': True,
        'remove_page_numbers': True,
        'normalize_whitespace': True,
    }
    return TextCleaner(config)


class TestCleaningStats:
    def test_chars_removed_property(self):
        stats = CleaningStats(original_length=100, final_length=80)
        assert stats.chars_removed == 20


class TestTextCleaner:
    def test_backwards_compatible_clean_returns_string(self, cleaner):
        """clean() should return just the text string"""
        result = cleaner.clean("Hello world")
        assert isinstance(result, str)
        assert result == "Hello world"

    def test_clean_with_stats_returns_dict(self, cleaner):
        """clean_with_stats() should return dict with text and stats"""
        result = cleaner.clean_with_stats("Hello world")
        assert 'text' in result
        assert 'stats' in result
        assert isinstance(result['stats'], CleaningStats)

    def test_smart_quote_normalization(self, cleaner):
        """Should convert smart quotes to ASCII"""
        text = '\u201cHello\u201d and \u2018world\u2019'
        result = cleaner.clean_with_stats(text)
        assert result['text'] == '"Hello" and \'world\''
        assert result['stats'].quotes_normalized == 4

    def test_german_quotes(self, cleaner):
        """Should normalize German-style quotes"""
        text = '\u201eGuten Tag\u201d'  # „ and "
        result = cleaner.clean(text)
        assert result == '"Guten Tag"'

    def test_french_quotes(self, cleaner):
        """Should normalize French-style guillemets"""
        text = '\u00abBonjour\u00bb'  # « and »
        result = cleaner.clean(text)
        assert result == '"Bonjour"'

    def test_dash_normalization(self, cleaner):
        """Should normalize various dashes"""
        text = "pages 10\u201320 and also\u2014here"  # en-dash and em-dash
        result = cleaner.clean_with_stats(text)
        assert result['text'] == "pages 10-20 and also--here"
        assert result['stats'].dashes_normalized == 2

    def test_control_char_removal(self, cleaner):
        """Should remove control characters but keep newlines/tabs"""
        text = "Hello\x00World\x07\nNew\tLine"
        result = cleaner.clean_with_stats(text)
        assert result['text'] == "HelloWorld\nNew Line"
        assert result['stats'].control_chars_removed == 2

    def test_preserves_newlines_and_tabs(self, cleaner):
        """Should preserve newlines and tabs"""
        text = "Line1\nLine2\tTabbed"
        result = cleaner.clean(text)
        # Tab becomes space due to whitespace normalization
        assert "Line1\nLine2" in result

    def test_html_tag_removal(self, cleaner):
        """Should strip HTML tags"""
        text = "<p>Hello <b>world</b></p>"
        result = cleaner.clean_with_stats(text)
        # Result should have content without tags
        assert '<' not in result['text']
        assert 'Hello' in result['text']
        assert 'world' in result['text']

    def test_html_entity_handling(self, cleaner):
        """Should handle HTML entities when bs4 not available"""
        # Test with regex fallback
        from src.processors import text_cleaner
        original_has_bs4 = text_cleaner.HAS_BS4
        text_cleaner.HAS_BS4 = False
        try:
            text = "Hello&nbsp;World &amp; Others"
            result = cleaner.clean(text)
            assert 'Hello' in result
            assert '&' in result or 'and' in result.lower()
        finally:
            text_cleaner.HAS_BS4 = original_has_bs4

    def test_whitespace_normalization(self, cleaner):
        """Should normalize excessive whitespace"""
        text = "Hello    world\n\n\n\nNew paragraph"
        result = cleaner.clean(text)
        assert "Hello world" in result
        assert "\n\n\n" not in result  # Max 2 newlines

    def test_page_number_removal(self, cleaner):
        """Should remove standalone page numbers after TOC area (line 600+)"""
        # Page number removal skips first 600 lines to preserve chapter numbers in TOC
        # Build text with 605 lines, put page number at line 602
        prefix_lines = ["Content line"] * 601  # Lines 0-600
        test_lines = ["Chapter 5", "42", "More content"]  # Lines 601-603
        text = '\n'.join(prefix_lines + test_lines)

        result = cleaner.clean(text)
        # The standalone "42" at line 602 should be removed
        lines = result.split('\n')
        # Check lines after prefix area
        tail_lines = [l.strip() for l in lines[600:] if l.strip()]
        assert '42' not in tail_lines, f"'42' should be removed. Tail lines: {tail_lines[:10]}"

    def test_combined_cleaning(self, cleaner):
        """Test all cleaning operations together"""
        text = '<p>\u201cHello\u201d\u2014world</p>\n\n\n\n        Some  extra   spaces'
        result = cleaner.clean_with_stats(text)

        # Check transformations applied
        assert '\u201c' not in result['text']  # Smart quotes normalized
        assert '\u2014' not in result['text']  # Em dash normalized
        assert '<' not in result['text']  # HTML removed
        assert '   ' not in result['text']  # Extra spaces removed

    def test_stats_tracking(self, cleaner):
        """Should track all cleaning statistics"""
        text = '<b>\u201ctest\u201d</b>\u2014dash\x00ctrl'
        result = cleaner.clean_with_stats(text)
        stats = result['stats']

        assert stats.original_length == len(text)
        assert stats.final_length == len(result['text'])
        assert stats.quotes_normalized >= 2
        assert stats.dashes_normalized >= 1
        assert stats.control_chars_removed >= 1
        assert stats.chars_removed > 0

    def test_disabled_options(self):
        """Should respect disabled config options"""
        config = MagicMock()
        config.text_cleaning = {
            'strip_markup': False,
            'normalize_unicode': False,
            'normalize_quotes': False,
            'normalize_dashes': False,
            'remove_control_chars': False,
            'remove_page_numbers': False,
            'normalize_whitespace': False,
        }
        cleaner = TextCleaner(config)

        text = '<b>"test"</b>'
        result = cleaner.clean(text)
        # Nothing should be changed
        assert result == text
