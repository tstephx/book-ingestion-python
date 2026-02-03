"""Tests for enhanced EPUB parsing with anchor resolution."""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from book_ingestion.converters.epub_types import (
    SplitPoint,
    AnchorLocation,
    AnchorMap,
    EnhancedTOC,
)
from book_ingestion.converters.enhanced_epub_parser import (
    EnhancedEPUBParser,
    EPUBStructure,
    SpineItem,
    parse_epub,
    build_enhanced_toc,
)


class TestSplitPoint:
    """Tests for SplitPoint dataclass."""

    def test_split_point_without_anchor(self):
        """Split point without anchor is file-level."""
        sp = SplitPoint(
            title="Chapter 1",
            href="chapter1.xhtml",
            anchor=None,
            depth=1,
            spine_index=0,
        )
        assert not sp.is_anchor_split
        assert sp.full_href == "chapter1.xhtml"

    def test_split_point_with_anchor(self):
        """Split point with anchor is sub-file level."""
        sp = SplitPoint(
            title="Section 1.1",
            href="chapter1.xhtml",
            anchor="section-1",
            depth=2,
            spine_index=0,
        )
        assert sp.is_anchor_split
        assert sp.full_href == "chapter1.xhtml#section-1"

    def test_split_point_depth_levels(self):
        """Depth indicates hierarchy level."""
        root = SplitPoint(title="Book", href="root.xhtml", depth=0, spine_index=0)
        part = SplitPoint(title="Part I", href="part1.xhtml", depth=1, spine_index=1)
        chapter = SplitPoint(title="Chapter 1", href="ch1.xhtml", depth=2, spine_index=2)
        section = SplitPoint(title="Section 1.1", href="ch1.xhtml", anchor="s1", depth=3, spine_index=2)

        assert root.depth == 0
        assert part.depth == 1
        assert chapter.depth == 2
        assert section.depth == 3


class TestAnchorLocation:
    """Tests for AnchorLocation dataclass."""

    def test_anchor_location_creation(self):
        """AnchorLocation stores resolved position."""
        loc = AnchorLocation(
            href="chapter1.xhtml#section-2",
            line_index=847,
            char_offset=12500,
            fingerprint="This is the start of section 2 which discusses...",
        )
        assert loc.line_index == 847
        assert loc.char_offset == 12500

    def test_anchor_location_validate_success(self):
        """Validation succeeds when fingerprint matches."""
        text = "Some preamble text. This is the start of section 2 which discusses important topics."
        loc = AnchorLocation(
            href="chapter1.xhtml#section-2",
            line_index=0,
            char_offset=20,
            fingerprint="This is the start of section 2 which discusses",
        )
        assert loc.validate(text)

    def test_anchor_location_validate_failure(self):
        """Validation fails when fingerprint doesn't match."""
        text = "Completely different text that doesn't contain the fingerprint."
        loc = AnchorLocation(
            href="chapter1.xhtml#section-2",
            line_index=0,
            char_offset=0,
            fingerprint="This is the start of section 2 which discusses",
        )
        assert not loc.validate(text)


class TestEnhancedTOC:
    """Tests for EnhancedTOC dataclass."""

    def test_enhanced_toc_empty(self):
        """Empty EnhancedTOC has zero counts."""
        toc = EnhancedTOC()
        assert toc.chapter_count == 0
        assert toc.anchor_count == 0
        assert toc.titles == []

    def test_enhanced_toc_with_chapters(self):
        """EnhancedTOC counts chapters correctly."""
        toc = EnhancedTOC(
            split_points=[
                SplitPoint(title="Part I", href="p1.xhtml", depth=1, spine_index=0),
                SplitPoint(title="Chapter 1", href="ch1.xhtml", depth=2, spine_index=1),
                SplitPoint(title="Section 1.1", href="ch1.xhtml", anchor="s1", depth=3, spine_index=1),
                SplitPoint(title="Chapter 2", href="ch2.xhtml", depth=2, spine_index=2),
            ],
            spine_files=["p1.xhtml", "ch1.xhtml", "ch2.xhtml"],
        )
        assert toc.chapter_count == 3  # depth <= 2
        assert toc.anchor_count == 1  # only s1 has anchor
        assert len(toc.titles) == 4

    def test_enhanced_toc_get_chapter_split_points(self):
        """get_chapter_split_points returns depth <= 2."""
        toc = EnhancedTOC(
            split_points=[
                SplitPoint(title="Chapter 1", href="ch1.xhtml", depth=2, spine_index=0),
                SplitPoint(title="Section 1.1", href="ch1.xhtml", anchor="s1", depth=3, spine_index=0),
                SplitPoint(title="Section 1.2", href="ch1.xhtml", anchor="s2", depth=3, spine_index=0),
            ]
        )
        chapter_splits = toc.get_chapter_split_points()
        assert len(chapter_splits) == 1
        assert chapter_splits[0].title == "Chapter 1"

    def test_enhanced_toc_get_section_split_points(self):
        """get_section_split_points returns depth > 2."""
        toc = EnhancedTOC(
            split_points=[
                SplitPoint(title="Chapter 1", href="ch1.xhtml", depth=2, spine_index=0),
                SplitPoint(title="Section 1.1", href="ch1.xhtml", anchor="s1", depth=3, spine_index=0),
                SplitPoint(title="Section 1.2", href="ch1.xhtml", anchor="s2", depth=3, spine_index=0),
            ]
        )
        section_splits = toc.get_section_split_points()
        assert len(section_splits) == 2
        assert section_splits[0].title == "Section 1.1"


