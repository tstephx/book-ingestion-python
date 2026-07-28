"""
Tests for Enhanced Pipeline

Tests the integrated pipeline including:
- Multi-strategy chapter detection
- Quality validation
- Semantic analysis (when available)
- Recommendations generation
"""

import pytest
from dataclasses import asdict

from book_ingestion.processors.enhanced_pipeline import (
    EnhancedPipeline,
    ProcessingMode,
    PipelineResult,
    ChapterDetectionResult,
    process_book_enhanced
)
from book_ingestion.processors.enhanced_text_cleaner import CleaningStats


class TestProcessingMode:
    """Tests for ProcessingMode enum"""
    
    def test_mode_values(self):
        """Test that all modes exist"""
        assert ProcessingMode.QUICK.value == "quick"
        assert ProcessingMode.STANDARD.value == "standard"
        assert ProcessingMode.THOROUGH.value == "thorough"
    
    def test_mode_from_string(self):
        """Test creating mode from string"""
        assert ProcessingMode("quick") == ProcessingMode.QUICK
        assert ProcessingMode("standard") == ProcessingMode.STANDARD
        assert ProcessingMode("thorough") == ProcessingMode.THOROUGH


class TestEnhancedPipeline:
    """Tests for EnhancedPipeline class"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.pipeline = EnhancedPipeline(mode=ProcessingMode.QUICK)
    
    def test_initialization_quick_mode(self):
        """Test pipeline initialization in quick mode"""
        pipeline = EnhancedPipeline(mode=ProcessingMode.QUICK)
        assert pipeline.mode == ProcessingMode.QUICK
        assert not pipeline.enable_semantic
    
    def test_initialization_standard_mode(self):
        """Test pipeline initialization in standard mode"""
        pipeline = EnhancedPipeline(mode=ProcessingMode.STANDARD)
        assert pipeline.mode == ProcessingMode.STANDARD
        assert pipeline.enable_semantic
    
    def test_initialization_thorough_mode(self):
        """Test pipeline initialization in thorough mode"""
        pipeline = EnhancedPipeline(mode=ProcessingMode.THOROUGH)
        assert pipeline.mode == ProcessingMode.THOROUGH
        assert pipeline.enable_semantic
    
    def test_initialization_custom_target(self):
        """Test pipeline with custom target chapter words"""
        pipeline = EnhancedPipeline(target_chapter_words=5000)
        assert pipeline.target_chapter_words == 5000
    
    def test_default_target_words(self):
        """Test default target chapter words"""
        pipeline = EnhancedPipeline()
        assert pipeline.target_chapter_words == pipeline.IDEAL_CHAPTER_WORDS

    def test_anchor_chapters_reapply_size_limit_after_cleaning(self, monkeypatch):
        """Cleaning must not leave stored EPUB chapters over the quality cap."""
        from book_ingestion.converters.epub_types import (
            AnchorLocation,
            EnhancedTOC,
            SplitPoint,
        )
        from book_ingestion.processors.chapter_splitter import ChapterSplitter

        monkeypatch.setattr(ChapterSplitter, "_QG_MAX_CHAPTER_WORDS", 10)
        monkeypatch.setattr(ChapterSplitter, "_QG_MIN_CHAPTERS", 3)

        lines = []
        specs = []
        for index, title in enumerate(
            ["1: First Region", "2: Second Region", "3: Third Region"]
        ):
            line_index = len(lines)
            lines.append(title)
            lines.append("one—two " * 8)
            specs.append((line_index, title, f"chapter-{index + 1}.xhtml"))
        text = "\n".join(lines)

        enhanced_toc = EnhancedTOC(
            split_points=[
                SplitPoint(
                    title=title,
                    href=href,
                    depth=0,
                    spine_index=index,
                )
                for index, (_, title, href) in enumerate(specs)
            ],
            spine_files=[href for _, _, href in specs],
            anchor_map={
                href: AnchorLocation(
                    href=href,
                    line_index=line_index,
                    char_offset=text.find(title),
                    fingerprint=title,
                )
                for line_index, title, href in specs
            },
        )

        result = self.pipeline.process_book(
            text,
            "cleaned-anchor-book",
            enhanced_toc=enhanced_toc,
        )

        assert all(chapter["word_count"] <= 10 for chapter in result.chapters)
        assert len({chapter["title"] for chapter in result.chapters}) == len(
            result.chapters
        )


class TestPipelineResult:
    """Tests for PipelineResult dataclass"""
    
    def create_mock_result(
        self,
        valid: bool = True,
        quality_score: int = 80,
        confidence: float = 0.8,
        warnings: list = None
    ) -> PipelineResult:
        """Create a mock PipelineResult for testing"""
        from book_ingestion.processors.chapter_validator import ValidationResult
        from book_ingestion.processors.profiler import BookProfile, QualityReport
        
        cleaning_stats = CleaningStats(
            original_length=10000,
            cleaned_length=9500
        )
        
        validation_result = ValidationResult(
            is_valid=valid,
            warnings=warnings or [],
            errors=[]
        )
        
        profile = BookProfile(
            book_id="test-book",
            total_words=50000,
            total_chapters=10,
            avg_chapter_words=5000,
            chapter_word_variance=1000000,
            min_chapter_words=3000,
            max_chapter_words=8000,
            estimated_tokens=66666,
            metadata_completeness=0.8,
            encoding_issues=0,
            chapters_under_threshold=0,
            chapters_over_threshold=0
        )
        
        quality_report = QualityReport(
            profile=profile,
            quality_score=quality_score,
            warnings=[],
            info=[]
        )
        
        return PipelineResult(
            cleaned_text="Sample cleaned text",
            chapters=[{"title": "Chapter 1", "word_count": 5000}],
            cleaning_stats=cleaning_stats,
            validation_result=validation_result,
            quality_report=quality_report,
            detection_method="toc",
            detection_confidence=confidence,
            warnings=warnings or [],
            recommendations=[]
        )
    
    def test_is_valid_true(self):
        """Test is_valid property when all checks pass"""
        result = self.create_mock_result(valid=True, quality_score=80)
        assert result.is_valid
    
    def test_is_valid_false_validation(self):
        """Test is_valid when validation fails"""
        result = self.create_mock_result(valid=False, quality_score=80)
        assert not result.is_valid
    
    def test_is_valid_false_quality(self):
        """Test is_valid when quality score is too low"""
        result = self.create_mock_result(valid=True, quality_score=40)
        assert not result.is_valid
    
    def test_needs_review_warnings(self):
        """Test needs_review when there are warnings"""
        result = self.create_mock_result(warnings=["Some warning"])
        assert result.needs_review
    
    def test_needs_review_low_confidence(self):
        """Test needs_review when confidence is low"""
        result = self.create_mock_result(confidence=0.5)
        assert result.needs_review
    
    def test_needs_review_low_quality(self):
        """Test needs_review when quality is moderate"""
        result = self.create_mock_result(quality_score=60)
        assert result.needs_review
    
    def test_no_review_needed(self):
        """Test when no review is needed"""
        result = self.create_mock_result(
            valid=True,
            quality_score=90,
            confidence=0.9,
            warnings=[]
        )
        assert not result.needs_review


class TestChapterDetectionResult:
    """Tests for ChapterDetectionResult dataclass"""
    
    def test_basic_result(self):
        """Test basic detection result creation"""
        result = ChapterDetectionResult(
            chapters=[{"title": "Chapter 1"}],
            method="toc",
            confidence=0.9,
            toc_chapters_found=5,
            semantic_boundaries_found=0,
            merge_suggestions=[]
        )
        
        assert result.method == "toc"
        assert result.confidence == 0.9
        assert len(result.chapters) == 1
    
    def test_with_merge_suggestions(self):
        """Test detection result with merge suggestions"""
        result = ChapterDetectionResult(
            chapters=[{"title": "Ch 1"}, {"title": "Ch 2"}],
            method="heuristic_merged",
            confidence=0.7,
            toc_chapters_found=0,
            semantic_boundaries_found=2,
            merge_suggestions=[(0, 1, "Both chapters small")]
        )
        
        assert len(result.merge_suggestions) == 1
        assert "small" in result.merge_suggestions[0][2]


class TestProcessBookEnhanced:
    """Tests for the convenience function"""
    
    def test_process_simple_text(self):
        """Test processing simple text"""
        text = """
