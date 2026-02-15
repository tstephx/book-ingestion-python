"""Chapter candidate detection and confidence scoring"""

import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional

from .code_block_detector import CodeBlockDetector


class MatchType(IntEnum):
    """
    Chapter match type hierarchy (higher = more confident).
    """
    PATTERN = 1      # Matches generic pattern like ^\d+\.\s+
    TITLE_CASE = 2   # Title-case heading preceded by blank
    EXPLICIT = 3     # Contains "Chapter", "Part", "Lesson", etc.
    TOC = 4          # Found in TOC and matched in body
    EPUB_ANCHOR = 5  # Resolved EPUB anchor with exact line position


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
        MatchType.EPUB_ANCHOR: 0.95,  # Highest confidence - exact line position from EPUB anchor
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
            re.compile(r'^(CHAPTER\s+\d+)$'),  # Standalone "CHAPTER N" (title on next line)
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

    def extract(self, text: str, toc_titles: List[str] = None,
                is_external_toc: bool = False,
                anchor_map: dict = None,
                enhanced_toc = None) -> List[ChapterCandidate]:
        """
        Extract chapter candidates from text.

        Args:
            text: Full book text
            toc_titles: Optional list of titles from TOC for matching
            is_external_toc: True if TOC titles come from external source (EPUB nav)
            anchor_map: Optional dict mapping full_href -> AnchorLocation for EPUB anchors
            enhanced_toc: Optional EnhancedTOC with split points and anchor map

        Returns:
            List of ChapterCandidate objects
        """
        lines = text.split('\n')
        code_regions = self.code_detector.detect(text)
        code_lines = self._get_code_line_set(code_regions)

        # If we have an enhanced TOC with anchor map, create candidates from anchors first
        anchor_candidates = []
        if enhanced_toc is not None and hasattr(enhanced_toc, 'anchor_map'):
            anchor_candidates = self._extract_from_anchors(
                enhanced_toc, lines, code_lines
            )

        candidates = []
        standalone_num_pattern = re.compile(r'^(\d{1,2})$')

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Skip empty lines
            if not line_stripped:
                continue

            # Skip very short lines (handled by Packt detection below)
            if len(line_stripped) <= 2:
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
                    # For standalone "CHAPTER N", append title from next line
                    if re.match(r'^CHAPTER\s+\d+$', title) and i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line and len(next_line) > 3 and next_line[0].isupper():
                            title = f"{title}: {next_line}"
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
            candidates = self._match_toc_titles(candidates, toc_titles, lines, is_external_toc)

        # Packt-style detection: look for sequential chapter numbers
        # Pattern: standalone "1" then "2" then "3"... with substantial titles
        packt_candidates = self._detect_packt_chapters(lines, code_lines)
        if packt_candidates:
            # Merge with existing candidates
            # For Packt books, the TOC has chapter titles, but so does the body
            # Keep body candidates (they have actual chapter content after them)
            # Only remove TOC-area duplicates (first 1000 lines)
            TOC_CUTOFF = 1000
            packt_titles = {c.title.lower() for c in packt_candidates}

            # Keep candidates that either:
            # 1. Don't match any Packt title, OR
            # 2. Are in the body (after TOC) - these are the actual chapter starts
            candidates = [c for c in candidates
                         if c.title.lower() not in packt_titles
                         or c.line_index >= TOC_CUTOFF]
            candidates.extend(packt_candidates)

        # If we have anchor candidates, they should be the primary source
        if anchor_candidates:
            # EPUB anchors provide exact line positions for chapters
            # Don't mix with TOC-matched candidates which may point to TOC listing
            # Only include pattern-matched candidates that are:
            # 1. Not overlapping with anchor lines
            # 2. Not TOC-matched (those would be from the TOC section, not chapter bodies)
            anchor_lines = {c.line_index for c in anchor_candidates}
            non_overlapping = [c for c in candidates
                               if c.line_index not in anchor_lines
                               and c.match_type != MatchType.TOC]
            return anchor_candidates + non_overlapping

        return candidates

    def _resolve_line_from_fingerprint(self, fingerprint: str, text: str,
                                       hint_offset: int = 0) -> Optional[int]:
        """Find the line index where a fingerprint appears in text.

        Finds ALL occurrences and returns the one closest to hint_offset.
        This avoids matching TOC entries instead of actual chapter headings
        when chapter titles appear multiple times in the text.

        Returns line index or None if fingerprint not found.
        """
        if not fingerprint:
            return None

        # Use first 50 chars for matching (enough to be unique, robust to truncation)
        search_str = fingerprint[:50]

        # Find all occurrences
        positions = []
        start = 0
        while True:
            pos = text.find(search_str, start)
            if pos < 0:
                break
            positions.append(pos)
            start = pos + 1

        # Try shorter match if no results
        if not positions and len(fingerprint) > 30:
            search_str = fingerprint[:30]
            start = 0
            while True:
                pos = text.find(search_str, start)
                if pos < 0:
                    break
                positions.append(pos)
                start = pos + 1

        if not positions:
            return None

        # Pick the occurrence closest to hint_offset
        best_pos = min(positions, key=lambda p: abs(p - hint_offset))

        return text[:best_pos].count('\n')

    def _extract_from_anchors(self, enhanced_toc, lines: List[str],
                              code_lines: set) -> List[ChapterCandidate]:
        """
        Extract chapter candidates from EPUB anchor map.

        Creates high-confidence candidates for each resolved anchor that
        represents a chapter boundary.

        Depth handling:
        - Depth 0: Top-level entries (actual chapters) - always include
        - Depth 1+: Sections - only include if no depth 0 entries exist
        """
        candidates = []
        full_text = '\n'.join(lines)

        # Check if we have top-level (depth 0) entries
        has_chapters = any(sp.depth == 0 for sp in enhanced_toc.split_points)

        # Get chapter-level split points
        for sp in enhanced_toc.split_points:
            # If we have depth 0 entries, only use those as chapter boundaries
            # Otherwise fall back to depth 0 and 1
            if has_chapters:
                if sp.depth != 0:
                    continue
            else:
                # No depth 0 entries - use depth 0 and 1
                if sp.depth > 1:
                    continue

            # Check if this split point has a resolved anchor
            full_href = sp.full_href
            if full_href not in enhanced_toc.anchor_map:
                continue

            location = enhanced_toc.anchor_map[full_href]

            # Re-resolve using fingerprint (indices may be stale after text cleaning)
            resolved_line = self._resolve_line_from_fingerprint(
                location.fingerprint, full_text, hint_offset=location.char_offset
            )

            if resolved_line is not None:
                line_idx = resolved_line
            elif location.line_index < len(lines):
                # Fallback: use original index if still in bounds
                line_idx = location.line_index
            else:
                # Skip this anchor - can't resolve
                continue

            # Create high-confidence candidate from anchor
            candidate = ChapterCandidate(
                line_index=line_idx,
                title=sp.title,
                match_type=MatchType.EPUB_ANCHOR,
                preceded_by_blank=self._is_preceded_by_blank(lines, line_idx),
                followed_by_prose=self._is_followed_by_prose(lines, line_idx),
                nearby_similar_lines=0,  # N/A for anchors
                in_code_block=line_idx in code_lines,
            )
            candidates.append(candidate)

        return candidates

    def _detect_packt_chapters(self, lines: List[str], code_lines: set) -> List[ChapterCandidate]:
        """
        Detect Packt cookbook-style chapters with sequential numbering.

        Pattern: standalone number on one line, title on next line.
        Only returns matches if we find a sequential run (1, 2, 3...).
        Uses TOC occurrences (first ~1000 lines) to build the chain.
        """
        standalone_num = re.compile(r'^(\d{1,2})$')

        # Collect all number -> title pairs from TOC area only
        # (avoid matching page headers in body which repeat chapter titles)
        TOC_LIMIT = 1000
        pairs = []
        for i, line in enumerate(lines[:TOC_LIMIT]):
            stripped = line.strip()
            num_match = standalone_num.match(stripped)
            if num_match and i + 1 < len(lines):
                num = int(num_match.group(1))
                next_line = lines[i + 1].strip()
                # Title criteria: substantial, starts with capital
                # Must look like a complete chapter title, not a fragment
                if (next_line and len(next_line) > 20 and
                    next_line[0].isupper() and
                    # Not a subsection header (common Packt subsection patterns)
                    not re.match(r'^(Technical requirements|Getting ready|How to do|There.s more|Hands-on exercises|Exercise \d|Understanding \w+$|Introduction to [\w-]+.s|Common data|Working with metadata|Best practices for|Hyperparameter tuning|Encoding categorical|Scaling techniques|Cleaning and|Handling missing|Feature engineering$|Practical exercises|Pipelines and|Transformers and|What is a)', next_line, re.IGNORECASE) and
                    # Not a title fragment (ending with preposition/article/conjunction)
                    not re.search(r"\b(the|and|of|to|in|for|with|a|an|or)\s*$", next_line, re.IGNORECASE)):
                    pairs.append((i, num, next_line))

        if not pairs:
            return []

        # Find sequences starting from 1
        # Group candidates by their chapter number
        by_num = {}
        for line_idx, num, title in pairs:
            if num not in by_num:
                by_num[num] = []
            by_num[num].append((line_idx, title))

        # Look for the best chain starting from 1
        if 1 not in by_num:
            return []

        # For each "1" candidate, try to build a sequence
        best_chain = []
        for start_idx, start_title in by_num.get(1, []):
            chain = [(start_idx, 1, start_title)]
            current_idx = start_idx

            for next_num in range(2, 20):  # Look for chapters 2-19
                if next_num not in by_num:
                    break
                # Find the first occurrence of next_num after current position
                found = False
                for idx, title in by_num[next_num]:
                    if idx > current_idx:
                        chain.append((idx, next_num, title))
                        current_idx = idx
                        found = True
                        break
                if not found:
                    break

            if len(chain) > len(best_chain):
                best_chain = chain

        # Need at least 3 sequential chapters to be confident
        if len(best_chain) < 3:
            return []

        # Convert to candidates
        candidates = []
        for line_idx, num, title in best_chain:
            # Remove trailing page number if present
            clean_title = re.sub(r'\s+\d+\s*$', '', title)
            candidates.append(ChapterCandidate(
                line_index=line_idx,
                title=clean_title,
                match_type=MatchType.EXPLICIT,
                preceded_by_blank=self._is_preceded_by_blank(lines, line_idx),
                followed_by_prose=self._is_followed_by_prose(lines, line_idx + 1),
                nearby_similar_lines=0,
                in_code_block=line_idx in code_lines,
            ))

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

    def _normalize_for_matching(self, text: str) -> str:
        """Normalize text for fuzzy TOC matching.

        Removes punctuation and normalizes whitespace to enable matching
        across different formatting (e.g., "Chapter 1 - Title" vs "Chapter 1  Title").
        """
        import re
        # Replace dashes, colons, and multiple spaces with single space
        normalized = re.sub(r'[\-–—:]+', ' ', text)
        # Collapse multiple whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized.lower().strip()

    def _match_toc_titles(self, candidates: List[ChapterCandidate],
                         toc_titles: List[str], lines: List[str],
                         is_external_toc: bool = False) -> List[ChapterCandidate]:
        """Upgrade candidates that match TOC titles.

        Only upgrades the first occurrence of each TOC title.
        For PDFs (internal TOC), skips first 1000 lines to avoid matching the TOC itself.
        For external TOC (e.g., EPUB navigation), matches from the beginning.

        Args:
            candidates: List of chapter candidates
            toc_titles: List of chapter titles from TOC
            lines: Full text split into lines
            is_external_toc: True if TOC titles come from external source (EPUB nav, etc.)
        """
        # Normalize TOC titles for fuzzy matching
        toc_normalized = [(self._normalize_for_matching(t), t) for t in toc_titles]
        matched_titles = set()  # Track which TOC titles we've matched

        # For PDFs with in-text TOC, skip the TOC area to avoid matching TOC entries
        # For external TOC (EPUB), match from the start of the document
        TOC_CUTOFF = 0 if is_external_toc else 1000

        # Sort by line index to process in document order
        sorted_candidates = sorted(candidates, key=lambda c: c.line_index)

        for candidate in sorted_candidates:
            # Skip TOC area for PDFs
            if candidate.line_index < TOC_CUTOFF:
                continue

            candidate_normalized = self._normalize_for_matching(candidate.title)

            for toc_norm, toc_original in toc_normalized:
                # Skip already matched titles
                if toc_original in matched_titles:
                    continue

                # Check for significant overlap (fuzzy matching)
                if (toc_norm in candidate_normalized or
                    candidate_normalized in toc_norm or
                    self._titles_match(candidate_normalized, toc_norm)):
                    candidate.match_type = MatchType.TOC
                    matched_titles.add(toc_original)
                    break

        return candidates

    def _titles_match(self, title1: str, title2: str) -> bool:
        """Check if two normalized titles are essentially the same.

        Requires significant overlap to avoid false positives like
        "how to test terraform" matching "how to create infrastructure".
        """
        # Exact match
        if title1 == title2:
            return True

        words1 = title1.split()
        words2 = title2.split()

        # Skip very short titles (need at least 3 words for meaningful match)
        if len(words1) < 3 or len(words2) < 3:
            return False

        # For partial matches, require at least 3 consecutive words to match
        # This avoids false positives from common prefixes like "How to"
        min_match = 3

        # Check if first min_match words match
        if words1[:min_match] == words2[:min_match]:
            return True

        # Also check if one is a prefix of the other (for truncated titles)
        # Require at least 60% of the shorter title's words to match
        shorter = words1 if len(words1) <= len(words2) else words2
        longer = words2 if len(words1) <= len(words2) else words1

        matching = 0
        for i, word in enumerate(shorter):
            if i < len(longer) and shorter[i] == longer[i]:
                matching += 1
            else:
                break  # Stop at first mismatch for prefix matching

        # Require at least 60% match and at least 3 words
        required = max(min_match, int(len(shorter) * 0.6))
        return matching >= required


