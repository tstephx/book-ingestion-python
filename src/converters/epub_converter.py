"""EPUB Converter using ebooklib"""

import re
from ebooklib import epub
from bs4 import BeautifulSoup


class EPUBConverter:
    def convert(self, file_path):
        """Convert EPUB to text with chapter information from navigation."""
        try:
            book = epub.read_epub(file_path)

            text_parts = []

            # Extract text from all document items
            for item in book.get_items():
                if item.get_type() == 9:  # DOCUMENT type
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    text_parts.append(soup.get_text())

            text = '\n\n'.join(text_parts)

            # Extract chapter titles from EPUB's native TOC/navigation
            toc_titles = self._extract_toc_titles(book)

            metadata = {
                'title': book.get_metadata('DC', 'title')[0][0] if book.get_metadata('DC', 'title') else '',
                'author': book.get_metadata('DC', 'creator')[0][0] if book.get_metadata('DC', 'creator') else '',
                'language': book.get_metadata('DC', 'language')[0][0] if book.get_metadata('DC', 'language') else 'en'
            }

            return {
                'success': True,
                'text': text,
                'metadata': metadata,
                'toc_titles': toc_titles  # Chapter titles from EPUB navigation
            }

        except Exception as e:
            return {
                'success': False,
                'text': '',
                'metadata': {},
                'toc_titles': [],
                'error': str(e)
            }

    def _extract_toc_titles(self, book):
        """Extract chapter titles from EPUB's table of contents.

        Filters out front/back matter to get actual chapter titles.
        """
        titles = []

        # Skip patterns for front/back matter
        skip_patterns = re.compile(
            r'^(cover|cover page|title|title page|copyright|contents|toc|'
            r'table of contents|dedication|acknowledgments?|preface|foreword|'
            r'introduction|about the authors?|about this book|index|glossary|'
            r'bibliography|appendix|colophon|front matter|back matter|'
            r'half title|full title|also by|praise for|endorsements|notes|'
            r'references|who this book is for|what this book covers|'
            r'how to read this book|conventions used|get in touch|code in action|'
            r'to get the most out of this book|download|errata|piracy|'
            r'other books you may enjoy|share your thoughts)$',
            re.IGNORECASE
        )

        def extract_from_toc(toc_items):
            """Recursively extract titles from TOC items."""
            for item in toc_items:
                if isinstance(item, tuple):
                    # Nested section: (Section, [children])
                    section, children = item
                    if hasattr(section, 'title') and section.title:
                        title = section.title.strip()
                        if not skip_patterns.match(title):
                            titles.append(title)
                    if children:
                        extract_from_toc(children)
                elif hasattr(item, 'title') and item.title:
                    # Simple Link item
                    title = item.title.strip()
                    if not skip_patterns.match(title):
                        titles.append(title)

        if hasattr(book, 'toc') and book.toc:
            extract_from_toc(book.toc)

        return titles
