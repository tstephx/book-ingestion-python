"""Tests for post-split quality gate in ChapterSplitter."""

import pytest
from types import SimpleNamespace

from book_ingestion.processors.chapter_splitter import ChapterSplitter


@pytest.fixture
def splitter():
    """Create a ChapterSplitter with mocked config."""
    config = SimpleNamespace(
        chapter_detection={
            'patterns': [r'^Chapter\s+\d+'],
            'min_words_per_chapter': 100,
            'max_words_per_chapter': 50_000,
        }
    )
    return ChapterSplitter(config)


def _make_chapter(book_id, num, title, word_count, use_paragraphs=True):
    """Helper to create a chapter dict with content of the given word count."""
    if use_paragraphs:
        # Create content with paragraph breaks every ~500 words
        paragraphs = []
        words_remaining = word_count
        while words_remaining > 0:
            chunk = min(500, words_remaining)
            paragraphs.append(' '.join([f'word{i}' for i in range(chunk)]))
            words_remaining -= chunk
        content = '\n\n'.join(paragraphs)
    else:
        # Single block with no paragraph breaks
        content = ' '.join([f'word{i}' for i in range(word_count)])
    return {
        'id': f'{book_id}-ch{num}',
        'book_id': book_id,
        'chapter_number': num,
        'title': title,
        'content': content,
        'word_count': len(content.split()),
        'file_path': '',
    }


class TestQualityResplitGoodSplit:
    """Good splits should pass through unchanged."""

    def test_good_split_unchanged(self, splitter):
        """10 chapters at 5k words each should not be modified."""
        chapters = [
            _make_chapter('book1', i + 1, f'Chapter {i + 1}', 5000)
            for i in range(10)
        ]
        result = splitter._quality_resplit(chapters, 'book1')
        assert len(result) == 10
        for i, ch in enumerate(result):
            assert ch['title'] == f'Chapter {i + 1}'

    def test_empty_chapters(self, splitter):
        """Empty list should return empty."""
        result = splitter._quality_resplit([], 'book1')
        assert result == []

    def test_single_small_chapter(self, splitter):
        """Single chapter under thresholds stays as-is."""
        chapters = [_make_chapter('book1', 1, 'Intro', 3000)]
        result = splitter._quality_resplit(chapters, 'book1')
        assert len(result) == 1
        assert result[0]['title'] == 'Intro'


class TestOversizedChapter:
    """Chapters exceeding _QG_MAX_CHAPTER_WORDS get re-split."""

    def test_oversized_chapter_resplit(self, splitter):
        """A 30k word chapter should be split into multiple under 20k."""
        chapters = [
            _make_chapter('book1', i + 1, f'Chapter {i + 1}', 5000)
            for i in range(9)
        ]
        chapters.append(_make_chapter('book1', 10, 'Big Chapter', 30000))
        result = splitter._quality_resplit(chapters, 'book1')
        for ch in result:
            assert ch['word_count'] <= 20_000, (
                f"Chapter '{ch['title']}' has {ch['word_count']} words, exceeds 20k"
            )
        assert len(result) > 10

    def test_oversized_first_part_keeps_title(self, splitter):
        """First part of resplit keeps the original title."""
        chapters = [_make_chapter('book1', 1, 'Big Chapter', 30000)]
        # Add enough small chapters to avoid min-chapter trigger
        for i in range(8):
            chapters.append(_make_chapter('book1', i + 2, f'Ch {i + 2}', 5000))
        result = splitter._quality_resplit(chapters, 'book1')
        assert result[0]['title'] == 'Big Chapter'

    def test_oversized_subsequent_parts_titled(self, splitter):
        """Subsequent parts get '(part N)' suffix."""
        chapters = [_make_chapter('book1', 1, 'Big Chapter', 30000)]
        for i in range(8):
            chapters.append(_make_chapter('book1', i + 2, f'Ch {i + 2}', 5000))
        result = splitter._quality_resplit(chapters, 'book1')
        part_titles = [ch['title'] for ch in result if 'part' in ch['title']]
        assert len(part_titles) > 0
        assert all('Big Chapter (part' in t for t in part_titles)


class TestTooFewChapters:
    """When total chapters < _QG_MIN_CHAPTERS, largest are re-split."""

    def test_too_few_chapters_triggers_resplit(self, splitter):
        """3 large chapters should produce more than the original 3."""
        chapters = [
            _make_chapter('book1', i + 1, f'Chapter {i + 1}', 25000)
            for i in range(3)
        ]
        result = splitter._quality_resplit(chapters, 'book1')
        assert len(result) >= splitter._QG_MIN_CHAPTERS

    def test_small_chapters_not_split_below_target(self, splitter):
        """Chapters under target_max (10k) should not be resplit even if too few."""
        chapters = [
            _make_chapter('book1', i + 1, f'Chapter {i + 1}', 3000)
            for i in range(4)
        ]
        result = splitter._quality_resplit(chapters, 'book1')
        # Can't increase count since chapters are small - stays at 4
        assert len(result) == 4


