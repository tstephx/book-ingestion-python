"""File writing utilities"""

from pathlib import Path
import json
import re
from typing import List, Dict, Optional


class FileWriter:
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_book(self, metadata, chapters, raw_text):
        """Write book files to disk (legacy method for unsplit chapters)"""
        book_id = metadata['id']
        book_dir = self.output_dir / book_id

        # Create directory structure
        (book_dir / 'raw').mkdir(parents=True, exist_ok=True)
        (book_dir / 'chapters').mkdir(parents=True, exist_ok=True)

        # Write metadata
        metadata_file = book_dir / 'metadata.json'
        with open(metadata_file, 'w') as f:
            json.dump({
                'id': metadata['id'],
                'title': metadata.get('title', 'Unknown'),
                'author': metadata.get('author'),
                'word_count': metadata.get('word_count', 0),
                'chapter_count': len(chapters)
            }, f, indent=2)

        # Write raw text
        raw_file = book_dir / 'raw' / 'original.txt'
        with open(raw_file, 'w', encoding='utf-8') as f:
            f.write(raw_text)

        # Write chapters
        for chapter in chapters:
            filename = self._sanitize_filename(
                f"{chapter['chapter_number']:02d}-{chapter['title']}.md"
            )
            chapter_path = book_dir / 'chapters' / filename

            with open(chapter_path, 'w', encoding='utf-8') as f:
                f.write(f"# {chapter['title']}\n\n")
                f.write(f"**Chapter {chapter['chapter_number']}**\n")
                f.write(f"*Word Count: {chapter['word_count']}*\n\n")
                f.write("---\n\n")
                f.write(chapter['content'])

            # Update chapter with file path
            chapter['file_path'] = str(chapter_path)

    def write_book_with_sections(
        self,
        metadata: Dict,
        chapters: List[Dict],
        sections: List[Dict],
        raw_text: str
    ):
        """
        Write book files with section-aware structure.

        For chapters that were split into sections:
        - Creates a folder: chapters/01-chapter-name/
        - Writes sections as: 01-section-name.md, 02-section-name.md

        For chapters that weren't split:
        - Writes directly: chapters/01-chapter-name.md
        """
        book_id = metadata['id']
        book_dir = self.output_dir / book_id

        # Create directory structure
        (book_dir / 'raw').mkdir(parents=True, exist_ok=True)
        (book_dir / 'chapters').mkdir(parents=True, exist_ok=True)

        # Group sections by parent chapter
        chapter_sections = {}
        for section in sections:
            ch_num = section.get('parent_chapter_number', 1)
            if ch_num not in chapter_sections:
                chapter_sections[ch_num] = []
            chapter_sections[ch_num].append(section)

        # Calculate section counts for metadata
        total_sections = len(sections)
        split_chapters = sum(1 for ch_num in chapter_sections if len(chapter_sections[ch_num]) > 1)

        # Write metadata
        metadata_file = book_dir / 'metadata.json'
        with open(metadata_file, 'w') as f:
            json.dump({
                'id': metadata['id'],
                'title': metadata.get('title', 'Unknown'),
                'author': metadata.get('author'),
                'word_count': metadata.get('word_count', 0),
                'chapter_count': len(chapters),
                'section_count': total_sections,
                'split_chapters': split_chapters,
                'max_tokens_per_file': 15000
            }, f, indent=2)

        # Write raw text
        raw_file = book_dir / 'raw' / 'original.txt'
        with open(raw_file, 'w', encoding='utf-8') as f:
            f.write(raw_text)

        # Write chapters/sections
        file_paths = []

        for ch_num, ch_sections in sorted(chapter_sections.items()):
            chapter = next(
                (c for c in chapters if c.get('chapter_number') == ch_num),
                ch_sections[0].get('original_chapter', {})
            )
            chapter_title = chapter.get('title', f'Chapter {ch_num}')

            if len(ch_sections) == 1:
                # Single section - write as single file
                section = ch_sections[0]
                filename = self._sanitize_filename(
                    f"{ch_num:02d}-{chapter_title}.md"
                )
                chapter_path = book_dir / 'chapters' / filename

                content = self._format_section_content(
                    section,
                    chapter_title,
                    ch_num,
                    is_single=True
                )

                with open(chapter_path, 'w', encoding='utf-8') as f:
                    f.write(content)

                file_paths.append(str(chapter_path))
            else:
                # Multiple sections - create folder
                folder_name = self._sanitize_filename(f"{ch_num:02d}-{chapter_title}")
                chapter_folder = book_dir / 'chapters' / folder_name
                chapter_folder.mkdir(parents=True, exist_ok=True)

                # Write chapter index file
                index_content = self._format_chapter_index(
                    chapter_title,
                    ch_num,
                    ch_sections
                )
                index_path = chapter_folder / '_index.md'
                with open(index_path, 'w', encoding='utf-8') as f:
                    f.write(index_content)

                # Write each section
                for i, section in enumerate(ch_sections, 1):
                    section_filename = self._sanitize_filename(
                        f"{i:02d}-{section['title']}.md"
                    )
                    section_path = chapter_folder / section_filename

                    content = self._format_section_content(
                        section,
                        section['title'],
                        ch_num,
                        is_single=False,
                        section_num=i,
                        total_sections=len(ch_sections)
                    )

                    with open(section_path, 'w', encoding='utf-8') as f:
                        f.write(content)

                    file_paths.append(str(section_path))

        # Update chapters with file paths for database
        for i, chapter in enumerate(chapters):
            ch_num = chapter.get('chapter_number', i + 1)
            ch_sections = chapter_sections.get(ch_num, [])

            if len(ch_sections) == 1:
                chapter_title = chapter.get('title', f'Chapter {ch_num}')
                filename = self._sanitize_filename(f"{ch_num:02d}-{chapter_title}.md")
                chapter['file_path'] = str(book_dir / 'chapters' / filename)
            else:
                chapter_title = chapter.get('title', f'Chapter {ch_num}')
                folder_name = self._sanitize_filename(f"{ch_num:02d}-{chapter_title}")
                chapter['file_path'] = str(book_dir / 'chapters' / folder_name)

        return file_paths

    def _format_section_content(
        self,
        section: Dict,
        title: str,
        chapter_num: int,
        is_single: bool = True,
        section_num: Optional[int] = None,
        total_sections: Optional[int] = None
    ) -> str:
        """Format section content with YAML frontmatter"""
        token_count = section.get('token_count', 0)
        word_count = section.get('word_count', 0)
        parent_title = section.get('parent_chapter_title', title)

        # Build YAML frontmatter
        frontmatter_lines = [
            '---',
            f'title: "{self._escape_yaml(title)}"',
            f'chapter: {chapter_num}',
            f'tokens: {token_count}',
            f'words: {word_count}',
        ]

        if not is_single:
            frontmatter_lines.extend([
                f'section: {section_num}',
                f'total_sections: {total_sections}',
                f'parent_chapter: "{self._escape_yaml(parent_title)}"',
            ])

        if section.get('is_partial'):
            frontmatter_lines.append('is_partial: true')

        frontmatter_lines.append('---')
        frontmatter = '\n'.join(frontmatter_lines)

        # Build content
        content_lines = [
            frontmatter,
            '',
            f'# {title}',
            '',
        ]

        if is_single:
            content_lines.append(f'**Chapter {chapter_num}** | *{word_count:,} words* | *~{token_count:,} tokens*')
        else:
            content_lines.append(
                f'**Chapter {chapter_num}, Section {section_num}/{total_sections}** | '
                f'*{word_count:,} words* | *~{token_count:,} tokens*'
            )

        content_lines.extend([
            '',
            '---',
            '',
            section.get('content', '')
        ])

        return '\n'.join(content_lines)

    def _format_chapter_index(
        self,
        chapter_title: str,
        chapter_num: int,
        sections: List[Dict]
    ) -> str:
        """Format chapter index file listing all sections"""
        total_tokens = sum(s.get('token_count', 0) for s in sections)
        total_words = sum(s.get('word_count', 0) for s in sections)

        lines = [
            '---',
            f'title: "{self._escape_yaml(chapter_title)}"',
            f'chapter: {chapter_num}',
            f'total_sections: {len(sections)}',
            f'total_tokens: {total_tokens}',
            f'total_words: {total_words}',
            '---',
            '',
            f'# {chapter_title}',
            '',
            f'**Chapter {chapter_num}** | *{len(sections)} sections* | *{total_words:,} words total*',
            '',
            'This chapter has been split into multiple sections for AI readability.',
            '',
            '## Sections',
            '',
        ]

        for i, section in enumerate(sections, 1):
            section_filename = self._sanitize_filename(f"{i:02d}-{section['title']}.md")
            tokens = section.get('token_count', 0)
            lines.append(f'{i}. [{section["title"]}](./{section_filename}) (~{tokens:,} tokens)')

        return '\n'.join(lines)

    def _escape_yaml(self, text: str) -> str:
        """Escape special characters for YAML strings"""
        return text.replace('"', '\\"').replace('\n', ' ')

    def _sanitize_filename(self, filename):
        """Clean filename for filesystem"""
        # Remove invalid characters
        filename = re.sub(r'[^\w\s\-.]', '', filename)
        # Replace spaces with hyphens
        filename = re.sub(r'\s+', '-', filename)
        # Remove multiple hyphens
        filename = re.sub(r'-+', '-', filename)
        return filename.lower()[:100]  # Limit length