class AnchorMerger:
    """
    Selects high-confidence anchors and absorbs low-confidence candidates.
    """

    HIGH_THRESHOLD = 0.7
    MEDIUM_THRESHOLD = 0.4
    LOW_THRESHOLD = 0.3  # For fallback promotion
    MIN_ANCHORS = 3  # Absolute minimum chapters
    WORDS_PER_CHAPTER = 8000  # Expect roughly 1 chapter per 8K words

    def _normalize_title(self, title: str) -> str:
        """Normalize title for deduplication comparison."""
        import re
        # Remove chapter number prefix but keep the rest of the title
        # Patterns like "CHAPTER 1: Title" -> "Title", "Chapter 1" -> ""
        normalized = re.sub(r'^(CHAPTER\s+\d+[:\s]*|Chapter\s+\d+[:\s]*)', '', title, flags=re.IGNORECASE)
        # Lowercase and strip
        return normalized.lower().strip()

    def _is_duplicate_title(self, candidate: ChapterCandidate, existing: List[ChapterCandidate]) -> bool:
        """Check if candidate has same title as an existing anchor.

        Only considers titles as duplicates if they have substantial content
        overlap, not just simple "Chapter N" variations.
        """
        candidate_norm = self._normalize_title(candidate.title)

        # If the normalized title is empty or very short (just "chapter 1" type),
        # don't consider it a duplicate based on title alone
        if len(candidate_norm) < 5:
            return False

        for anchor in existing:
            anchor_norm = self._normalize_title(anchor.title)
            if len(anchor_norm) < 5:
                continue
            # Check for significant overlap (one contains the other or very similar)
            if candidate_norm in anchor_norm or anchor_norm in candidate_norm:
                return True
            # Check for exact match after normalization
            if candidate_norm == anchor_norm:
                return True
        return False

    def select_anchors(self, candidates: List[ChapterCandidate],
                       word_count: int = 0) -> List[ChapterCandidate]:
        """
        Select anchor candidates based on confidence.

        High-confidence (>= 0.7) candidates become anchors.
        If too few anchors, promote best medium-confidence candidates.
        Uses word count to estimate expected chapters.
        Prefers candidates spread throughout the document (skips TOC area).
        Deduplicates by title to avoid running headers being selected.
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

        # Select high-confidence anchors, deduplicating by title
        anchors = []
        for c in sorted_candidates:
            if c.confidence >= self.HIGH_THRESHOLD:
                if not self._is_duplicate_title(c, anchors):
                    anchors.append(c)

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

            # Pick candidates that are well-spaced and not duplicates
            for candidate in medium:
                if len(anchors) >= expected_chapters:
                    break
                # Skip if too close to an existing anchor
                if any(abs(candidate.line_index - a.line_index) < min_spacing for a in anchors):
                    continue
                # Skip if duplicate title
                if self._is_duplicate_title(candidate, anchors):
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
                if self._is_duplicate_title(candidate, anchors):
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
