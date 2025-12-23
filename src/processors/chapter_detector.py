"""Chapter candidate detection and confidence scoring"""

import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional

from src.processors.code_block_detector import CodeBlockDetector


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


class CandidateExtractor:
    """
    Extracts chapter candidates from text with context for scoring.
    """

    def __init__(self):
        self.code_detector = CodeBlockDetector()

        # Explicit chapter patterns (highest priority after TOC)
        self.explicit_patterns = [
            re.compile(r'^(Chapter\s+\d+[:\s].*)$', re.IGNORECASE),
            re.compile(r'^(CHAPTER\s+\d+[:\s].*)$'),
            re.compile(r'^(Part\s+\d+[:\s].*)$', re.IGNORECASE),
            re.compile(r'^(Lesson\s+\d+[:\s].*)$', re.IGNORECASE),
            re.compile(r'^(Module\s+\d+[:\s].*)$', re.IGNORECASE),
            re.compile(r'^(Unit\s+\d+[:\s].*)$', re.IGNORECASE),
            re.compile(r'^(Project\s+\d+[A-Z]?[:\s].*)$', re.IGNORECASE),
        ]

        # Generic patterns (lower priority)
        self.generic_patterns = [
            re.compile(r'^(\d+)\.\s+([A-Z].{5,})$'),  # "1. Title Here"
            re.compile(r'^(\d+)\s+([A-Z].{5,})$'),    # "1 Title Here"
        ]

    def extract(self, text: str, toc_titles: List[str] = None) -> List[ChapterCandidate]:
        """
        Extract chapter candidates from text.

        Args:
            text: Full book text
            toc_titles: Optional list of titles from TOC for matching

        Returns:
            List of ChapterCandidate objects
        """
        lines = text.split('\n')
        code_regions = self.code_detector.detect(text)
        code_lines = self._get_code_line_set(code_regions)

        candidates = []
        standalone_num_pattern = re.compile(r'^(\d{1,2})$')

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Skip empty lines
            if not line_stripped:
                continue

            # Check for Packt-style standalone chapter number (e.g., "1" on its own line)
            # followed by a title on the next line
            if len(line_stripped) <= 2:
                num_match = standalone_num_pattern.match(line_stripped)
                if num_match and i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    # Next line should be a substantial title
                    if (next_line and len(next_line) > 10 and
                        next_line[0].isupper() and
                        not re.match(r'^(Technical|Getting|How to)', next_line)):
                        # Remove trailing page number if present
                        title = re.sub(r'\s+\d+\s*$', '', next_line)
                        if len(title) > 5:
                            candidate = ChapterCandidate(
                                line_index=i,
                                title=title,
                                match_type=MatchType.EXPLICIT,  # High priority
                                preceded_by_blank=self._is_preceded_by_blank(lines, i),
                                followed_by_prose=self._is_followed_by_prose(lines, i + 1),
                                nearby_similar_lines=0,  # Standalone numbers aren't lists
                                in_code_block=i in code_lines,
                            )
                            candidates.append(candidate)
                continue

            # Skip very short or very long lines for other patterns
            if len(line_stripped) < 3 or len(line_stripped) > 100:
                continue

            # Try to match patterns
            match_type = None
            title = None

            # Check explicit patterns first
            for pattern in self.explicit_patterns:
                match = pattern.match(line_stripped)
                if match:
                    title = match.group(1)
                    match_type = MatchType.EXPLICIT
                    break

            # Check generic patterns if no explicit match
            if not match_type:
                for pattern in self.generic_patterns:
                    match = pattern.match(line_stripped)
                    if match:
                        title = line_stripped
                        match_type = MatchType.PATTERN
                        break

            # Check title case (fallback)
            if not match_type and self._is_title_case(line_stripped):
                title = line_stripped
                match_type = MatchType.TITLE_CASE

            if match_type and title:
                candidate = ChapterCandidate(
                    line_index=i,
                    title=title,
                    match_type=match_type,
                    preceded_by_blank=self._is_preceded_by_blank(lines, i),
                    followed_by_prose=self._is_followed_by_prose(lines, i),
                    nearby_similar_lines=self._count_nearby_similar(lines, i),
                    in_code_block=i in code_lines,
                )
                candidates.append(candidate)

        # Check against TOC if provided
        if toc_titles:
            candidates = self._match_toc_titles(candidates, toc_titles, lines)

        return candidates

    def _get_code_line_set(self, regions: List[tuple]) -> set:
        """Convert code regions to set of line indices"""
        code_lines = set()
        for start, end in regions:
            code_lines.update(range(start, end + 1))
        return code_lines

    def _is_preceded_by_blank(self, lines: List[str], index: int) -> bool:
        """Check if line is preceded by a blank line"""
        if index == 0:
            return True  # First line counts as preceded by blank
        return lines[index - 1].strip() == ''

    def _is_followed_by_prose(self, lines: List[str], index: int, check_lines: int = 50) -> bool:
        """Check if line is followed by substantial prose content"""
        end = min(index + check_lines, len(lines))
        content = ' '.join(lines[index + 1:end])
        words = content.split()

        # Need at least 10 words of content
        if len(words) < 10:
            return False

        # Check for sentence-like structure (periods or multiple sentences)
        # Even short content can be considered prose if it has proper structure
        sentences = re.split(r'[.!?]', content)
        if len(sentences) >= 2:
            return True

        # For longer content, require more structure
        if len(words) >= 100 and len(sentences) >= 3:
            return True

        # Medium content with some words is considered prose
        return len(words) >= 10

    def _count_nearby_similar(self, lines: List[str], index: int, window: int = 5) -> int:
        """Count lines with similar patterns nearby (list detection)"""
        current = lines[index].strip()

        # Extract the pattern type
        numbered_match = re.match(r'^(\d+)[.\s]', current)
        if not numbered_match:
            return 0

        count = 0
        start = max(0, index - window)
        end = min(len(lines), index + window + 1)

        for i in range(start, end):
            if i == index:
                continue
            other = lines[i].strip()
            if re.match(r'^\d+[.\s]', other):
                count += 1

        return count

    def _is_title_case(self, line: str) -> bool:
        """Check if line is in title case (potential chapter title)"""
        words = line.split()
        if len(words) < 2 or len(words) > 10:
            return False

        # Skip if contains common non-title patterns
        if re.search(r'[=<>{}()\[\]]', line):
            return False

        # Check that most significant words are capitalized
        significant = [w for w in words if len(w) > 3]
        if not significant:
            return False

        capitalized = sum(1 for w in significant if w[0].isupper())
        return capitalized / len(significant) >= 0.7

    def _match_toc_titles(self, candidates: List[ChapterCandidate],
                         toc_titles: List[str], lines: List[str]) -> List[ChapterCandidate]:
        """Upgrade candidates that match TOC titles"""
        toc_lower = [t.lower() for t in toc_titles]

        for candidate in candidates:
            title_lower = candidate.title.lower()
            for toc_title in toc_lower:
                # Check for significant overlap
                if toc_title in title_lower or title_lower in toc_title:
                    candidate.match_type = MatchType.TOC
                    break

        return candidates


