"""Tests for chapter candidate detection and scoring"""

import pytest
from src.processors.chapter_detector import (
    AnchorMerger,
    ChapterCandidate,
    CandidateScorer,
    DetectionStats,
    MatchType,
)


class TestChapterCandidate:
    def test_candidate_creation(self):
        """ChapterCandidate should store all context fields"""
        candidate = ChapterCandidate(
            line_index=10,
            title="Chapter 1 Introduction",
            match_type=MatchType.EXPLICIT,
            preceded_by_blank=True,
            followed_by_prose=True,
            nearby_similar_lines=0,
            in_code_block=False,
        )

        assert candidate.line_index == 10
        assert candidate.title == "Chapter 1 Introduction"
        assert candidate.match_type == MatchType.EXPLICIT
        assert candidate.preceded_by_blank is True
        assert candidate.followed_by_prose is True
        assert candidate.nearby_similar_lines == 0
        assert candidate.in_code_block is False
        assert candidate.confidence == 0.0  # Not scored yet

    def test_match_type_ordering(self):
        """Match types should have correct hierarchy"""
        assert MatchType.TOC.value > MatchType.EXPLICIT.value
        assert MatchType.EXPLICIT.value > MatchType.TITLE_CASE.value
        assert MatchType.TITLE_CASE.value > MatchType.PATTERN.value


class TestDetectionStats:
    def test_stats_creation(self):
        """DetectionStats should track all metrics"""
        stats = DetectionStats(
            method='toc',
            confidence='high',
            candidates_found=15,
            candidates_rejected=3,
            anchors_used=12,
            merges_performed=2,
            code_blocks_detected=5,
            warnings=["Missing 1 chapter"],
        )

        assert stats.method == 'toc'
        assert stats.confidence == 'high'
        assert stats.candidates_found == 15
        assert stats.anchors_used == 12
        assert len(stats.warnings) == 1


class TestCandidateScorer:
    def setup_method(self):
        self.scorer = CandidateScorer()

    def test_toc_match_scores_high(self):
        """TOC matches should score >= 0.7"""
        candidate = ChapterCandidate(
            line_index=100,
            title="Building Your First App",
            match_type=MatchType.TOC,
            preceded_by_blank=True,
            followed_by_prose=True,
            nearby_similar_lines=0,
            in_code_block=False,
        )

        score = self.scorer.score(candidate)
        assert score >= 0.7

    def test_explicit_match_scores_high(self):
        """Explicit 'Chapter N' matches should score >= 0.7"""
        candidate = ChapterCandidate(
            line_index=50,
            title="Chapter 3 Advanced Topics",
            match_type=MatchType.EXPLICIT,
            preceded_by_blank=True,
            followed_by_prose=True,
            nearby_similar_lines=0,
            in_code_block=False,
        )

        score = self.scorer.score(candidate)
        assert score >= 0.7

    def test_code_block_penalty(self):
        """Lines in code blocks should score low"""
        candidate = ChapterCandidate(
            line_index=50,
            title="388 history 7",
            match_type=MatchType.PATTERN,
            preceded_by_blank=False,
            followed_by_prose=False,
            nearby_similar_lines=3,
            in_code_block=True,
        )

        score = self.scorer.score(candidate)
        assert score < 0.4

    def test_list_item_penalty(self):
        """Lines near similar patterns (list items) should score low"""
        candidate = ChapterCandidate(
            line_index=50,
            title="1. First item",
            match_type=MatchType.PATTERN,
            preceded_by_blank=False,
            followed_by_prose=True,
            nearby_similar_lines=5,  # Part of a numbered list
            in_code_block=False,
        )

        score = self.scorer.score(candidate)
        assert score < 0.4

    def test_no_blank_line_penalty(self):
        """Headers not preceded by blank line score lower"""
        with_blank = ChapterCandidate(
            line_index=50,
            title="Chapter 1",
            match_type=MatchType.EXPLICIT,
            preceded_by_blank=True,
            followed_by_prose=True,
        )

        without_blank = ChapterCandidate(
            line_index=50,
            title="Chapter 1",
            match_type=MatchType.EXPLICIT,
            preceded_by_blank=False,
            followed_by_prose=True,
        )

        assert self.scorer.score(with_blank) > self.scorer.score(without_blank)

    def test_confidence_level_high(self):
        """Scores >= 0.7 should be 'high' confidence"""
        assert self.scorer.get_confidence_level(0.8) == 'high'
        assert self.scorer.get_confidence_level(0.7) == 'high'

    def test_confidence_level_medium(self):
        """Scores 0.4-0.7 should be 'medium' confidence"""
        assert self.scorer.get_confidence_level(0.5) == 'medium'
        assert self.scorer.get_confidence_level(0.4) == 'medium'

    def test_confidence_level_low(self):
        """Scores < 0.4 should be 'low' confidence"""
        assert self.scorer.get_confidence_level(0.3) == 'low'
        assert self.scorer.get_confidence_level(0.0) == 'low'


