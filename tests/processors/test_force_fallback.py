"""Tests for force_fallback in EnhancedPipeline._detect_chapters()."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def pipeline():
    from book_ingestion.processors.enhanced_pipeline import EnhancedPipeline, ProcessingMode

    return EnhancedPipeline(mode=ProcessingMode.QUICK, enable_semantic=False)


def _make_text(word_count: int) -> str:
    """Generate text with paragraph breaks."""
    paragraphs = []
    words_remaining = word_count
    while words_remaining > 0:
        chunk = min(500, words_remaining)
        paragraphs.append(" ".join(["word"] * chunk))
        words_remaining -= chunk
    return "\n\n".join(paragraphs)


class TestForceFallback:
    def test_returns_force_fallback_method(self, pipeline):
        """force_fallback=True returns method='force_fallback'."""
        text = _make_text(50000)
        result = pipeline._detect_chapters(text, "test-book", force_fallback=True)
        assert result.method == "force_fallback"

    def test_produces_chapters(self, pipeline):
        """force_fallback=True produces chapters from the text."""
        text = _make_text(50000)
        result = pipeline._detect_chapters(text, "test-book", force_fallback=True)
        assert len(result.chapters) >= 7  # quality gate enforces min 7

    def test_chapters_under_max_words(self, pipeline):
        """All chapters should be under 20k words."""
        text = _make_text(50000)
        result = pipeline._detect_chapters(text, "test-book", force_fallback=True)
        for ch in result.chapters:
            assert ch["word_count"] <= 20000

    def test_confidence_is_moderate(self, pipeline):
        """Fallback confidence should be moderate (not high)."""
        text = _make_text(50000)
        result = pipeline._detect_chapters(text, "test-book", force_fallback=True)
        assert result.confidence <= 0.6

    def test_skips_toc_detection(self, pipeline):
        """force_fallback should not use TOC-based detection."""
        text = _make_text(50000)
        result = pipeline._detect_chapters(text, "test-book", force_fallback=True)
        assert result.toc_chapters_found == 0

    def test_process_book_passes_force_fallback(self, pipeline):
        """process_book forwards force_fallback to _detect_chapters."""
        text = _make_text(20000)
        result = pipeline.process_book(text, "test-book", force_fallback=True)
        assert result.detection_method == "force_fallback"
