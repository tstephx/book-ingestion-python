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