class AnchorMerger:
    """
    Selects high-confidence anchors and absorbs low-confidence candidates.
    """

    HIGH_THRESHOLD = 0.7
    MEDIUM_THRESHOLD = 0.4
    LOW_THRESHOLD = 0.3  # For fallback promotion
    MIN_ANCHORS = 3  # Absolute minimum chapters
    WORDS_PER_CHAPTER = 8000  # Expect roughly 1 chapter per 8K words

    def select_anchors(self, candidates: List[ChapterCandidate],
                       word_count: int = 0) -> List[ChapterCandidate]:
        """
        Select anchor candidates based on confidence.

        High-confidence (>= 0.7) candidates become anchors.
        If too few anchors, promote best medium-confidence candidates.
        Uses word count to estimate expected chapters.
        Prefers candidates spread throughout the document (skips TOC area).
        """
        # Sort by line index for sequential processing
        sorted_candidates = sorted(candidates, key=lambda c: c.line_index)
        if not sorted_candidates:
            return []

        max_line = max(c.line_index for c in sorted_candidates)

        # Calculate expected chapters based on word count
        if word_count > 0:
            expected_chapters = max(self.MIN_ANCHORS, word_count // self.WORDS_PER_CHAPTER)
        else:
            expected_chapters = self.MIN_ANCHORS

        # Select high-confidence anchors
        anchors = [c for c in sorted_candidates if c.confidence >= self.HIGH_THRESHOLD]

        # If not enough anchors, promote medium-confidence with spacing preference
        if len(anchors) < expected_chapters:
            medium = [c for c in sorted_candidates
                     if self.MEDIUM_THRESHOLD <= c.confidence < self.HIGH_THRESHOLD]

            # Skip first 10% of document (likely TOC/front matter)
            skip_lines = max_line // 10
            medium_after_front = [c for c in medium if c.line_index > skip_lines]
            medium_front = [c for c in medium if c.line_index <= skip_lines]

            # Prefer candidates from body of document
            if len(medium_after_front) >= expected_chapters:
                medium = medium_after_front
            else:
                # Use both but prioritize body content
                medium = medium_after_front + medium_front

            # Sort by line index to pick evenly spaced candidates
            medium.sort(key=lambda c: c.line_index)

            # Calculate ideal spacing for chapters
            ideal_spacing = max_line // expected_chapters if expected_chapters > 0 else max_line
            min_spacing = max(ideal_spacing // 3, 50)  # At least 50 lines or 1/3 ideal

            # Pick candidates that are well-spaced
            for candidate in medium:
                if len(anchors) >= expected_chapters:
                    break
                # Skip if too close to an existing anchor
                if any(abs(candidate.line_index - a.line_index) < min_spacing for a in anchors):
                    continue
                anchors.append(candidate)

            anchors.sort(key=lambda c: c.line_index)

        # If still not enough, try low-confidence candidates with good context
        if len(anchors) < self.MIN_ANCHORS:
            low = [c for c in sorted_candidates
                   if self.LOW_THRESHOLD <= c.confidence < self.MEDIUM_THRESHOLD
                   and c.preceded_by_blank  # Must have blank line before
                   and c.followed_by_prose]  # Must have content after
            low.sort(key=lambda c: c.confidence, reverse=True)

            for candidate in low:
                if len(anchors) >= self.MIN_ANCHORS:
                    break
                if any(abs(candidate.line_index - a.line_index) < 20 for a in anchors):
                    continue
                anchors.append(candidate)

            anchors.sort(key=lambda c: c.line_index)

        return anchors

    def merge(self, candidates: List[ChapterCandidate], word_count: int = 0) -> tuple:
        """
        Perform full anchor selection and merge.

        Args:
            candidates: List of chapter candidates
            word_count: Total word count for estimating expected chapters

        Returns:
            Tuple of (anchors, DetectionStats)
        """
        anchors = self.select_anchors(candidates, word_count)
        anchor_indices = {a.line_index for a in anchors}

        # Count merges (candidates not selected as anchors)
        merges = len(candidates) - len(anchors)

        # Determine overall confidence
        if not anchors:
            confidence = 'low'
        elif all(a.confidence >= self.HIGH_THRESHOLD for a in anchors):
            confidence = 'high'
        elif any(a.confidence >= self.HIGH_THRESHOLD for a in anchors):
            confidence = 'medium'
        else:
            confidence = 'low'

        # Determine method based on anchor types
        toc_count = sum(1 for a in anchors if a.match_type == MatchType.TOC)
        explicit_count = sum(1 for a in anchors if a.match_type == MatchType.EXPLICIT)

        if toc_count > len(anchors) / 2:
            method = 'toc'
        elif explicit_count > 0:
            method = 'pattern'
        else:
            method = 'fallback'

        stats = DetectionStats(
            method=method,
            confidence=confidence,
            candidates_found=len(candidates),
            candidates_rejected=merges,
            anchors_used=len(anchors),
            merges_performed=merges,
        )

        return anchors, stats
