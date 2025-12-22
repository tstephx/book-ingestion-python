"""Tests for improved chapter splitter"""

import pytest
from src.processors.chapter_splitter import ChapterSplitter
from src.utils.config import Config


class TestImprovedChapterSplitter:
    def setup_method(self):
        config = Config()
        self.splitter = ChapterSplitter(config)

    def test_filters_code_block_false_positives(self):
        """Should not detect code output as chapters"""
        text = """Chapter 1 Using the Shell

This chapter covers shell basics.

$ ps aux
10432 chris 20 0 471m 121m 18m S 99.9 3.2 77:01.76 bigcommand
20284 root 25 5 98.7m 932 644 D 2.7 0.0 0:00.96 updatedb

The output shows running processes.

Chapter 2 Advanced Commands

More content here with substantial text to make this
a valid chapter with enough words to pass validation.
We need at least 500 words so let me add more content.
""" + "More content. " * 200  # Pad to meet word minimums

        chapters = self.splitter.split(text, "test-book-1")

        titles = [ch['title'] for ch in chapters]

        # Should have the real chapters
        assert any("Chapter 1" in t for t in titles)
        assert any("Chapter 2" in t for t in titles)

        # Should NOT have the code output
        assert not any("10432" in t for t in titles)
        assert not any("20284" in t for t in titles)

    def test_returns_detection_stats(self):
        """Should return detection statistics"""
        text = """Chapter 1 Introduction

Content here. """ + "More words. " * 300 + """

Chapter 2 Methods

More content. """ + "Additional text. " * 300

        result = self.splitter.split_with_stats(text, "test-book-2")

        assert 'chapters' in result
        assert 'stats' in result
        assert result['stats'].candidates_found >= 2
        assert result['stats'].anchors_used >= 2

    def test_handles_numbered_lists_correctly(self):
        """Should not detect numbered list items as chapters"""
        text = """Chapter 1 Setup

Before starting, gather these items:

1. A computer
2. An internet connection
3. A text editor
4. Some patience
5. Coffee (optional)

Now let's begin the actual content of this chapter.
""" + "Explanation text. " * 300 + """

Chapter 2 Installation

More content here.""" + " Installation details. " * 300

        chapters = self.splitter.split(text, "test-book-3")

        titles = [ch['title'] for ch in chapters]

        # Should have real chapters
        assert any("Chapter 1" in t for t in titles)
        assert any("Chapter 2" in t for t in titles)

        # Should NOT have list items
        assert not any(t.strip().startswith("1.") for t in titles)
        assert not any(t.strip().startswith("2.") for t in titles)

    def test_backwards_compatible_api(self):
        """split() should work exactly as before"""
        text = """Chapter 1 First

Content. """ + "Words. " * 300 + """

Chapter 2 Second

More. """ + "Text. " * 300

        # Should return list of chapter dicts (not ChapterResult)
        chapters = self.splitter.split(text, "test-book-4")

        assert isinstance(chapters, list)
        assert len(chapters) >= 2
        assert all(isinstance(ch, dict) for ch in chapters)
        assert all('id' in ch and 'title' in ch and 'content' in ch for ch in chapters)
