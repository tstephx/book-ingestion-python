"""Enhanced EPUB Parser combining ebooklib with EpubSplit's spine/anchor detection.

This module extracts chapter structure from EPUBs using multiple strategies:
1. Spine order - the publisher's intended reading sequence
2. NCX/NAV TOC - explicit chapter titles with anchor points
3. Anchor-level granularity - sub-chapter split points within files
4. Content fingerprinting - resolves anchors to exact line positions

Inspired by https://github.com/JimmXinu/EpubSplit
"""

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote
from xml.dom.minidom import parseString

from bs4 import BeautifulSoup
from ebooklib import epub

from .epub_types import AnchorLocation, AnchorMap, EnhancedTOC, SplitPoint


@dataclass
class SpineItem:
    """A content document in the EPUB spine (reading order)."""

    idref: str  # Reference ID in manifest
    href: str  # File path
    media_type: str  # MIME type
    content: str = ""  # Raw HTML content
    text: str = ""  # Extracted plain text
    line_offset: int = 0  # Starting line in combined text


@dataclass
class EPUBStructure:
    """Complete structural analysis of an EPUB."""

    title: str
    authors: List[str]
    spine: List[SpineItem]  # Files in reading order
    split_points: List[SplitPoint]  # All potential chapter boundaries
    toc_titles: List[str]  # Flat list of TOC titles (for compatibility)
    full_text: str = ""  # Combined text content
    anchor_map: AnchorMap = field(default_factory=dict)  # Resolved anchors

    # Metadata about the parsing
    has_ncx: bool = False
    has_nav: bool = False
    spine_count: int = 0
    anchor_count: int = 0


