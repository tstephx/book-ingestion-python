"""Chapter splitting logic with improved detection"""

import logging
import re
from statistics import median
from typing import List, Dict

logger = logging.getLogger(__name__)

from .code_block_detector import CodeBlockDetector
from .chapter_detector import (
    ChapterCandidate,
    CandidateExtractor,
    CandidateScorer,
    AnchorMerger,
    DetectionStats,
    MatchType,
)


class ChapterSplitter:
    _QG_MIN_CHAPTERS = 7
    _QG_MAX_CHAPTER_WORDS = 20_000
    _QG_MAX_TO_MEDIAN_RATIO = 4.0

    def __init__(self, config):
        self.config = config.chapter_detection
        self.patterns = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.config['patterns']]

        # New pipeline components
        self.code_detector = CodeBlockDetector()
        self.extractor = CandidateExtractor()
        self.scorer = CandidateScorer()
        self.merger = AnchorMerger()

    def split(self, text: str, book_id: str, external_toc_titles: List[str] = None,
              enhanced_toc=None) -> List[Dict]:
        """Backwards-compatible API - returns list of chapter dicts."""
        result = self.split_with_stats(text, book_id, external_toc_titles, enhanced_toc)
        return result['chapters']

    def split_with_stats(self, text: str, book_id: str, external_toc_titles: List[str] = None,
                         enhanced_toc=None) -> Dict:
        """Split text into chapters with detection statistics.

        Args:
            text: Full text content to split
            book_id: Unique identifier for the book
            external_toc_titles: Optional list of chapter titles from external source
                                 (e.g., EPUB navigation). If provided and has 3+ titles,
                                 these are used instead of text-based TOC detection.
            enhanced_toc: Optional EnhancedTOC from enhanced EPUB parser with
                         split points and anchor map for precise chapter detection.
        """
        # Calculate word count for expected chapters estimation
        word_count = len(text.split())

        # Stage 1: Detect code blocks
        code_regions = self.code_detector.detect(text)

        # Stage 2: Try TOC-based detection
        # Priority: enhanced_toc > external_toc_titles > text-based extraction
        is_external_toc = False
        if enhanced_toc is not None and hasattr(enhanced_toc, 'titles'):
            # Use titles from enhanced TOC
            toc_titles = enhanced_toc.titles
            is_external_toc = True
        elif external_toc_titles and len(external_toc_titles) >= 3:
            toc_titles = external_toc_titles
            is_external_toc = True
        else:
            toc_titles = self._extract_toc_titles(text)

        # Stage 3: Extract candidates
        # Pass enhanced_toc for anchor-based extraction if available
        candidates = self.extractor.extract(
            text, toc_titles, is_external_toc, enhanced_toc=enhanced_toc
        )

        # Stage 4: Score candidates
        for candidate in candidates:
            candidate.confidence = self.scorer.score(candidate)

        # Stage 5: Select anchors and merge (pass word count for better estimation)
        anchors, stats = self.merger.merge(candidates, word_count)
        stats.code_blocks_detected = len(code_regions)

        # Update stats if EPUB anchors were used
        epub_anchor_count = sum(
            1 for a in anchors if a.match_type == MatchType.EPUB_ANCHOR
        )
        if epub_anchor_count > 0:
            stats.method = 'epub_anchor'
            stats.confidence = 'high'
            stats.anchors_used = epub_anchor_count

        # Build chapters from anchors
        if anchors:
            chapters = self._build_chapters_from_anchors(text, book_id, anchors)
        else:
            chapters = self._fixed_size_split(text, book_id)
            stats.method = 'fallback'
            stats.confidence = 'low'

        # Validate chapter sizes
        chapters = self._validate_chapter_sizes(chapters, book_id)

        if len(chapters) == 0:
            chapters = self._fixed_size_split(text, book_id)
            stats.method = 'fallback'
            stats.confidence = 'low'

        # Post-split quality gate: re-split oversized chapters
        chapters = self._quality_resplit(chapters, book_id)

        return {'chapters': chapters, 'stats': stats}

    def _extract_toc_titles(self, text: str) -> List[str]:
        """Extract chapter titles from table of contents."""
        lines = text.split('\n')

        # Patterns for different TOC formats
        toc_patterns = [
            # No Starch Press style: "Chapter N: Title. . . . ." or "Chapter N: Title...page"
            # The dots can be ". . ." (spaced) or "..." (consecutive)
            (re.compile(r'^Chapter\s+(\d+):\s+(.+?)(?:\s+\.\s|\.\s*\.|\s*\.{2,})'), 2),
            # Packt style: "Chapter X, Title, description..."
            (re.compile(r'^Chapter\s+(\d+),\s+([^,]+)', re.IGNORECASE), 2),
            # Apress style: "Chapter X: Title...page" or "Chapter X: Title"
            (re.compile(r'^Chapter\s+(\d+):\s+([^\.]+?)(?:\.{2,}|\s*$)', re.IGNORECASE), 2),
            # Leanpub/self-published style: "Chapter N - Title . . . ." or "Chapter N - Title"
            (re.compile(r'^Chapter\s+(\d+)\s*-\s*(.+?)(?:\s+\.|\s*\.{2,}|\s*$)', re.IGNORECASE), 2),
            # O'Reilly style: "N. Title. . . . . ." (with spaced dots) or "N. Title..."
            (re.compile(r'^(\d{1,2})\.\s+(.+?)(?:\s+\.|\s*\.{2,})'), 2),
            # Project style: "Project XA: Title"
            (re.compile(r'^Project\s+(\d+[A-Z]):\s+(.+)', re.IGNORECASE), 2),
            # DevOps Handbook style: "NN Title" (zero-padded chapter number)
            (re.compile(r'^(\d{2})\s+([A-Z][^0-9]{15,})$'), 2),
        ]

        # Try each pattern in order - use first pattern with enough matches
        # This prioritizes more specific patterns (listed first) over greedy ones
        chapter_titles = []
        for toc_pattern, title_group in toc_patterns:
            titles_for_pattern = []
            for line in lines[:600]:  # Extended for longer TOCs (some have 20+ chapters)
                match = toc_pattern.match(line.strip())
                if match:
                    # Strip whitespace from title
                    title = match.group(title_group).strip()
                    # Remove any trailing punctuation or whitespace
                    title = title.rstrip(' \t\n\r.')
                    # Skip titles that start with quotes (likely from testimonials/index)
                    # Check both ASCII and Unicode curly quotes
                    if len(title) >= 3 and not title[0] in '""\u201C\u201D':
                        titles_for_pattern.append(title)

            # Use first pattern that finds at least 3 chapters
            if len(titles_for_pattern) >= 3:
                chapter_titles = titles_for_pattern
                break

        # Packt cookbook style: standalone number line followed by title line
        # Example:
        #   1
        #   Common Conventions and API Elements of scikit-learn 1
        # Must find sequential numbers (1, 2, 3...) to avoid matching subsections
        if len(chapter_titles) < 3:
            packt_pairs = []
            standalone_num = re.compile(r'^(\d{1,2})$')

            # Patterns for subsection headers to exclude
            subsection_patterns = re.compile(
                r'^(Technical requirements|Getting ready|How to do it|'
                r'How it works|There.s more|Tere.s more|Hands-on exercises|'
                r'Exercise \d|Understanding \w+$|Introduction to [\w\'\-]+.s|'
                r'Common data|Common attributes|Working with metadata|Best practices for|'
                r'Hyperparameter tuning|Encoding categorical|Scaling techniques|'
                r'Cleaning and|Handling missing|Feature engineering$|'
                r'Practical exercises|Pipelines and workﬂow|Transformers and the|'
                r'Handling custom|What is a|Visualizing|Table of Contents|'
                r'Te impact|The impact)',
                re.IGNORECASE
            )

            for i, line in enumerate(lines[:1000]):
                stripped = line.strip()
                num_match = standalone_num.match(stripped)
                if num_match and i + 1 < len(lines):
                    num = int(num_match.group(1))
                    next_line = lines[i + 1].strip()
                    # Next line should be the title (starts with capital, has length)
                    if (next_line and len(next_line) > 20 and next_line[0].isupper()
                        and not subsection_patterns.match(next_line)):
                        # Remove trailing page number if present
                        title = re.sub(r'\s+\d+\s*$', '', next_line)
                        if len(title) > 5:
                            packt_pairs.append((num, title))

            # Find sequential chain starting from 1
            if packt_pairs:
                # Group by chapter number, keep first occurrence
                by_num = {}
                for num, title in packt_pairs:
                    if num not in by_num:
                        by_num[num] = title

                # Build sequential chain
                packt_titles = []
                expected = 1
                while expected in by_num:
                    packt_titles.append(by_num[expected])
                    expected += 1

                if len(packt_titles) >= 3:
                    chapter_titles = packt_titles

        # Addison-Wesley style: "CHAPTER N" on one line, title on next line
        # Example:
        #   CHAPTER 1
        #   What Is Software Architecture?  1
        if len(chapter_titles) < 3:
            aw_pattern = re.compile(r'^CHAPTER\s+(\d+)\s*$', re.IGNORECASE)
            aw_pairs = []
            for i, line in enumerate(lines[:400]):
                match = aw_pattern.match(line.strip())
                if match and i + 1 < len(lines):
                    num = int(match.group(1))
                    next_line = lines[i + 1].strip()
                    # Title should be substantial and start with capital
                    if next_line and len(next_line) > 10 and next_line[0].isupper():
                        # Remove trailing page number
                        title = re.sub(r'\s+\d+\s*$', '', next_line)
                        if len(title) > 5:
                            aw_pairs.append((num, title))

            if aw_pairs:
                by_num = {}
                for num, title in aw_pairs:
                    if num not in by_num:
                        by_num[num] = title
                aw_titles = []
                expected = 1
                while expected in by_num:
                    aw_titles.append(by_num[expected])
                    expected += 1
                if len(aw_titles) >= 3:
                    chapter_titles = aw_titles

        # Manning style: standalone number, "I" marker, title on third line
        # Example:
        #   1
        #   I
        #   Improving your Python with practice
        if len(chapter_titles) < 3:
            manning_pairs = []
            standalone_num = re.compile(r'^(\d{1,2})$')
            for i, line in enumerate(lines[:400]):
                stripped = line.strip()
                num_match = standalone_num.match(stripped)
                if num_match and i + 2 < len(lines):
                    num = int(num_match.group(1))
                    marker = lines[i + 1].strip()
                    title_line = lines[i + 2].strip()
                    # Check for "I" marker (Manning chapter marker)
                    # Titles can be short (e.g., "Files", "Strings")
                    if marker == 'I' and title_line and len(title_line) >= 4:
                        # Remove trailing page number
                        title = re.sub(r'\s+\d+\s*$', '', title_line)
                        if len(title) >= 4 and title[0].isupper():
                            manning_pairs.append((num, title))

            if manning_pairs:
                by_num = {}
                for num, title in manning_pairs:
                    if num not in by_num:
                        by_num[num] = title
                manning_titles = []
                expected = 1
                while expected in by_num:
                    manning_titles.append(by_num[expected])
                    expected += 1
                if len(manning_titles) >= 3:
                    chapter_titles = manning_titles

        return chapter_titles

    def _build_chapters_from_anchors(self, text: str, book_id: str,
                                     anchors: List[ChapterCandidate]) -> List[Dict]:
        """Build chapter objects from anchor candidates."""
        lines = text.split('\n')
        chapters = []

        for idx, anchor in enumerate(anchors):
            start = anchor.line_index + 1
            end = anchors[idx + 1].line_index if idx + 1 < len(anchors) else len(lines)

            content = '\n'.join(lines[start:end]).strip()
            word_count = len(content.split())

            chapters.append({
                'id': f"{book_id}-ch{len(chapters) + 1}",
                'book_id': book_id,
                'chapter_number': len(chapters) + 1,
                'title': anchor.title,
                'content': content,
                'word_count': word_count,
                'file_path': ''
            })

        return chapters

    def _validate_chapter_sizes(self, chapters: List[Dict], book_id: str) -> List[Dict]:
        """Validate and filter chapters based on size constraints."""
        if not chapters:
            return []

        # First pass: filter out chapters that are too long
        size_filtered = []
        for chapter in chapters:
            word_count = chapter['word_count']
            # Skip very long chapters (might be bad detection)
            if word_count <= self.config['max_words_per_chapter']:
                size_filtered.append(chapter)

        if not size_filtered:
            return []

        # Second pass: filter out short chapters ONLY if we have enough that meet minimum
        chapters_meeting_min = [ch for ch in size_filtered
                               if ch['word_count'] >= self.config['min_words_per_chapter']]

        # If we have at least 2 chapters meeting minimum, use only those
        if len(chapters_meeting_min) >= 2:
            valid_chapters = chapters_meeting_min
        # If only 1 or 0 chapters meet minimum, keep all chapters (even short ones)
        else:
            valid_chapters = size_filtered

        # Renumber after filtering
        for i, chapter in enumerate(valid_chapters):
            chapter['chapter_number'] = i + 1
            chapter['id'] = f"{book_id}-ch{i + 1}"

        return valid_chapters

    def fallback_split(self, text: str, book_id: str) -> List[Dict]:
        """Split text using fixed-size chunks with quality gate.

        Public API for callers that need to bypass anchor/TOC detection
        (e.g. force_fallback retry path). Produces 2500-word chunks, then
        runs _quality_resplit() to enforce min chapters, max words, and
        lopsided ratio thresholds.
        """
        chapters = self._fixed_size_split(text, book_id)
        return self._quality_resplit(chapters, book_id)

    def _fixed_size_split(self, text, book_id):
        """Split into fixed-size chunks when no chapters detected."""
        words = text.split()
        chunk_size = 2500
        chapters = []

        for i in range(0, len(words), chunk_size):
            content = ' '.join(words[i:i + chunk_size])

            chapters.append({
                'id': f"{book_id}-ch{len(chapters) + 1}",
                'book_id': book_id,
                'chapter_number': len(chapters) + 1,
                'title': f"Section {len(chapters) + 1}",
                'content': content,
                'word_count': len(content.split()),
                'file_path': ''
            })

        return chapters

    def _quality_resplit(self, chapters: List[Dict], book_id: str) -> List[Dict]:
        """Check quality thresholds and re-split oversized chapters.

        Runs up to 3 rounds of checks until stable:
        1. Any chapter > _QG_MAX_CHAPTER_WORDS -> re-split
        2. Total chapters < _QG_MIN_CHAPTERS -> re-split largest to increase count
        3. Max/median word ratio > _QG_MAX_TO_MEDIAN_RATIO -> re-split outliers
        """
        if not chapters or len(chapters) < 1:
            return chapters

        for _round in range(3):
            changed = False

            # Check 1: Absolute cap - any chapter over max words
            new_chapters = []
            oversized_count = 0
            for ch in chapters:
                if ch['word_count'] > self._QG_MAX_CHAPTER_WORDS:
                    parts = self._resplit_chapter(ch, book_id, self._QG_MAX_CHAPTER_WORDS)
                    new_chapters.extend(parts)
                    changed = True
                    oversized_count += 1
                else:
                    new_chapters.append(ch)
            if oversized_count:
                logger.info("Quality gate: re-split %d oversized chapter(s) for book %s", oversized_count, book_id)
            chapters = new_chapters

            # Check 2: Too few chapters - re-split largest to increase count
            if len(chapters) < self._QG_MIN_CHAPTERS:
                target_max = self._QG_MAX_CHAPTER_WORDS // 2
                # Sort indices by word count descending to split largest first
                indexed = list(enumerate(chapters))
                indexed.sort(key=lambda x: x[1]['word_count'], reverse=True)
                to_split = set()
                projected_count = len(chapters)
                for orig_idx, ch in indexed:
                    if projected_count >= self._QG_MIN_CHAPTERS:
                        break
                    if ch['word_count'] > target_max:
                        to_split.add(orig_idx)
                        # Estimate how many parts this will produce
                        est_parts = max(2, ch['word_count'] // target_max)
                        projected_count += est_parts - 1

                if to_split:
                    logger.info("Quality gate: too few chapters (%d < %d), re-splitting %d largest for book %s",
                                len(chapters), self._QG_MIN_CHAPTERS, len(to_split), book_id)
                    new_chapters = []
                    for i, ch in enumerate(chapters):
                        if i in to_split:
                            parts = self._resplit_chapter(ch, book_id, target_max)
                            new_chapters.extend(parts)
                            changed = True
                        else:
                            new_chapters.append(ch)
                    chapters = new_chapters

            # Check 3: Lopsided ratio - max/median too high
            if len(chapters) >= 2:
                word_counts = [ch['word_count'] for ch in chapters if ch['word_count'] > 0]
                if word_counts:
                    med = median(word_counts)
                    if med > 0:
                        threshold = med * self._QG_MAX_TO_MEDIAN_RATIO
                        lopsided_count = sum(1 for ch in chapters if ch['word_count'] > threshold)
                        if lopsided_count:
                            logger.info("Quality gate: lopsided ratio (max/median=%.1fx > %.1fx), re-splitting %d chapter(s) for book %s",
                                        max(word_counts) / med, self._QG_MAX_TO_MEDIAN_RATIO, lopsided_count, book_id)
                        new_chapters = []
                        for ch in chapters:
                            if ch['word_count'] > threshold:
                                target = int(med * 2)
                                if target < 500:
                                    target = 500
                                parts = self._resplit_chapter(ch, book_id, target)
                                new_chapters.extend(parts)
                                changed = True
                            else:
                                new_chapters.append(ch)
                        chapters = new_chapters

            if not changed:
                break

        # Renumber all chapters
        for i, ch in enumerate(chapters):
            ch['chapter_number'] = i + 1
            ch['id'] = f"{book_id}-ch{i + 1}"

        return chapters

    def _resplit_chapter(self, chapter: Dict, book_id: str, max_words: int) -> List[Dict]:
        """Re-split a single oversized chapter at paragraph boundaries.

        Splits at blank lines (\\n\\s*\\n). If no paragraph breaks exist,
        falls back to word-count chunking.
        """
        content = chapter.get('content', '')
        title = chapter.get('title', 'Section')

        if not content or len(content.split()) <= max_words:
            return [chapter]

        # Split at paragraph boundaries
        paragraphs = re.split(r'\n\s*\n', content)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        if len(paragraphs) <= 1:
            # No paragraph breaks - fall back to word-count chunking
            words = content.split()
            parts = []
            for i in range(0, len(words), max_words):
                chunk_words = words[i:i + max_words]
                chunk_content = ' '.join(chunk_words)
                part_num = len(parts) + 1
                part_title = title if part_num == 1 else f"{title} (part {part_num})"
                parts.append({
                    'id': '',
                    'book_id': book_id,
                    'chapter_number': 0,
                    'title': part_title,
                    'content': chunk_content,
                    'word_count': len(chunk_words),
                    'file_path': ''
                })
            return parts

        # Greedily merge paragraphs into sub-chapters up to max_words
        parts = []
        current_paragraphs = []
        current_words = 0

        for para in paragraphs:
            para_words = len(para.split())
            if current_words + para_words > max_words and current_paragraphs:
                # Flush current accumulator
                part_num = len(parts) + 1
                part_title = title if part_num == 1 else f"{title} (part {part_num})"
                part_content = '\n\n'.join(current_paragraphs)
                parts.append({
                    'id': '',
                    'book_id': book_id,
                    'chapter_number': 0,
                    'title': part_title,
                    'content': part_content,
                    'word_count': len(part_content.split()),
                    'file_path': ''
                })
                current_paragraphs = [para]
                current_words = para_words
            else:
                current_paragraphs.append(para)
                current_words += para_words

        # Flush remaining
        if current_paragraphs:
            part_num = len(parts) + 1
            part_title = title if part_num == 1 else f"{title} (part {part_num})"
            part_content = '\n\n'.join(current_paragraphs)
            parts.append({
                'id': '',
                'book_id': book_id,
                'chapter_number': 0,
                'title': part_title,
                'content': part_content,
                'word_count': len(part_content.split()),
                'file_path': ''
            })

        return parts if parts else [chapter]
