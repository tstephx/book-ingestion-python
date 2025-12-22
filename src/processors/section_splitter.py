"""Section splitting logic for large chapters"""

import re
from typing import List, Dict, Optional


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.
    Uses rough heuristic: ~4 characters per token for English text.
    This is conservative to stay safely under limits.
    """
    return len(text) // 4


class SectionSplitter:
    """
    Splits large chapters into smaller, AI-readable sections.

    Strategy:
    1. Detect section headers within chapter content
    2. Split at natural boundaries (headers)
    3. If sections are still too large, sub-chunk at paragraph boundaries
    """

    def __init__(self, config: dict):
        self.max_tokens = config.get('max_tokens_per_section', 15000)
        self.min_tokens = config.get('min_tokens_per_section', 500)
        self.header_patterns = self._compile_patterns(config.get('section_patterns', []))

    def _compile_patterns(self, patterns: List[str]) -> List[re.Pattern]:
        """Compile section header patterns"""
        default_patterns = [
            # Markdown headers
            r'^#{2,4}\s+.+$',
            # Numbered sections like "1.1 Title" or "1.1.1 Title"
            r'^\d+\.\d+(?:\.\d+)?\s+[A-Z].+$',
            # ALL CAPS headers (min 3 words, max 60 chars)
            r'^[A-Z][A-Z\s]{10,60}$',
            # Title case headers preceded by blank line (handled specially)
            r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,6}$',
            # Common section markers
            r'^(?:Introduction|Summary|Conclusion|Overview|Background|Prerequisites|Setup|Installation|Configuration|Implementation|Example|Exercise|Review|Key\s+(?:Points|Takeaways|Concepts))(?:\s*:)?$',
        ]

        all_patterns = patterns + default_patterns
        return [re.compile(p, re.MULTILINE | re.IGNORECASE) for p in all_patterns]

    def split_chapter(self, chapter: Dict) -> List[Dict]:
        """
        Split a chapter into sections if it exceeds token limit.

        Returns list of section dicts with:
        - title: section title
        - content: section content
        - token_count: estimated tokens
        - section_number: 1-based index within chapter
        - is_partial: True if this is a sub-chunk of a larger section
        """
        content = chapter.get('content', '')
        token_count = estimate_tokens(content)

        # If chapter is small enough, return as-is
        if token_count <= self.max_tokens:
            return [{
                'title': chapter.get('title', 'Untitled'),
                'content': content,
                'token_count': token_count,
                'word_count': len(content.split()),
                'section_number': 1,
                'is_partial': False,
                'original_chapter': chapter
            }]

        # Detect sections within the chapter
        sections = self._detect_sections(content)

        # If no sections found, use paragraph-based chunking
        if len(sections) <= 1:
            return self._chunk_by_paragraphs(chapter, content)

        # Process each section, sub-chunking if needed
        result = []
        section_num = 1

        for section in sections:
            section_tokens = estimate_tokens(section['content'])

            if section_tokens <= self.max_tokens:
                result.append({
                    'title': section['title'],
                    'content': section['content'],
                    'token_count': section_tokens,
                    'word_count': len(section['content'].split()),
                    'section_number': section_num,
                    'is_partial': False,
                    'original_chapter': chapter
                })
                section_num += 1
            else:
                # Sub-chunk this large section
                chunks = self._chunk_by_paragraphs_content(
                    section['content'],
                    section['title']
                )
                for i, chunk in enumerate(chunks):
                    result.append({
                        'title': f"{section['title']} (Part {i + 1})",
                        'content': chunk['content'],
                        'token_count': chunk['token_count'],
                        'word_count': len(chunk['content'].split()),
                        'section_number': section_num,
                        'is_partial': True,
                        'original_chapter': chapter
                    })
                    section_num += 1

        return result

    def _detect_sections(self, content: str) -> List[Dict]:
        """
        Detect section headers and split content accordingly.
        """
        lines = content.split('\n')
        section_starts = []

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Skip empty or very short lines
            if len(line_stripped) < 3:
                continue

            # Skip lines that are too long (not headers)
            if len(line_stripped) > 80:
                continue

            # Check each pattern
            for pattern in self.header_patterns:
                if pattern.match(line_stripped):
                    # Additional validation: should be preceded by blank line
                    # (except for first few lines)
                    if i > 5 and i > 0 and lines[i - 1].strip() != '':
                        continue

                    # Validate it's not a list item
                    if self._is_list_item(line_stripped, lines, i):
                        continue

                    section_starts.append({
                        'index': i,
                        'title': self._clean_section_title(line_stripped)
                    })
                    break

        # If no sections found, return entire content as one section
        if not section_starts:
            return [{'title': 'Content', 'content': content}]

        # Build sections from detected headers
        sections = []
        for idx, start in enumerate(section_starts):
            begin_line = start['index'] + 1  # Start after the header

            if idx + 1 < len(section_starts):
                end_line = section_starts[idx + 1]['index']
            else:
                end_line = len(lines)

            section_content = '\n'.join(lines[begin_line:end_line]).strip()

            # Skip tiny sections
            if len(section_content.split()) < 50:
                continue

            sections.append({
                'title': start['title'],
                'content': section_content
            })

        # If first section starts after significant content, capture it
        if section_starts and section_starts[0]['index'] > 10:
            preamble = '\n'.join(lines[:section_starts[0]['index']]).strip()
            if len(preamble.split()) >= 100:
                sections.insert(0, {
                    'title': 'Introduction',
                    'content': preamble
                })

        return sections

    def _is_list_item(self, line: str, lines: List[str], index: int) -> bool:
        """Check if a line is part of a numbered list rather than a header"""
        # Check surrounding lines for similar patterns
        numbered_pattern = re.compile(r'^\d+\.\d+')

        nearby_matches = 0
        for j in range(max(0, index - 3), min(len(lines), index + 4)):
            if j != index and numbered_pattern.match(lines[j].strip()):
                nearby_matches += 1

        return nearby_matches >= 2

    def _clean_section_title(self, title: str) -> str:
        """Clean up a section title"""
        # Remove markdown header markers
        title = re.sub(r'^#+\s*', '', title)
        # Remove trailing colons or periods
        title = title.rstrip(':.')
        # Normalize whitespace
        title = re.sub(r'\s+', ' ', title).strip()
        return title[:80]  # Limit length

    def _chunk_by_paragraphs(self, chapter: Dict, content: str) -> List[Dict]:
        """
        Split content by paragraphs when no sections are detected.
        """
        chunks = self._chunk_by_paragraphs_content(content, chapter.get('title', 'Section'))

        result = []
        for i, chunk in enumerate(chunks):
            result.append({
                'title': f"{chapter.get('title', 'Section')} (Part {i + 1})",
                'content': chunk['content'],
                'token_count': chunk['token_count'],
                'word_count': len(chunk['content'].split()),
                'section_number': i + 1,
                'is_partial': True,
                'original_chapter': chapter
            })

        return result

    def _chunk_by_paragraphs_content(self, content: str, base_title: str) -> List[Dict]:
        """
        Split content into chunks at paragraph boundaries.
        """
        # Split on double newlines (paragraph breaks)
        paragraphs = re.split(r'\n\s*\n', content)

        chunks = []
        current_chunk = []
        current_tokens = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_tokens = estimate_tokens(para)

            # If single paragraph exceeds limit, split it further
            if para_tokens > self.max_tokens:
                # Save current chunk first
                if current_chunk:
                    chunk_content = '\n\n'.join(current_chunk)
                    chunks.append({
                        'content': chunk_content,
                        'token_count': estimate_tokens(chunk_content)
                    })
                    current_chunk = []
                    current_tokens = 0

                # Split large paragraph by sentences
                sentence_chunks = self._split_large_paragraph(para)
                chunks.extend(sentence_chunks)
                continue

            # Check if adding this paragraph would exceed limit
            if current_tokens + para_tokens > self.max_tokens and current_chunk:
                # Save current chunk and start new one
                chunk_content = '\n\n'.join(current_chunk)
                chunks.append({
                    'content': chunk_content,
                    'token_count': estimate_tokens(chunk_content)
                })
                current_chunk = [para]
                current_tokens = para_tokens
            else:
                current_chunk.append(para)
                current_tokens += para_tokens

        # Don't forget the last chunk
        if current_chunk:
            chunk_content = '\n\n'.join(current_chunk)
            chunks.append({
                'content': chunk_content,
                'token_count': estimate_tokens(chunk_content)
            })

        return chunks

    def _split_large_paragraph(self, paragraph: str) -> List[Dict]:
        """
        Split a very large paragraph by sentences.
        """
        # Simple sentence splitting
        sentences = re.split(r'(?<=[.!?])\s+', paragraph)

        chunks = []
        current_chunk = []
        current_tokens = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sent_tokens = estimate_tokens(sentence)

            if current_tokens + sent_tokens > self.max_tokens and current_chunk:
                chunk_content = ' '.join(current_chunk)
                chunks.append({
                    'content': chunk_content,
                    'token_count': estimate_tokens(chunk_content)
                })
                current_chunk = [sentence]
                current_tokens = sent_tokens
            else:
                current_chunk.append(sentence)
                current_tokens += sent_tokens

        if current_chunk:
            chunk_content = ' '.join(current_chunk)
            chunks.append({
                'content': chunk_content,
                'token_count': estimate_tokens(chunk_content)
            })

        return chunks

    def needs_splitting(self, chapter: Dict) -> bool:
        """Check if a chapter needs to be split"""
        content = chapter.get('content', '')
        return estimate_tokens(content) > self.max_tokens


def split_chapters_for_ai(chapters: List[Dict], config: dict) -> List[Dict]:
    """
    Process a list of chapters, splitting large ones into AI-readable sections.

    This is the main entry point for the section splitting feature.
    """
    splitter = SectionSplitter(config)
    result = []

    for chapter in chapters:
        sections = splitter.split_chapter(chapter)

        # Add metadata about the split
        for section in sections:
            section['parent_chapter_number'] = chapter.get('chapter_number', 1)
            section['parent_chapter_title'] = chapter.get('title', 'Unknown')

        result.extend(sections)

    return result