class EnhancedEPUBParser:
    """Parse EPUB structure with spine and anchor-level granularity."""

    # Skip patterns for front/back matter
    SKIP_PATTERNS = re.compile(
        r"^(cover|cover page|title|title page|copyright|contents|toc|"
        r"table of contents|dedication|acknowledgments?|preface|foreword|"
        r"introduction|about the authors?|about this book|index|glossary|"
        r"bibliography|appendix|colophon|front matter|back matter|"
        r"half title|full title|also by|praise for|endorsements|notes|"
        r"references|who this book is for|what this book covers|"
        r"how to read this book|conventions used|get in touch|code in action|"
        r"to get the most out of this book|download|errata|piracy|"
        r"other books you may enjoy|share your thoughts)$",
        re.IGNORECASE,
    )

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path)
        self._epub: Optional[epub.EpubBook] = None
        self._zip: Optional[zipfile.ZipFile] = None
        self._opf_path: str = ""
        self._opf_dir: str = ""
        self._manifest: Dict[str, Tuple[str, str]] = {}  # id -> (href, media_type)
        self._toc_map: Dict[
            str, List[Tuple[str, Optional[str], int]]
        ] = {}  # href -> [(title, anchor, depth)]

    def parse(self) -> EPUBStructure:
        """Parse the EPUB and return complete structural analysis."""
        # Use ebooklib for high-level access
        self._epub = epub.read_epub(str(self.file_path))

        # Also open as ZIP for low-level access (spine order, raw content)
        self._zip = zipfile.ZipFile(self.file_path, "r")

        try:
            # Parse container.xml to find OPF
            self._parse_container()

            # Parse manifest from OPF
            self._parse_manifest()

            # Parse TOC (NCX or NAV) with anchors
            self._parse_toc_with_anchors()

            # Build spine with content
            spine = self._build_spine()

            # Generate split points combining spine + TOC
            split_points = self._generate_split_points(spine)

            # Combine full text with line tracking
            full_text, spine = self._combine_text_with_tracking(spine)

            # Build anchor map (resolve anchors to line indices)
            anchor_map = self._build_anchor_map(spine, split_points, full_text)

            # Extract metadata
            title = self._get_metadata("title") or "(Title Missing)"
            authors = self._get_authors()

            # Build flat TOC titles list (for compatibility with existing code)
            toc_titles = [
                sp.title for sp in split_points if not self._should_skip(sp.title)
            ]

            return EPUBStructure(
                title=title,
                authors=authors,
                spine=spine,
                split_points=split_points,
                toc_titles=toc_titles,
                full_text=full_text,
                anchor_map=anchor_map,
                has_ncx=self._has_ncx(),
                has_nav=self._has_nav(),
                spine_count=len(spine),
                anchor_count=sum(1 for sp in split_points if sp.is_anchor_split),
            )
        finally:
            if self._zip:
                self._zip.close()

    def _parse_container(self) -> None:
        """Parse META-INF/container.xml to find OPF location."""
        try:
            container_xml = self._zip.read("META-INF/container.xml").decode("utf-8")
            dom = parseString(container_xml)
            rootfile = dom.getElementsByTagName("rootfile")[0]
            self._opf_path = rootfile.getAttribute("full-path")
            # Get directory part for resolving relative paths
            if "/" in self._opf_path:
                self._opf_dir = self._opf_path.rsplit("/", 1)[0] + "/"
            else:
                self._opf_dir = ""
        except Exception:
            # Fallback: look for .opf file
            for name in self._zip.namelist():
                if name.endswith(".opf"):
                    self._opf_path = name
                    if "/" in name:
                        self._opf_dir = name.rsplit("/", 1)[0] + "/"
                    break

    def _parse_manifest(self) -> None:
        """Parse manifest from OPF to map IDs to hrefs."""
        try:
            opf_content = self._zip.read(self._opf_path).decode("utf-8")
            dom = parseString(opf_content)

            for item in dom.getElementsByTagName("item"):
                item_id = item.getAttribute("id")
                href = item.getAttribute("href")
                media_type = item.getAttribute("media-type")
                # Resolve relative path
                full_href = self._resolve_path(href)
                self._manifest[item_id] = (full_href, media_type)
        except Exception:
            pass

    def _parse_toc_with_anchors(self) -> None:
        """Parse TOC (NCX or NAV) extracting anchors for sub-chapter splits."""
        # Try NCX first (EPUB 2)
        ncx_path = self._find_ncx_path()
        if ncx_path:
            self._parse_ncx(ncx_path)
            return

        # Try NAV (EPUB 3)
        nav_path = self._find_nav_path()
        if nav_path:
            self._parse_nav(nav_path)

    def _find_ncx_path(self) -> Optional[str]:
        """Find NCX file path from manifest."""
        for item_id, (href, media_type) in self._manifest.items():
            if media_type == "application/x-dtbncx+xml" or href.endswith(".ncx"):
                return href
        return None

    def _find_nav_path(self) -> Optional[str]:
        """Find NAV file path from manifest."""
        for item_id, (href, media_type) in self._manifest.items():
            if "nav" in item_id.lower() and media_type == "application/xhtml+xml":
                return href
        return None

    def _parse_ncx(self, ncx_path: str) -> None:
        """Parse NCX file for TOC with anchors."""
        try:
            ncx_content = self._zip.read(ncx_path).decode("utf-8")
            dom = parseString(ncx_content)

            # Get NCX directory for resolving relative paths
            ncx_dir = ""
            if "/" in ncx_path:
                ncx_dir = ncx_path.rsplit("/", 1)[0] + "/"

            def parse_navpoints(navpoints, depth=0):
                for navpoint in navpoints:
                    if navpoint.nodeType != navpoint.ELEMENT_NODE:
                        continue
                    if navpoint.tagName != "navPoint":
                        continue

                    # Get title
                    title = ""
                    text_nodes = navpoint.getElementsByTagName("text")
                    if text_nodes and text_nodes[0].firstChild:
                        title = text_nodes[0].firstChild.data.strip()

                    # Get src with potential anchor
                    content_nodes = navpoint.getElementsByTagName("content")
                    if content_nodes:
                        src = content_nodes[0].getAttribute("src")
                        src = unquote(src)

                        # Resolve relative to NCX location
                        if not src.startswith("/"):
                            src = ncx_dir + src
                        src = self._normalize_path(src)

                        # Split href and anchor
                        if "#" in src:
                            href, anchor = src.split("#", 1)
                        else:
                            href, anchor = src, None

                        # Store in toc_map
                        if href not in self._toc_map:
                            self._toc_map[href] = []
                        self._toc_map[href].append((title, anchor, depth))

                    # Recurse into nested navPoints
                    child_navpoints = [
                        n
                        for n in navpoint.childNodes
                        if n.nodeType == n.ELEMENT_NODE and n.tagName == "navPoint"
                    ]
                    if child_navpoints:
                        parse_navpoints(child_navpoints, depth + 1)

            nav_map = dom.getElementsByTagName("navMap")
            if nav_map:
                parse_navpoints(nav_map[0].childNodes)

        except Exception:
            pass

    def _parse_nav(self, nav_path: str) -> None:
        """Parse EPUB 3 NAV file for TOC with anchors."""
        try:
            nav_content = self._zip.read(nav_path).decode("utf-8")
            soup = BeautifulSoup(nav_content, "html.parser")

            # Get NAV directory for resolving relative paths
            nav_dir = ""
            if "/" in nav_path:
                nav_dir = nav_path.rsplit("/", 1)[0] + "/"

            # Find the toc nav element
            toc_nav = soup.find("nav", {"epub:type": "toc"}) or soup.find(
                "nav", id="toc"
            )
            if not toc_nav:
                return

            def parse_list(ol, depth=0):
                if not ol:
                    return
                for li in ol.find_all("li", recursive=False):
                    a = li.find("a")
                    if a and a.get("href"):
                        title = a.get_text(strip=True)
                        href = unquote(a["href"])

                        # Resolve relative path
                        if not href.startswith("/") and not href.startswith("#"):
                            href = nav_dir + href
                        href = self._normalize_path(href)

                        # Split href and anchor
                        if "#" in href:
                            file_href, anchor = href.split("#", 1)
                        else:
                            file_href, anchor = href, None

                        if file_href not in self._toc_map:
                            self._toc_map[file_href] = []
                        self._toc_map[file_href].append((title, anchor, depth))

                    # Recurse into nested lists
                    nested_ol = li.find("ol")
                    if nested_ol:
                        parse_list(nested_ol, depth + 1)

            parse_list(toc_nav.find("ol"))

        except Exception:
            pass

    def _build_spine(self) -> List[SpineItem]:
        """Build spine (reading order) with content."""
        spine = []

        try:
            opf_content = self._zip.read(self._opf_path).decode("utf-8")
            dom = parseString(opf_content)

            for itemref in dom.getElementsByTagName("itemref"):
                idref = itemref.getAttribute("idref")
                if idref not in self._manifest:
                    continue

                href, media_type = self._manifest[idref]

                # Only include document types
                if media_type not in ("application/xhtml+xml", "text/html"):
                    continue

                # Read content
                try:
                    content = self._zip.read(href).decode("utf-8")
                    soup = BeautifulSoup(content, "html.parser")
                    text = soup.get_text(separator="\n", strip=True)
                except Exception:
                    content = ""
                    text = ""

                spine.append(
                    SpineItem(
                        idref=idref,
                        href=href,
                        media_type=media_type,
                        content=content,
                        text=text,
                    )
                )
        except Exception:
            pass

        return spine

    def _combine_text_with_tracking(
        self, spine: List[SpineItem]
    ) -> Tuple[str, List[SpineItem]]:
        """Combine spine text and track line offsets for each file.

        Returns:
            Tuple of (full_text, updated_spine_with_offsets)
        """
        full_text_parts = []
        current_line = 0

        for item in spine:
            item.line_offset = current_line
            if item.text:
                full_text_parts.append(item.text)
                current_line += item.text.count("\n") + 2  # +2 for separator

        full_text = "\n\n".join(full_text_parts)
        return full_text, spine

    def _generate_split_points(self, spine: List[SpineItem]) -> List[SplitPoint]:
        """Generate split points combining spine files with TOC anchors."""
        split_points = []

        for spine_idx, item in enumerate(spine):
            href = item.href

            # Check if this file has TOC entries
            if href in self._toc_map:
                toc_entries = self._toc_map[href]

                # Sort entries: file-level first, then anchors in order
                file_level = [(t, a, d) for t, a, d in toc_entries if a is None]
                anchor_level = [(t, a, d) for t, a, d in toc_entries if a is not None]

                # Add file-level entry if present
                for title, anchor, depth in file_level:
                    if not self._should_skip(title):
                        split_points.append(
                            SplitPoint(
                                title=title,
                                href=href,
                                anchor=None,
                                depth=depth,
                                spine_index=spine_idx,
                            )
                        )

                # Add anchor-level entries
                for title, anchor, depth in anchor_level:
                    if not self._should_skip(title):
                        split_points.append(
                            SplitPoint(
                                title=title,
                                href=href,
                                anchor=anchor,
                                depth=depth,
                                spine_index=spine_idx,
                            )
                        )
            else:
                # No TOC entry - create split point from spine item anyway
                word_count = len(item.text.split()) if item.text else 0

                # Try to extract title from content
                title = (
                    self._extract_title_from_content(item.content)
                    or f"Section {spine_idx + 1}"
                )

                if (
                    not self._should_skip(title) and word_count > 100
                ):  # Skip empty/tiny sections
                    split_points.append(
                        SplitPoint(
                            title=title,
                            href=href,
                            anchor=None,
                            depth=0,
                            spine_index=spine_idx,
                        )
                    )

        return split_points

    def _build_anchor_map(
        self,
        spine: List[SpineItem],
        split_points: List[SplitPoint],
        full_text: str,
    ) -> AnchorMap:
        """Build anchor map by resolving each split point to a line index.

        Uses content fingerprinting to find anchor locations in the extracted text.
        """
        anchor_map: AnchorMap = {}
        full_text_lines = full_text.split("\n")

        # Build href->spine item lookup
        spine_by_href: Dict[str, SpineItem] = {item.href: item for item in spine}

        for sp in split_points:
            if sp.href not in spine_by_href:
                continue

            spine_item = spine_by_href[sp.href]

            if sp.anchor:
                # Anchor-level: find element in HTML and extract fingerprint
                location = self._resolve_anchor(
                    spine_item, sp.anchor, full_text, full_text_lines
                )
                if location:
                    anchor_map[sp.full_href] = location
            else:
                # File-level: use start of spine item's text
                line_idx = spine_item.line_offset
                char_offset = self._line_to_char_offset(full_text_lines, line_idx)
                fingerprint = full_text[char_offset : char_offset + 100].strip()

                if fingerprint:
                    anchor_map[sp.full_href] = AnchorLocation(
                        href=sp.full_href,
                        line_index=line_idx,
                        char_offset=char_offset,
                        fingerprint=fingerprint,
                    )

        return anchor_map

    def _resolve_anchor(
        self,
        spine_item: SpineItem,
        anchor: str,
        full_text: str,
        full_text_lines: List[str],
    ) -> Optional[AnchorLocation]:
        """Resolve an anchor to a line index using content fingerprinting.

        1. Find element with matching ID in source HTML
        2. Extract ~100 chars of text starting from that element (fingerprint)
        3. Find fingerprint in extracted full text
        4. Calculate line index from character position
        """
        try:
            soup = BeautifulSoup(spine_item.content, "html.parser")

            # Find element with matching ID
            element = soup.find(id=anchor)
            if not element:
                # Try finding by name attribute
                element = soup.find(attrs={"name": anchor})

            if not element:
                return None

            # Extract fingerprint (first ~100 chars of text from this element)
            element_text = element.get_text(strip=True)
            if not element_text:
                # Try getting text from parent or next sibling
                parent = element.parent
                if parent:
                    element_text = parent.get_text(strip=True)

            if not element_text or len(element_text) < 10:
                return None

            fingerprint = element_text[:100].strip()

            # Find fingerprint in full text
            # Start searching from this spine item's offset for efficiency
            search_start = self._line_to_char_offset(
                full_text_lines, spine_item.line_offset
            )
            pos = full_text.find(fingerprint, search_start)

            if pos < 0:
                # Try with shorter fingerprint
                fingerprint = element_text[:50].strip()
                pos = full_text.find(fingerprint, search_start)

            if pos < 0:
                return None

            # Convert character position to line index
            line_idx = full_text[:pos].count("\n")

            return AnchorLocation(
                href=f"{spine_item.href}#{anchor}",
                line_index=line_idx,
                char_offset=pos,
                fingerprint=fingerprint,
            )

        except Exception:
            return None

    def _line_to_char_offset(self, lines: List[str], line_idx: int) -> int:
        """Convert line index to character offset."""
        if line_idx <= 0:
            return 0
        # Sum lengths of all lines before target + newlines
        return sum(len(line) + 1 for line in lines[:line_idx])

    def _extract_title_from_content(self, html: str) -> Optional[str]:
        """Try to extract a title from HTML content."""
        try:
            soup = BeautifulSoup(html, "html.parser")

            # Try common title elements in order
            for tag in ["h1", "h2", "title"]:
                element = soup.find(tag)
                if element:
                    title = element.get_text(strip=True)
                    if title and len(title) < 200:  # Sanity check
                        return title
        except Exception:
            pass

        return None

    def _resolve_path(self, href: str) -> str:
        """Resolve a relative path against the OPF directory."""
        if href.startswith("/"):
            return href[1:]  # Remove leading slash
        return self._opf_dir + href

    def _normalize_path(self, path: str) -> str:
        """Normalize path (resolve .. and .)"""
        parts = []
        for part in path.split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part and part != ".":
                parts.append(part)
        return "/".join(parts)

    def _should_skip(self, title: str) -> bool:
        """Check if title should be skipped (front/back matter)."""
        return bool(self.SKIP_PATTERNS.match(title.strip()))

    def _get_metadata(self, key: str) -> Optional[str]:
        """Get metadata value from EPUB."""
        try:
            values = self._epub.get_metadata("DC", key)
            if values:
                return values[0][0]
        except Exception:
            pass
        return None

    def _get_authors(self) -> List[str]:
        """Get list of authors from EPUB."""
        authors = []
        try:
            creators = self._epub.get_metadata("DC", "creator")
            for creator in creators:
                if creator[0]:
                    authors.append(creator[0])
        except Exception:
            pass
        return authors if authors else ["(Authors Missing)"]

    def _has_ncx(self) -> bool:
        """Check if EPUB has NCX file."""
        return self._find_ncx_path() is not None

    def _has_nav(self) -> bool:
        """Check if EPUB has NAV file."""
        return self._find_nav_path() is not None


