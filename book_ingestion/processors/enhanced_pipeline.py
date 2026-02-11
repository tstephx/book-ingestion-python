"""
Enhanced Book Processing Pipeline with Quality Validation

Integrates:
1. Enhanced text cleaning (LLM-era best practices)
2. Recursive text splitting (LangChain-style)
3. Semantic chunking for boundary validation
4. Comprehensive quality metrics and validation

Based on best practices from:
- Python Data Cleaning and Preparation Best Practices
- Generative AI with LangChain
- LLM Design Patterns

Usage:
    from src.processors.enhanced_pipeline import EnhancedPipeline
    
    pipeline = EnhancedPipeline()
    result = pipeline.process_book(text, book_id, external_toc_titles)
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum
import statistics

from .enhanced_text_cleaner import EnhancedTextCleaner, CleaningStats
from .recursive_splitter import ChapterAwareSplitter, RecursiveTextSplitter
from .semantic_chunker import (
    SemanticChunker, 
    ChapterBoundaryValidator,
    validate_chunking,
    SemanticChunkingResult
)
from .profiler import DataProfiler, BookProfile, QualityReport
from .chapter_validator import ChapterValidator, ValidationResult

logger = logging.getLogger(__name__)


class ProcessingMode(Enum):
    """Processing mode options"""
    QUICK = "quick"           # Basic processing, no semantic analysis
    STANDARD = "standard"     # Standard processing with validation
    THOROUGH = "thorough"     # Full semantic analysis and validation


@dataclass
class ChapterDetectionResult:
    """Result of chapter detection"""
    chapters: List[Dict]
    method: str                    # 'toc', 'heuristic', 'semantic', 'hybrid', 'fallback'
    confidence: float              # 0-1 overall confidence
    toc_chapters_found: int
    semantic_boundaries_found: int
    merge_suggestions: List[Tuple[int, int, str]]  # (chapter_idx, merge_with, reason)


@dataclass
class PipelineResult:
    """Complete result from the enhanced pipeline"""
    # Core outputs
    cleaned_text: str
    chapters: List[Dict]
    
    # Quality metrics
    cleaning_stats: CleaningStats
    validation_result: ValidationResult
    quality_report: QualityReport
    
    # Detection info
    detection_method: str
    detection_confidence: float
    
    # Semantic analysis (if performed)
    semantic_result: Optional[SemanticChunkingResult] = None
    
    # Recommendations
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    @property
    def is_valid(self) -> bool:
        """Check if processing result is valid"""
        return (
            self.validation_result.is_valid and
            self.quality_report.quality_score >= 50
        )
    
    @property
    def needs_review(self) -> bool:
        """Check if result needs manual review"""
        return (
            len(self.warnings) > 0 or
            self.detection_confidence < 0.7 or
            self.quality_report.quality_score < 75
        )


class EnhancedPipeline:
    """
    Enhanced book processing pipeline with integrated quality validation.
    
    Features:
    - LLM-optimized text cleaning
    - Multi-strategy chapter detection
    - Semantic boundary validation
    - Comprehensive quality metrics
    - Actionable recommendations
    """
    
    # Target chapter sizes based on best practices
    TARGET_MIN_WORDS = 3000
    TARGET_MAX_WORDS = 15000
    IDEAL_CHAPTER_WORDS = 8000
    
    def __init__(
        self,
        mode: ProcessingMode = ProcessingMode.STANDARD,
        enable_semantic: bool = True,
        target_chapter_words: int = None,
    ):
        """
        Initialize the enhanced pipeline.
        
        Args:
            mode: Processing thoroughness level
            enable_semantic: Enable semantic boundary detection
            target_chapter_words: Target words per chapter
        """
        self.mode = mode
        self.enable_semantic = enable_semantic and mode != ProcessingMode.QUICK
        self.target_chapter_words = target_chapter_words or self.IDEAL_CHAPTER_WORDS
        
        # Initialize components
        self.text_cleaner = EnhancedTextCleaner()
        self.chapter_splitter = ChapterAwareSplitter(
            target_words=self.target_chapter_words,
            min_words=self.TARGET_MIN_WORDS,
            max_words=self.TARGET_MAX_WORDS,
        )
        self.validator = ChapterValidator()
        self.profiler = DataProfiler()
        
        # Semantic components (lazy loaded)
        self._semantic_chunker = None
        self._boundary_validator = None
    
    @property
    def semantic_chunker(self) -> SemanticChunker:
        """Lazy load semantic chunker"""
        if self._semantic_chunker is None:
            self._semantic_chunker = SemanticChunker()
        return self._semantic_chunker
    
    @property
    def boundary_validator(self) -> ChapterBoundaryValidator:
        """Lazy load boundary validator"""
        if self._boundary_validator is None:
            self._boundary_validator = ChapterBoundaryValidator(use_semantic=True)
        return self._boundary_validator
    
    def process_book(
        self,
        text: str,
        book_id: str,
        external_toc_titles: List[str] = None,
        metadata: Dict = None,
        enhanced_toc=None,
    ) -> PipelineResult:
        """
        Process a book through the enhanced pipeline.

        Args:
            text: Raw book text
            book_id: Unique book identifier
            external_toc_titles: Optional chapter titles from external source
            metadata: Optional book metadata
            enhanced_toc: Optional EnhancedTOC with split points and anchor map
                         for precise chapter detection (from enhanced EPUB parser)

        Returns:
            PipelineResult with chapters and quality metrics
        """
        logger.info(f"Processing book {book_id} with mode={self.mode.value}")

        # Step 1: Clean text
        cleaned_text, cleaning_stats = self.text_cleaner.clean(text, track_stats=True)
        logger.info(f"Cleaned text: {cleaning_stats.bytes_saved:,} bytes saved")

        # Step 2: Detect chapters using multiple strategies
        detection_result = self._detect_chapters(
            cleaned_text,
            book_id,
            external_toc_titles,
            enhanced_toc=enhanced_toc,
        )
        
        chapters = detection_result.chapters
        logger.info(f"Detected {len(chapters)} chapters via {detection_result.method}")
        
        # Step 3: Validate detection quality
        word_count = len(cleaned_text.split())
        validation_result = self.validator.validate(cleaned_text, chapters, word_count)
        
        # Step 4: Quick validation check
        quick_validation = validate_chunking(chapters)
        
        # Step 5: Semantic validation (if enabled and mode allows)
        semantic_result = None
        if self.enable_semantic and self.mode == ProcessingMode.THOROUGH:
            try:
                semantic_result = self.boundary_validator.validate_chapters(
                    cleaned_text, chapters
                )
                logger.info(f"Semantic validation complete: {semantic_result.overall_confidence:.2f} confidence")
            except Exception as e:
                logger.warning(f"Semantic validation failed: {e}")
        
        # Step 6: Generate quality report
        book_metadata = metadata or {'id': book_id}
        profile = self.profiler.profile_book(book_metadata, chapters)
        quality_report = self.profiler.assess_quality(profile)
        
        # Step 7: Compile warnings and recommendations
        warnings, recommendations = self._compile_recommendations(
            detection_result,
            validation_result,
            quick_validation,
            semantic_result,
            quality_report
        )
        
        return PipelineResult(
            cleaned_text=cleaned_text,
            chapters=chapters,
            cleaning_stats=cleaning_stats,
            validation_result=validation_result,
            quality_report=quality_report,
            detection_method=detection_result.method,
            detection_confidence=detection_result.confidence,
            semantic_result=semantic_result,
            warnings=warnings,
            recommendations=recommendations,
        )
    
    def _detect_chapters(
        self,
        text: str,
        book_id: str,
        external_toc_titles: List[str] = None,
        enhanced_toc=None,
    ) -> ChapterDetectionResult:
        """
        Detect chapters using multiple strategies.

        Priority order:
        1. EPUB anchor-based detection (highest confidence if enhanced_toc provided)
        2. External TOC (e.g., from EPUB navigation) - most reliable
        3. Internal TOC detection
        4. Semantic boundary detection (if enabled)
        5. Recursive splitting with validation
        6. Fixed-size fallback
        """
        chapters = []
        method = "unknown"
        confidence = 0.0
        toc_chapters = 0
        semantic_boundaries = 0
        merge_suggestions = []

        # Try TOC-based detection first
        from .chapter_splitter import ChapterSplitter
        from ..utils.config import Config

        try:
            config = Config()
            splitter = ChapterSplitter(config)
            result = splitter.split_with_stats(
                text, book_id, external_toc_titles, enhanced_toc=enhanced_toc
            )
            chapters = result['chapters']
            stats = result['stats']
            
            method = stats.method if hasattr(stats, 'method') else 'heuristic'
            confidence = self._method_to_confidence(stats.confidence) if hasattr(stats, 'confidence') else 0.5
            toc_chapters = stats.anchors_used if hasattr(stats, 'anchors_used') else len(chapters)
            
        except Exception as e:
            logger.warning(f"Chapter splitter failed: {e}, falling back to recursive splitting")
            
            # Fallback to recursive splitting
            split_result = self.chapter_splitter.split(text)
            chapters = self._splits_to_chapters(split_result.chunks, book_id)
            method = "recursive"
            confidence = 0.4
        
        # Validate and potentially improve detection
        quick_check = validate_chunking(chapters)

        if not quick_check['valid']:
            logger.warning(f"Initial detection issue: {quick_check['issue']}")

            # Try to fix over-fragmentation
            if quick_check['issue'] == 'over-fragmentation':
                chapters, merges = self._merge_small_chapters(chapters, book_id)
                merge_suggestions = merges
                method = f"{method}_merged"
                confidence = min(confidence + 0.1, 0.8)

        # Post-detection quality gate: if most chapters are near-empty
        # (< 100 words), the TOC matched the Table of Contents page rather
        # than actual chapter positions. Fall back to fixed-size splitting.
        total_words = sum(c.get('word_count', 0) for c in chapters)
        near_empty = sum(1 for c in chapters if c.get('word_count', 0) < 100)
        if len(chapters) > 1 and near_empty > len(chapters) * 0.5 and total_words < len(text.split()) * 0.5:
            logger.warning(
                f"Degenerate detection: {near_empty}/{len(chapters)} chapters have < 100 words "
                f"({total_words} captured vs {len(text.split())} total). "
                f"Falling back to fixed-size splitting."
            )
            try:
                chapters = splitter._fixed_size_split(text, book_id)
                method = "fallback"
                confidence = 0.4
            except Exception:
                # If splitter not available (exception path), use recursive
                split_result = self.chapter_splitter.split(text)
                chapters = self._splits_to_chapters(split_result.chunks, book_id)
                method = "recursive_fallback"
                confidence = 0.4

        # Add semantic boundary count if available
        if self.enable_semantic and self.mode != ProcessingMode.QUICK:
            try:
                boundaries = self.semantic_chunker.detect_boundaries(text)
                semantic_boundaries = sum(1 for b in boundaries if b.is_significant)
            except Exception as e:
                logger.debug(f"Semantic boundary detection skipped: {e}")
        
        return ChapterDetectionResult(
            chapters=chapters,
            method=method,
            confidence=confidence,
            toc_chapters_found=toc_chapters,
            semantic_boundaries_found=semantic_boundaries,
            merge_suggestions=merge_suggestions,
        )
    
    def _method_to_confidence(self, confidence_str: str) -> float:
        """Convert confidence string to numeric value"""
        mapping = {
            'high': 0.9,
            'medium': 0.7,
            'low': 0.4,
        }
        return mapping.get(str(confidence_str).lower(), 0.5)
    
    def _splits_to_chapters(self, chunks, book_id: str) -> List[Dict]:
        """Convert split chunks to chapter dictionaries"""
        chapters = []
        for i, chunk in enumerate(chunks):
            chapters.append({
                'id': f"{book_id}-ch{i+1}",
                'book_id': book_id,
                'chapter_number': i + 1,
                'title': f"Chapter {i + 1}",
                'content': chunk.text if hasattr(chunk, 'text') else str(chunk),
                'word_count': chunk.word_count if hasattr(chunk, 'word_count') else len(str(chunk).split()),
                'file_path': '',
            })
        return chapters
    
    def _merge_small_chapters(
        self,
        chapters: List[Dict],
        book_id: str,
    ) -> Tuple[List[Dict], List[Tuple[int, int, str]]]:
        """
        Merge chapters that are too small, with guards against over-merging.

        Guards:
        - Won't merge if the combined chapter would exceed TARGET_MAX_WORDS
        - If merging produces fewer chapters than expected for the total word
          count, returns the original chapters instead

        Returns:
            Tuple of (merged_chapters, merge_records)
        """
        if not chapters:
            return chapters, []

        total_words = sum(c.get('word_count', 0) for c in chapters)

        merged = []
        merges = []
        current = None

        for i, chapter in enumerate(chapters):
            word_count = chapter.get('word_count', 0)

            if current is None:
                current = chapter.copy()
                continue

            current_words = current.get('word_count', 0)
            combined_words = current_words + word_count

            # Merge if current is too small AND the result wouldn't be too large
            if current_words < self.TARGET_MIN_WORDS and combined_words <= self.TARGET_MAX_WORDS:
                # Merge with next chapter
                merged_content = current.get('content', '') + '\n\n' + chapter.get('content', '')
                current = {
                    'id': current['id'],
                    'book_id': book_id,
                    'chapter_number': current['chapter_number'],
                    'title': current.get('title', ''),
                    'content': merged_content,
                    'word_count': combined_words,
                    'file_path': '',
                }
                merges.append((i, i-1, f"Merged: {current_words} + {word_count} words"))
            else:
                merged.append(current)
                current = chapter.copy()

        # Don't forget the last chapter
        if current is not None:
            merged.append(current)

        # Guard: if merging produced a degenerate result (too few chapters for
        # the total word count), return the original chapters unchanged.
        # Expected minimum: 1 chapter per 15K words (TARGET_MAX_WORDS).
        min_expected = max(2, total_words // self.TARGET_MAX_WORDS)
        if len(merged) < min_expected and len(chapters) >= min_expected:
            logger.warning(
                f"Merge produced only {len(merged)} chapters for {total_words} words "
                f"(expected >= {min_expected}). Keeping original {len(chapters)} chapters."
            )
            return chapters, []

        # Renumber chapters
        for i, chapter in enumerate(merged):
            chapter['chapter_number'] = i + 1
            chapter['id'] = f"{book_id}-ch{i+1}"

        return merged, merges
    
    def _compile_recommendations(
        self,
        detection: ChapterDetectionResult,
        validation: ValidationResult,
        quick_check: Dict,
        semantic: Optional[SemanticChunkingResult],
        quality: QualityReport,
    ) -> Tuple[List[str], List[str]]:
        """Compile warnings and recommendations from all sources"""
        warnings = []
        recommendations = []
        
        # From validation
        warnings.extend(validation.warnings)
        warnings.extend(validation.errors)
        
        # From quality report
        warnings.extend(quality.warnings)
        
        # From quick check
        if not quick_check['valid']:
            issue = quick_check.get('issue', 'unknown')
            message = quick_check.get('message', f"Validation issue: {issue}")
            warnings.append(message)
        
        # From semantic analysis
        if semantic:
            recommendations.extend(semantic.recommendations)
        
        # Detection-specific recommendations
        if detection.confidence < 0.5:
            recommendations.append(
                "Low detection confidence - consider manual review of chapter boundaries"
            )
        
        if detection.method == 'fallback':
            recommendations.append(
                "Fell back to fixed-size splitting - add chapter patterns for this book format"
            )
        
        # Quality-specific recommendations
        if quality.quality_score < 50:
            recommendations.append(
                "Low quality score - review chapter detection and text cleaning"
            )
        elif quality.quality_score < 75:
            recommendations.append(
                "Moderate quality - some optimization possible"
            )
        
        # Remove duplicates while preserving order
        warnings = list(dict.fromkeys(warnings))
        recommendations = list(dict.fromkeys(recommendations))
        
        return warnings, recommendations
    
    def generate_report(self, result: PipelineResult) -> str:
        """Generate a comprehensive processing report"""
        report_lines = [
            "# Book Processing Report",
            "",
            "## Summary",
            f"- **Chapters detected:** {len(result.chapters)}",
            f"- **Detection method:** {result.detection_method}",
            f"- **Detection confidence:** {result.detection_confidence:.0%}",
            f"- **Quality score:** {result.quality_report.quality_score}/100",
            f"- **Valid:** {'✅ Yes' if result.is_valid else '❌ No'}",
            f"- **Needs review:** {'⚠️ Yes' if result.needs_review else '✅ No'}",
            "",
            "## Text Cleaning",
            f"- Original size: {result.cleaning_stats.original_length:,} chars",
            f"- Cleaned size: {result.cleaning_stats.cleaned_length:,} chars",
            f"- Bytes saved: {result.cleaning_stats.bytes_saved:,} ({result.cleaning_stats.reduction_percent:.1f}%)",
            "",
            "## Chapter Statistics",
        ]
        
        if result.chapters:
            word_counts = [c.get('word_count', 0) for c in result.chapters]
            report_lines.extend([
                f"- Total words: {sum(word_counts):,}",
                f"- Average chapter: {statistics.mean(word_counts):,.0f} words",
                f"- Min chapter: {min(word_counts):,} words",
                f"- Max chapter: {max(word_counts):,} words",
            ])
        
        if result.warnings:
            report_lines.extend([
                "",
                "## ⚠️ Warnings",
            ])
            for warning in result.warnings:
                report_lines.append(f"- {warning}")
        
        if result.recommendations:
            report_lines.extend([
                "",
                "## 💡 Recommendations",
            ])
            for rec in result.recommendations:
                report_lines.append(f"- {rec}")
        
        return "\n".join(report_lines)


def process_book_enhanced(
    text: str,
    book_id: str,
    mode: str = "standard",
    external_toc: List[str] = None,
) -> PipelineResult:
    """
    Convenience function for enhanced book processing.
    
    Args:
        text: Raw book text
        book_id: Unique book identifier
        mode: 'quick', 'standard', or 'thorough'
        external_toc: Optional chapter titles from external source
        
    Returns:
        PipelineResult with chapters and quality metrics
    """
    processing_mode = ProcessingMode(mode.lower())
    pipeline = EnhancedPipeline(mode=processing_mode)
    return pipeline.process_book(text, book_id, external_toc)