Chapter 1: Introduction

This is the first chapter of the book. It contains some introductory
content that sets up the rest of the material. The chapter goes on
for several paragraphs to ensure we have enough content.

Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do
eiusmod tempor incididunt ut labore et dolore magna aliqua.

Chapter 2: Main Content

This is the second chapter with the main content. It contains
detailed explanations and examples.

More content in this chapter to make it longer.
"""
        # Repeat content to get reasonable word count
        text = text * 50
        
        result = process_book_enhanced(text, "test-book", mode="quick")
        
        assert isinstance(result, PipelineResult)
        assert result.cleaned_text
        assert len(result.chapters) > 0
    
    def test_process_with_external_toc(self):
        """Test processing with external TOC"""
        text = "Some book content " * 1000
        external_toc = ["Chapter 1: Introduction", "Chapter 2: Content"]
        
        result = process_book_enhanced(
            text,
            "test-book",
            mode="quick",
            external_toc=external_toc
        )
        
        assert isinstance(result, PipelineResult)


class TestEnhancedPipelineIntegration:
    """Integration tests for the enhanced pipeline"""
    
    @pytest.fixture
    def sample_book_text(self):
        """Generate sample book text for testing"""
        chapters = []
        for i in range(1, 6):
            chapter_content = f"""
Chapter {i}: Topic Number {i}

This is chapter {i} of our test book. It contains information about
topic {i} and related subjects. The chapter includes multiple paragraphs
to ensure proper word count for testing.

Section {i}.1: First Section

Here we discuss the first aspect of topic {i}. This section provides
detailed explanations and examples to illustrate the concepts.

Section {i}.2: Second Section

This section covers additional material related to topic {i}. We explore
various applications and use cases.

Summary of chapter {i}. This wraps up the main points covered.
"""
            chapters.append(chapter_content)
        
        return "\n\n".join(chapters) * 10  # Repeat for word count
    
    def test_full_pipeline_quick(self, sample_book_text):
        """Test full pipeline in quick mode"""
        pipeline = EnhancedPipeline(mode=ProcessingMode.QUICK)
        result = pipeline.process_book(sample_book_text, "integration-test")
        
        assert result.cleaned_text
        assert len(result.chapters) > 0
        assert result.detection_method
        assert 0 <= result.detection_confidence <= 1
        assert result.quality_report.quality_score >= 0
    
    def test_full_pipeline_standard(self, sample_book_text):
        """Test full pipeline in standard mode"""
        pipeline = EnhancedPipeline(mode=ProcessingMode.STANDARD)
        result = pipeline.process_book(sample_book_text, "integration-test")
        
        assert result.cleaned_text
        assert result.validation_result is not None
        assert result.quality_report is not None
    
    def test_report_generation(self, sample_book_text):
        """Test that report generation works"""
        pipeline = EnhancedPipeline(mode=ProcessingMode.QUICK)
        result = pipeline.process_book(sample_book_text, "integration-test")
        
        report = pipeline.generate_report(result)
        
        assert "# Book Processing Report" in report
        assert "Summary" in report
        assert "Chapters detected:" in report
        assert "Quality score:" in report
