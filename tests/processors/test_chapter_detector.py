"""Tests for chapter candidate detection and scoring"""

import pytest
from src.processors.chapter_detector import (
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