class TestEnhancedEPUBParserMocked:
    """Tests for EnhancedEPUBParser using mocked EPUB data."""

    @patch("book_ingestion.converters.enhanced_epub_parser.epub.read_epub")
    @patch("book_ingestion.converters.enhanced_epub_parser.zipfile.ZipFile")
    def test_parser_extracts_metadata(self, mock_zip, mock_read_epub):
        """Parser extracts title and authors from EPUB."""
        # Setup mock EPUB
        mock_book = MagicMock()
        mock_book.get_metadata.side_effect = lambda ns, key: {
            ("DC", "title"): [("Test Book", {})],
            ("DC", "creator"): [("Author One", {}), ("Author Two", {})],
        }.get((ns, key), [])
        mock_read_epub.return_value = mock_book

        # Setup mock ZIP
        mock_zip_file = MagicMock()
        mock_zip_file.__enter__ = MagicMock(return_value=mock_zip_file)
        mock_zip_file.__exit__ = MagicMock(return_value=False)
        mock_zip_file.namelist.return_value = ["content.opf"]
        mock_zip_file.read.side_effect = lambda path: {
            "META-INF/container.xml": b'<?xml version="1.0"?><container><rootfile full-path="content.opf"/></container>',
            "content.opf": b'<?xml version="1.0"?><package><manifest></manifest><spine></spine></package>',
        }.get(path, b"")
        mock_zip.return_value = mock_zip_file

        parser = EnhancedEPUBParser("/fake/path.epub")
        structure = parser.parse()

        assert structure.title == "Test Book"
        assert "Author One" in structure.authors
        assert "Author Two" in structure.authors


class TestBuildEnhancedTOC:
    """Tests for build_enhanced_toc helper function."""

    def test_build_enhanced_toc_from_structure(self):
        """build_enhanced_toc creates EnhancedTOC from EPUBStructure."""
        split_points = [
            SplitPoint(title="Chapter 1", href="ch1.xhtml", depth=2, spine_index=0),
            SplitPoint(title="Chapter 2", href="ch2.xhtml", depth=2, spine_index=1),
        ]
        anchor_map = {
            "ch1.xhtml": AnchorLocation(
                href="ch1.xhtml",
                line_index=0,
                char_offset=0,
                fingerprint="Chapter 1 content",
            ),
        }

        structure = EPUBStructure(
            title="Test Book",
            authors=["Author"],
            spine=[
                SpineItem(idref="ch1", href="ch1.xhtml", media_type="application/xhtml+xml"),
                SpineItem(idref="ch2", href="ch2.xhtml", media_type="application/xhtml+xml"),
            ],
            split_points=split_points,
            toc_titles=["Chapter 1", "Chapter 2"],
            full_text="Chapter 1 content\n\nChapter 2 content",
            anchor_map=anchor_map,
        )

        enhanced_toc = build_enhanced_toc(structure)

        assert len(enhanced_toc.split_points) == 2
        assert len(enhanced_toc.spine_files) == 2
        assert "ch1.xhtml" in enhanced_toc.anchor_map


class TestIntegrationWithChapterDetector:
    """Tests for integration with chapter detector."""

    def test_anchor_candidates_have_high_confidence(self):
        """Candidates from anchors should have high confidence scores."""
        from book_ingestion.processors.chapter_detector import (
            CandidateExtractor,
            CandidateScorer,
            MatchType,
        )

        # Create enhanced TOC with resolved anchors
        # Note: depth=0 represents top-level chapters in EPUB structure
        enhanced_toc = EnhancedTOC(
            split_points=[
                SplitPoint(title="Chapter 1: Introduction", href="ch1.xhtml", depth=0, spine_index=0),
                SplitPoint(title="Chapter 2: Main Content", href="ch2.xhtml", depth=0, spine_index=1),
            ],
            spine_files=["ch1.xhtml", "ch2.xhtml"],
            anchor_map={
                "ch1.xhtml": AnchorLocation(
                    href="ch1.xhtml",
                    line_index=10,
                    char_offset=100,
                    fingerprint="Introduction to the book",
                ),
                "ch2.xhtml": AnchorLocation(
                    href="ch2.xhtml",
                    line_index=100,
                    char_offset=2000,
                    fingerprint="This chapter covers main content",
                ),
            },
        )

        # Create sample text with substantial prose content after each chapter start
        lines = []
        for i in range(200):
            if i == 10:
                lines.append("Introduction to the book content starts here")
            elif i == 100:
                lines.append("This chapter covers main content and more")
            elif 11 <= i <= 50:
                # Add substantial prose after Chapter 1
                lines.append("This is paragraph content for the chapter. It contains many words "
                           "that form complete sentences. The reader will find valuable information here.")
            elif 101 <= i <= 150:
                # Add substantial prose after Chapter 2
                lines.append("More detailed explanations follow in this section. Multiple sentences "
                           "provide context and depth to the topic being discussed here.")
            else:
                lines.append("")
        text = "\n".join(lines)

        # Extract candidates
        extractor = CandidateExtractor()
        candidates = extractor.extract(text, enhanced_toc=enhanced_toc)

        # Should have anchor-based candidates
        anchor_candidates = [c for c in candidates if c.match_type == MatchType.EPUB_ANCHOR]
        assert len(anchor_candidates) == 2

        # Score them
        scorer = CandidateScorer()
        for candidate in anchor_candidates:
            candidate.confidence = scorer.score(candidate)
            # EPUB_ANCHOR base score is 0.95, with prose following should stay high
            assert candidate.confidence >= 0.7  # High confidence with proper prose