class TestLopsidedRatio:
    """When max/median ratio exceeds threshold, outliers are re-split."""

    def test_lopsided_ratio_triggers_resplit(self, splitter):
        """8 chapters where one is 9x the median should be resplit."""
        # 7 chapters at 2k words each, 1 at 18k words
        # median = 2000, ratio = 18000/2000 = 9.0 > 4.0
        chapters = [
            _make_chapter('book1', i + 1, f'Chapter {i + 1}', 2000)
            for i in range(7)
        ]
        chapters.append(_make_chapter('book1', 8, 'Huge Chapter', 18000))
        result = splitter._quality_resplit(chapters, 'book1')
        # The huge chapter should be split
        assert len(result) > 8
        # No chapter should be wildly larger than the rest
        word_counts = [ch['word_count'] for ch in result]
        from statistics import median
        med = median(word_counts)
        max_wc = max(word_counts)
        # After resplit, ratio should be better (may take multiple rounds)
        assert max_wc <= med * splitter._QG_MAX_TO_MEDIAN_RATIO + 500  # small tolerance

    def test_balanced_ratio_unchanged(self, splitter):
        """Chapters with acceptable ratio should not be touched."""
        # All chapters around 3k-5k words
        chapters = [
            _make_chapter('book1', i + 1, f'Chapter {i + 1}', 3000 + i * 200)
            for i in range(10)
        ]
        result = splitter._quality_resplit(chapters, 'book1')
        assert len(result) == 10


class TestRenumbering:
    """Chapters are renumbered after resplit."""

    def test_chapters_renumbered(self, splitter):
        """After resplit, chapter numbers should be sequential from 1."""
        chapters = [
            _make_chapter('book1', 1, 'Big Chapter', 30000),
        ]
        for i in range(8):
            chapters.append(_make_chapter('book1', i + 2, f'Ch {i + 2}', 5000))
        result = splitter._quality_resplit(chapters, 'book1')
        for i, ch in enumerate(result):
            assert ch['chapter_number'] == i + 1
            assert ch['id'] == f'book1-ch{i + 1}'


class TestPreservesGoodChapters:
    """Good chapters should not be modified."""

    def test_good_chapters_preserved(self, splitter):
        """Content of chapters that don't need resplit stays the same."""
        good_ch = _make_chapter('book1', 1, 'Good Chapter', 5000)
        original_content = good_ch['content']
        chapters = [good_ch]
        # Add a bad chapter to trigger resplit
        chapters.append(_make_chapter('book1', 2, 'Big Chapter', 30000))
        # Add more to avoid min-chapter trigger affecting good chapter
        for i in range(6):
            chapters.append(_make_chapter('book1', i + 3, f'Ch {i + 3}', 5000))
        result = splitter._quality_resplit(chapters, 'book1')
        # First chapter content should be unchanged
        assert result[0]['content'] == original_content


class TestSplitsAtBlankLines:
    """Resplit should split at paragraph boundaries."""

    def test_splits_at_paragraph_boundaries(self, splitter):
        """Content with paragraph breaks should split at those breaks."""
        # Create a chapter with 3 large paragraphs
        para1 = ' '.join([f'alpha{i}' for i in range(8000)])
        para2 = ' '.join([f'beta{i}' for i in range(8000)])
        para3 = ' '.join([f'gamma{i}' for i in range(8000)])
        content = f'{para1}\n\n{para2}\n\n{para3}'
        chapter = {
            'id': 'book1-ch1',
            'book_id': 'book1',
            'chapter_number': 1,
            'title': 'Big Chapter',
            'content': content,
            'word_count': len(content.split()),
            'file_path': '',
        }
        parts = splitter._resplit_chapter(chapter, 'book1', 10000)
        assert len(parts) >= 2
        # First part should start with alpha words
        assert parts[0]['content'].startswith('alpha0')
        # No part should exceed max_words (with some tolerance for paragraph boundaries)
        for p in parts:
            assert p['word_count'] <= 20000  # generous upper bound


class TestFallbackNoBreaks:
    """When no paragraph breaks, falls back to word-count chunking."""

    def test_no_paragraph_breaks_fallback(self, splitter):
        """Single block of text with no blank lines uses word chunking."""
        chapter = _make_chapter('book1', 1, 'Dense Chapter', 25000, use_paragraphs=False)
        parts = splitter._resplit_chapter(chapter, 'book1', 10000)
        assert len(parts) >= 2
        # Each part should be roughly max_words or less
        for p in parts:
            assert p['word_count'] <= 10001  # allow for rounding
        # First part keeps original title
        assert parts[0]['title'] == 'Dense Chapter'
        # Subsequent parts get "(part N)"
        if len(parts) > 1:
            assert parts[1]['title'] == 'Dense Chapter (part 2)'
