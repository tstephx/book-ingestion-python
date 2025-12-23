"""Diagnostic tools for chapter detection analysis."""

from dataclasses import dataclass
from typing import List, Dict, Optional
from pathlib import Path

from src.processors.chapter_detector import (
    ChapterCandidate,
    CandidateExtractor,
    CandidateScorer,
    AnchorMerger,
    DetectionStats,
    MatchType,
)
from src.processors.chapter_splitter import ChapterSplitter
from src.utils.config import Config


@dataclass
class AnchorDiagnostic:
    """Diagnostic info for a single anchor."""
    line_index: int
    title: str
    match_type: str
    confidence: float
    is_high_confidence: bool
    preceded_by_blank: bool
    followed_by_prose: bool
    nearby_similar_lines: int
    in_code_block: bool
    penalties_applied: List[str]


@dataclass
class DetectionDiagnostic:
    """Full diagnostic report for chapter detection."""
    file_name: str
    total_candidates: int
    high_confidence_count: int
    medium_confidence_count: int
    low_confidence_count: int
    anchors_selected: int
    toc_titles_found: int
    toc_titles_matched: int
    method: str
    confidence: str
    anchors: List[AnchorDiagnostic]
    issues: List[str]
    suggestions: List[str]


class DetectionDiagnostics:
    """Analyze chapter detection and provide diagnostic information."""

    def __init__(self):
        self.config = Config()
        self.splitter = ChapterSplitter(self.config)
        self.extractor = CandidateExtractor()
        self.scorer = CandidateScorer()
        self.merger = AnchorMerger()

    def analyze_text(self, text: str, file_name: str = "unknown",
                     external_toc_titles: List[str] = None) -> DetectionDiagnostic:
        """Analyze chapter detection for given text."""
        # Get TOC titles
        is_external_toc = False
        if external_toc_titles and len(external_toc_titles) >= 3:
            toc_titles = external_toc_titles
            is_external_toc = True
        else:
            toc_titles = self.splitter._extract_toc_titles(text)

        # Extract and score candidates
        candidates = self.extractor.extract(text, toc_titles, is_external_toc)
        for c in candidates:
            c.confidence = self.scorer.score(c)

        # Categorize by confidence
        high = [c for c in candidates if c.confidence >= 0.7]
        medium = [c for c in candidates if 0.4 <= c.confidence < 0.7]
        low = [c for c in candidates if c.confidence < 0.4]

        # Get anchors
        word_count = len(text.split())
        anchors, stats = self.merger.merge(candidates, word_count)

        # Count TOC matches
        toc_matched = sum(1 for a in anchors if a.match_type == MatchType.TOC)

        # Build anchor diagnostics
        anchor_diagnostics = []
        for anchor in anchors:
            penalties = self._get_penalties(anchor)
            anchor_diagnostics.append(AnchorDiagnostic(
                line_index=anchor.line_index,
                title=anchor.title[:60] + ("..." if len(anchor.title) > 60 else ""),
                match_type=anchor.match_type.name,
                confidence=anchor.confidence,
                is_high_confidence=anchor.confidence >= 0.7,
                preceded_by_blank=anchor.preceded_by_blank,
                followed_by_prose=anchor.followed_by_prose,
                nearby_similar_lines=anchor.nearby_similar_lines,
                in_code_block=anchor.in_code_block,
                penalties_applied=penalties,
            ))

        # Identify issues and suggestions
        issues, suggestions = self._analyze_issues(
            candidates, anchors, toc_titles, toc_matched, stats
        )

        return DetectionDiagnostic(
            file_name=file_name,
            total_candidates=len(candidates),
            high_confidence_count=len(high),
            medium_confidence_count=len(medium),
            low_confidence_count=len(low),
            anchors_selected=len(anchors),
            toc_titles_found=len(toc_titles),
            toc_titles_matched=toc_matched,
            method=stats.method,
            confidence=stats.confidence,
            anchors=anchor_diagnostics,
            issues=issues,
            suggestions=suggestions,
        )

    def _get_penalties(self, candidate: ChapterCandidate) -> List[str]:
        """Identify which penalties were applied to a candidate."""
        penalties = []
        if candidate.in_code_block:
            penalties.append("in_code_block (-0.5)")
        if not candidate.preceded_by_blank:
            penalties.append("no_blank_before (-0.2)")
        if not candidate.followed_by_prose:
            penalties.append("no_prose_after (-0.3)")
        if candidate.nearby_similar_lines >= 2:
            penalties.append("list_item (-0.4)")
        return penalties

    def _analyze_issues(self, candidates: List[ChapterCandidate],
                        anchors: List[ChapterCandidate],
                        toc_titles: List[str],
                        toc_matched: int,
                        stats: DetectionStats) -> tuple:
        """Identify issues and provide suggestions."""
        issues = []
        suggestions = []

        # Check for low TOC match rate
        if toc_titles and toc_matched < len(toc_titles) * 0.5:
            issues.append(f"Only {toc_matched}/{len(toc_titles)} TOC titles matched in body")
            suggestions.append("TOC titles may not match body headings (different formatting?)")

        # Check for medium-confidence anchors
        medium_anchors = [a for a in anchors if 0.4 <= a.confidence < 0.7]
        if medium_anchors:
            issues.append(f"{len(medium_anchors)} anchors have medium confidence")
            for a in medium_anchors:
                penalties = self._get_penalties(a)
                if penalties:
                    issues.append(f"  Line {a.line_index}: {', '.join(penalties)}")

        # Check for fallback method
        if stats.method == 'fallback':
            issues.append("Using fallback method (no good chapter markers found)")
            suggestions.append("PDF may have unusual structure or chapter markers")

        # Check for too many candidates
        if len(candidates) > 500:
            issues.append(f"High candidate count ({len(candidates)}) may indicate noise")

        # Check for no TOC titles
        if not toc_titles:
            issues.append("No TOC titles extracted from text")
            suggestions.append("Add TOC pattern for this book's format")

        # Check for anchors in TOC area
        early_anchors = [a for a in anchors if a.line_index < 100]
        if early_anchors and len(anchors) > 3:
            issues.append(f"{len(early_anchors)} anchors in first 100 lines (likely TOC)")
            suggestions.append("These may be TOC entries, not chapter starts")

        return issues, suggestions

    def format_report(self, diagnostic: DetectionDiagnostic) -> str:
        """Format diagnostic as readable report."""
        lines = []
        lines.append(f"=== Chapter Detection Diagnostic: {diagnostic.file_name} ===")
        lines.append("")
        lines.append("Summary:")
        lines.append(f"  Method: {diagnostic.method}")
        lines.append(f"  Confidence: {diagnostic.confidence}")
        lines.append(f"  Total candidates: {diagnostic.total_candidates}")
        lines.append(f"  Anchors selected: {diagnostic.anchors_selected}")
        lines.append("")
        lines.append("Candidate Distribution:")
        lines.append(f"  High (>=0.7):   {diagnostic.high_confidence_count}")
        lines.append(f"  Medium (0.4-0.7): {diagnostic.medium_confidence_count}")
        lines.append(f"  Low (<0.4):     {diagnostic.low_confidence_count}")
        lines.append("")
        lines.append("TOC Matching:")
        lines.append(f"  TOC titles found: {diagnostic.toc_titles_found}")
        lines.append(f"  TOC titles matched: {diagnostic.toc_titles_matched}")
        lines.append("")

        if diagnostic.issues:
            lines.append("Issues Detected:")
            for issue in diagnostic.issues:
                lines.append(f"  - {issue}")
            lines.append("")

        if diagnostic.suggestions:
            lines.append("Suggestions:")
            for suggestion in diagnostic.suggestions:
                lines.append(f"  - {suggestion}")
            lines.append("")

        lines.append("Anchors:")
        for i, anchor in enumerate(diagnostic.anchors, 1):
            conf_marker = "✓" if anchor.is_high_confidence else "○"
            lines.append(f"  {i:2d}. [{conf_marker}] Line {anchor.line_index:5d} | "
                        f"{anchor.confidence:.2f} | {anchor.match_type:10s}")
            lines.append(f"      Title: {anchor.title}")
            if anchor.penalties_applied:
                lines.append(f"      Penalties: {', '.join(anchor.penalties_applied)}")

        return "\n".join(lines)


def diagnose_pdf(pdf_path: str) -> str:
    """Convenience function to diagnose a PDF file."""
    from src.converters.pdf_converter import PDFConverter

    converter = PDFConverter()
    result = converter.convert(pdf_path)

    if not result['success']:
        return f"Failed to convert PDF: {result.get('error', 'Unknown error')}"

    diagnostics = DetectionDiagnostics()
    diagnostic = diagnostics.analyze_text(result['text'], Path(pdf_path).name)
    return diagnostics.format_report(diagnostic)


def diagnose_epub(epub_path: str) -> str:
    """Convenience function to diagnose an EPUB file."""
    from src.converters.epub_converter import EPUBConverter

    converter = EPUBConverter()
    result = converter.convert(epub_path)

    if not result['success']:
        return f"Failed to convert EPUB: {result.get('error', 'Unknown error')}"

    toc_titles = result.get('toc_titles', [])
    diagnostics = DetectionDiagnostics()
    diagnostic = diagnostics.analyze_text(
        result['text'],
        Path(epub_path).name,
        external_toc_titles=toc_titles
    )
    return diagnostics.format_report(diagnostic)