class TestEPUBConverterEnhancedMode:
    """Tests for EPUB converter enhanced mode."""

    def test_enhanced_mode_returns_enhanced_toc(self):
        """Enhanced mode returns enhanced_toc in result."""
        # Patch where the imports happen in the epub_converter module
        with patch("book_ingestion.converters.enhanced_epub_parser.parse_epub") as mock_parse, \
             patch("book_ingestion.converters.enhanced_epub_parser.build_enhanced_toc") as mock_build_toc:

            from book_ingestion.converters.epub_converter import EPUBConverter

            # Setup mocks
            mock_structure = MagicMock()
            mock_structure.title = "Test Book"
            mock_structure.authors = ["Test Author"]
            mock_structure.full_text = "Full book content here"
            mock_structure.toc_titles = ["Chapter 1", "Chapter 2"]
            mock_parse.return_value = mock_structure

            mock_enhanced_toc = MagicMock()
            mock_build_toc.return_value = mock_enhanced_toc

            converter = EPUBConverter()
            result = converter.convert("/fake/book.epub", enhanced=True)

            assert result["success"]
            assert "enhanced_toc" in result
            assert result["enhanced_toc"] == mock_enhanced_toc
            assert result["toc_titles"] == ["Chapter 1", "Chapter 2"]

    @patch("book_ingestion.converters.epub_converter.epub.read_epub")
    def test_basic_mode_no_enhanced_toc(self, mock_read_epub):
        """Basic mode does not return enhanced_toc."""
        from book_ingestion.converters.epub_converter import EPUBConverter

        # Setup mock
        mock_book = MagicMock()
        mock_book.get_metadata.return_value = []
        mock_book.get_items.return_value = []
        mock_book.toc = []
        mock_read_epub.return_value = mock_book

        converter = EPUBConverter()
        result = converter.convert("/fake/book.epub", enhanced=False)

        assert result["success"]
        assert "enhanced_toc" not in result


class TestAnchorResolution:
    """Tests for anchor resolution logic."""

    def test_fingerprint_matching_finds_correct_position(self):
        """Fingerprint matching locates correct line in text."""
        # Simulate text with known structure
        lines = [
            "Preamble line 1",
            "Preamble line 2",
            "",
            "Chapter 1: Introduction",
            "This chapter introduces the main concepts.",
            "We will explore various topics.",
            "",
            "Chapter 2: Deep Dive",
            "Now we go deeper into the subject matter.",
        ]
        full_text = "\n".join(lines)

        # Create anchor location pointing to Chapter 2
        fingerprint = "Chapter 2: Deep Dive"
        char_offset = full_text.find(fingerprint)
        line_index = full_text[:char_offset].count("\n")

        loc = AnchorLocation(
            href="ch2.xhtml",
            line_index=line_index,
            char_offset=char_offset,
            fingerprint=fingerprint,
        )

        assert loc.line_index == 7  # 0-indexed, Chapter 2 is on line 8 (index 7)
        assert loc.validate(full_text)

    def test_depth_filtering_for_chapters(self):
        """Only depth <= 2 should be treated as chapter boundaries."""
        enhanced_toc = EnhancedTOC(
            split_points=[
                # These should be chapter boundaries
                SplitPoint(title="Part I", href="p1.xhtml", depth=1, spine_index=0),
                SplitPoint(title="Chapter 1", href="ch1.xhtml", depth=2, spine_index=1),
                # These should NOT be chapter boundaries (too deep)
                SplitPoint(title="Section 1.1", href="ch1.xhtml", anchor="s1", depth=3, spine_index=1),
                SplitPoint(title="Subsection 1.1.1", href="ch1.xhtml", anchor="ss1", depth=4, spine_index=1),
            ]
        )

        chapter_splits = enhanced_toc.get_chapter_split_points()
        section_splits = enhanced_toc.get_section_split_points()

        assert len(chapter_splits) == 2  # Part I and Chapter 1
        assert len(section_splits) == 2  # Section 1.1 and Subsection 1.1.1
