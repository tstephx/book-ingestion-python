"""Data types for enhanced EPUB parsing with anchor-level granularity.

These types support the enhanced EPUB parser which provides:
- Spine-ordered content extraction
- TOC with anchor-level split points
- Line-index resolution for precise chapter boundaries
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SplitPoint:
    """A potential chapter/section boundary in the EPUB.

    Represents a TOC entry with optional anchor for sub-file positioning.
    """

    title: str  # Chapter/section title from TOC
    href: str  # File path within EPUB (e.g., 'chapter1.xhtml')
    anchor: Optional[str] = None  # Fragment ID (e.g., 'section-2')
    depth: int = 0  # Hierarchy level (0=root, 1=part, 2=chapter, 3+=section)
    spine_index: int = 0  # Position in reading order

    @property
    def is_anchor_split(self) -> bool:
        """True if this is a sub-file split point."""
        return self.anchor is not None

    @property
    def full_href(self) -> str:
        """Full href including anchor if present."""
        if self.anchor:
            return f"{self.href}#{self.anchor}"
        return self.href


@dataclass
class AnchorLocation:
    """Resolved location of a TOC anchor in the extracted text.

    Maps an EPUB anchor (href#fragment) to an exact position in the
    full extracted text, enabling precise chapter boundary detection.
    """

    href: str  # Full href with anchor (e.g., 'chapter1.xhtml#section-2')
    line_index: int  # Line number in extracted text (0-indexed)
    char_offset: int  # Character offset from start of text
    fingerprint: str  # Text snippet (~100 chars) for validation

    def validate(self, text: str) -> bool:
        """Verify fingerprint exists at expected location."""
        if self.char_offset >= len(text):
            return False
        actual = text[self.char_offset : self.char_offset + len(self.fingerprint)]
        # Fuzzy match - first 50 chars should match
        return actual[:50] == self.fingerprint[:50]


# Type alias for anchor map: full_href -> AnchorLocation
AnchorMap = Dict[str, AnchorLocation]


@dataclass
class EnhancedTOC:
    """Enhanced table of contents with split points and anchor map.

    Combines TOC structure with resolved anchor locations for
    high-confidence chapter boundary detection.
    """

    split_points: List[SplitPoint] = field(default_factory=list)
    spine_files: List[str] = field(default_factory=list)  # Ordered file paths
    anchor_map: AnchorMap = field(default_factory=dict)  # Resolved anchors

    @property
    def chapter_count(self) -> int:
        """Count of top-level chapters (depth <= 2)."""
        return sum(1 for sp in self.split_points if sp.depth <= 2)

    @property
    def anchor_count(self) -> int:
        """Count of anchor-level split points."""
        return sum(1 for sp in self.split_points if sp.is_anchor_split)

    @property
    def titles(self) -> List[str]:
        """Flat list of all TOC titles for compatibility."""
        return [sp.title for sp in self.split_points]

    def get_chapter_split_points(self) -> List[SplitPoint]:
        """Get split points that represent chapter boundaries (depth <= 2)."""
        return [sp for sp in self.split_points if sp.depth <= 2]

    def get_section_split_points(self) -> List[SplitPoint]:
        """Get split points that represent sections (depth > 2)."""
        return [sp for sp in self.split_points if sp.depth > 2]
