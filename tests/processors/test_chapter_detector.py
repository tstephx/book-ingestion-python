"""Tests for chapter candidate detection and scoring"""

import pytest
from src.processors.chapter_detector import (
    ChapterCandidate,
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