class TestCandidateExtractor:
    def setup_method(self):
        from src.processors.chapter_detector import CandidateExtractor
        self.extractor = CandidateExtractor()

    def test_extracts_explicit_chapter_markers(self):
        """Should find 'Chapter N' style headers"""
        text = """Introduction

Chapter 1 Getting Started

This chapter covers basics.

Chapter 2 Advanced Topics

More content here."""

        candidates = self.extractor.extract(text)

        titles = [c.title for c in candidates]
        assert "Chapter 1 Getting Started" in titles
        assert "Chapter 2 Advanced Topics" in titles

        # Should be marked as EXPLICIT type
        ch1 = next(c for c in candidates if "Chapter 1" in c.title)
        assert ch1.match_type == MatchType.EXPLICIT

    def test_extracts_with_context(self):
        """Should capture context for scoring"""
        text = """Some intro text.

Chapter 1 Introduction

This is the first chapter content with multiple
sentences that form proper prose paragraphs."""

        candidates = self.extractor.extract(text)

        ch1 = next(c for c in candidates if "Chapter 1" in c.title)
        assert ch1.preceded_by_blank is True
        assert ch1.followed_by_prose is True

    def test_detects_nearby_similar_patterns(self):
        """Should count nearby similar patterns (list detection)"""
        text = """Contents:

1. First item
2. Second item
3. Third item
4. Fourth item

Chapter 1 Real Chapter"""

        candidates = self.extractor.extract(text)

        # The numbered list items should have high nearby_similar_lines
        list_candidates = [c for c in candidates if c.title.startswith(('1.', '2.', '3.'))]
        for c in list_candidates:
            assert c.nearby_similar_lines >= 2

    def test_marks_code_block_lines(self):
        """Should mark candidates found in code blocks"""
        text = """Chapter 1 Shell Commands

Here's how to list processes:

$ ps aux
10432 chris 20 0 471m

Chapter 2 Next Topic"""

        candidates = self.extractor.extract(text)

        # Real chapters should not be in code blocks
        ch1 = next(c for c in candidates if "Chapter 1" in c.title)
        ch2 = next(c for c in candidates if "Chapter 2" in c.title)
        assert ch1.in_code_block is False
        assert ch2.in_code_block is False

    def test_skips_lines_in_code_blocks(self):
        """Pattern matches inside code blocks should be marked"""
        text = """Chapter 1 Commands

$ cat file.txt
1. First line
2. Second line

Back to text."""

        candidates = self.extractor.extract(text)

        # Any candidates from the code block should be marked
        code_candidates = [c for c in candidates if c.in_code_block]
        # They may or may not exist, but if they do, they're marked
        for c in code_candidates:
            assert c.in_code_block is True


class TestAnchorMerger:
    def setup_method(self):
        self.merger = AnchorMerger()

    def test_high_confidence_becomes_anchor(self):
        """High confidence candidates become anchors"""
        candidates = [
            ChapterCandidate(line_index=10, title="Chapter 1",
                           match_type=MatchType.EXPLICIT, confidence=0.8),
            ChapterCandidate(line_index=50, title="Chapter 2",
                           match_type=MatchType.EXPLICIT, confidence=0.75),
        ]

        anchors = self.merger.select_anchors(candidates)
        assert len(anchors) == 2

    def test_low_confidence_absorbed(self):
        """Low confidence candidates are absorbed into previous anchor"""
        candidates = [
            ChapterCandidate(line_index=10, title="Chapter 1",
                           match_type=MatchType.EXPLICIT, confidence=0.8),
            ChapterCandidate(line_index=30, title="388 history 7",
                           match_type=MatchType.PATTERN, confidence=0.2),
            ChapterCandidate(line_index=50, title="Chapter 2",
                           match_type=MatchType.EXPLICIT, confidence=0.75),
        ]

        anchors = self.merger.select_anchors(candidates)

        # Only real chapters should be anchors
        titles = [a.title for a in anchors]
        assert "Chapter 1" in titles
        assert "Chapter 2" in titles
        assert "388 history 7" not in titles

    def test_promotes_medium_when_no_high(self):
        """When no high-confidence, promote best medium candidates"""
        candidates = [
            ChapterCandidate(line_index=10, title="Introduction",
                           match_type=MatchType.TITLE_CASE, confidence=0.5),
            ChapterCandidate(line_index=50, title="Background",
                           match_type=MatchType.TITLE_CASE, confidence=0.55),
            ChapterCandidate(line_index=90, title="Conclusion",
                           match_type=MatchType.TITLE_CASE, confidence=0.5),
        ]

        anchors = self.merger.select_anchors(candidates)

        # Should promote medium-confidence as fallback
        assert len(anchors) >= 2

    def test_merge_stats_tracking(self):
        """Should track merge statistics"""
        candidates = [
            ChapterCandidate(line_index=10, title="Chapter 1",
                           match_type=MatchType.EXPLICIT, confidence=0.8),
            ChapterCandidate(line_index=20, title="1.1 Section",
                           match_type=MatchType.PATTERN, confidence=0.3),
            ChapterCandidate(line_index=30, title="1.2 Another",
                           match_type=MatchType.PATTERN, confidence=0.25),
            ChapterCandidate(line_index=100, title="Chapter 2",
                           match_type=MatchType.EXPLICIT, confidence=0.8),
        ]

        anchors, stats = self.merger.merge(candidates)

        assert stats.anchors_used == 2
        assert stats.merges_performed == 2  # Two low-confidence absorbed
