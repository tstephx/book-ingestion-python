"""Chapter candidate detection and confidence scoring"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional


class MatchType(IntEnum):
    """
    Chapter match type hierarchy (higher = more confident).
    """
    PATTERN = 1      # Matches generic pattern like ^\d+\.\s+
    TITLE_CASE = 2   # Title-case heading preceded by blank
    EXPLICIT = 3     # Contains "Chapter", "Part", "Lesson", etc.
    TOC = 4          # Found in TOC and matched in body


@dataclass
class ChapterCandidate:
    """
    A potential chapter marker with context for scoring.
    """
    line_index: int
    title: str
    match_type: MatchType

    # Context for confidence scoring
    preceded_by_blank: bool = False
    followed_by_prose: bool = False
    nearby_similar_lines: int = 0
    in_code_block: bool = False

    # Computed after scoring
    confidence: float = 0.0


@dataclass
class DetectionStats:
    """
    Statistics about chapter detection for debugging and quality tracking.
    """
    method: str  # 'toc', 'pattern', 'fallback'
    confidence: str  # 'high', 'medium', 'low'
    candidates_found: int = 0
    candidates_rejected: int = 0
    anchors_used: int = 0
    merges_performed: int = 0
    code_blocks_detected: int = 0
    warnings: List[str] = field(default_factory=list)


@dataclass
class ChapterResult:
    """
    Result of chapter detection including chapters and metadata.
    """
    chapters: List[dict]
    stats: DetectionStats


class CandidateScorer:
    """
    Scores chapter candidates based on match type and context.
    """

    # Base scores by match type
    BASE_SCORES = {
        MatchType.TOC: 0.9,
        MatchType.EXPLICIT: 0.8,
        MatchType.TITLE_CASE: 0.5,
        MatchType.PATTERN: 0.4,
    }

    # Penalty weights
    CODE_BLOCK_PENALTY = 0.5
    NO_BLANK_PENALTY = 0.2
    NO_PROSE_PENALTY = 0.3
    LIST_ITEM_PENALTY = 0.4  # Applied when nearby_similar_lines >= 2

    # Confidence thresholds
    HIGH_THRESHOLD = 0.7
    MEDIUM_THRESHOLD = 0.4

    def score(self, candidate: ChapterCandidate) -> float:
        """
        Calculate confidence score for a candidate.

        Returns:
            Float between 0.0 and 1.0
        """
        score = self.BASE_SCORES.get(candidate.match_type, 0.4)

        # Apply penalties
        if candidate.in_code_block:
            score -= self.CODE_BLOCK_PENALTY

        if not candidate.preceded_by_blank:
            score -= self.NO_BLANK_PENALTY

        if not candidate.followed_by_prose:
            score -= self.NO_PROSE_PENALTY

        if candidate.nearby_similar_lines >= 2:
            score -= self.LIST_ITEM_PENALTY

        # Clamp to valid range
        return max(0.0, min(1.0, score))

    def get_confidence_level(self, score: float) -> str:
        """Convert numeric score to confidence level string"""
        if score >= self.HIGH_THRESHOLD:
            return 'high'
        elif score >= self.MEDIUM_THRESHOLD:
            return 'medium'
        else:
            return 'low'
