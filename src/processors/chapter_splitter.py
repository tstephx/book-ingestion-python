"""Chapter splitting logic with improved detection"""

import re
from typing import List, Dict

from src.processors.code_block_detector import CodeBlockDetector
from src.processors.chapter_detector import (
    ChapterCandidate,
    CandidateExtractor,
    CandidateScorer,
    AnchorMerger,
    DetectionStats,
    MatchType,
)


class ChapterSplitter:
    def __init__(self, config):
        self.config = config.chapter_detection
        self.patterns = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.config['patterns']]

        # New pipeline components
        self.code_detector = CodeBlockDetector()
        self.extractor = CandidateExtractor()
        self.scorer = CandidateScorer()
        self.merger = AnchorMerger()

    def split(self, text: str, book_id: str) -> List[Dict]:
        """Backwards-compatible API - returns list of chapter dicts."""
        result = self.split_with_stats(text, book_id)
        return result['chapters']

    def split_with_stats(self, text: str, book_id: str) -> Dict:
        """Split text into chapters with detection statistics."""
        # Calculate word count for expected chapters estimation
        word_count = len(text.split())

        # Stage 1: Detect code blocks
        code_regions = self.code_detector.detect(text)

        # Stage 2: Try TOC-based detection first
        toc_titles = self._extract_toc_titles(text)

        # Stage 3: Extract candidates
        candidates = self.extractor.extract(text, toc_titles)

        # Stage 4: Score candidates
        for candidate in candidates:
            candidate.confidence = self.scorer.score(candidate)

        # Stage 5: Select anchors and merge (pass word count for better estimation)
        anchors, stats = self.merger.merge(candidates, word_count)
        stats.code_blocks_detected = len(code_regions)

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

        return {'chapters': chapters, 'stats': stats}

    def _extract_toc_titles(self, text: str) -> List[str]:
        """Extract chapter titles from table of contents."""
        lines = text.split('\n')

        # Patterns for different TOC formats
        toc_patterns = [
            # Packt style: "Chapter X, Title, description..."
            (re.compile(r'^Chapter\s+(\d+),\s+([^,]+)', re.IGNORECASE), 2),
            # Apress style: "Chapter X: Title...page" or "Chapter X: Title"
            (re.compile(r'^Chapter\s+(\d+):\s+([^\.]+?)(?:\.{2,}|\s*$)', re.IGNORECASE), 2),
            # Project style: "Project XA: Title"
            (re.compile(r'^Project\s+(\d+[A-Z]):\s+(.+)', re.IGNORECASE), 2),
        ]

        # Try each pattern to find chapter titles in TOC
        chapter_titles = []
        for toc_pattern, title_group in toc_patterns:
            chapter_titles = []
            for line in lines[:400]:  # Extended for longer TOCs
                match = toc_pattern.match(line.strip())
                if match:
                    # Strip whitespace from title
                    title = match.group(title_group).strip()
                    # Remove any trailing punctuation or whitespace
                    title = title.rstrip(' \t\n\r')
                    chapter_titles.append(title)

            # If we found enough chapters with this pattern, use it
            if len(chapter_titles) >= 3:
                break

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

    def _fixed_size_split(self, text, book_id):
        """Split into fixed-size chunks when no chapters detected"""
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