def parse_epub(file_path: str | Path) -> EPUBStructure:
    """Convenience function to parse an EPUB file.

    Args:
        file_path: Path to the EPUB file

    Returns:
        EPUBStructure with complete structural analysis including anchor map

    Example:
        structure = parse_epub("/path/to/book.epub")

        # Get spine-ordered content
        for item in structure.spine:
            print(f"{item.href}: {len(item.text)} chars")

        # Get chapter split points with anchors
        for split in structure.split_points:
            print(f"{split.title} @ {split.full_href} (depth={split.depth})")

        # Get resolved anchor locations
        for href, location in structure.anchor_map.items():
            print(f"{href} -> line {location.line_index}")

        # Get flat TOC titles (compatible with existing code)
        for title in structure.toc_titles:
            print(title)
    """
    parser = EnhancedEPUBParser(file_path)
    return parser.parse()


def build_enhanced_toc(structure: EPUBStructure) -> EnhancedTOC:
    """Convert EPUBStructure to EnhancedTOC for use in chapter detection.

    Args:
        structure: Parsed EPUB structure

    Returns:
        EnhancedTOC with split points and anchor map
    """
    return EnhancedTOC(
        split_points=structure.split_points,
        spine_files=[item.href for item in structure.spine],
        anchor_map=structure.anchor_map,
    )
