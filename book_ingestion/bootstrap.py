"""
Composition Root for Book Ingestion Pipeline.

This module provides the BookIngestionApp class which serves as the main
entry point for using book-ingestion as a library. It wires up all
dependencies and provides a clean API for processing books.

Usage:
    from book_ingestion import BookIngestionApp

    # Simple usage
    app = BookIngestionApp.create(db_path="/path/to/books.db")
    result = app.process("/path/to/book.pdf")

    # With LLM fallback
    app = BookIngestionApp.create(
        db_path="/path/to/books.db",
        llm_fallback=my_llm_adapter
    )
    result = app.process("/path/to/book.epub")
"""

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any

from book_ingestion.ports.llm_fallback import (
    LLMFallbackPort,
    LLMFallbackRequest,
    LLMFallbackResponse,
)
from book_ingestion.ports.logger import PipelineLogger
from book_ingestion.ports.repository import BookRepository
from book_ingestion.processors.enhanced_pipeline import (
    EnhancedPipeline,
    PipelineResult,
    ProcessingMode,
)

logger = logging.getLogger(__name__)


@dataclass
class ProcessingConfig:
    """Configuration for book processing."""

    db_path: Path
    output_dir: Optional[Path] = None
    processing_mode: ProcessingMode = ProcessingMode.STANDARD
    llm_fallback_threshold: float = 0.5  # Trigger LLM if confidence below this
    enable_section_splitting: bool = True
    max_tokens_per_section: int = 15000


class DefaultLogger:
    """Default logger implementation using Python's logging."""

    def info(self, message: str, **kwargs: Any) -> None:
        logger.info(message, extra=kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        logger.warning(message, extra=kwargs)

    def error(
        self, message: str, error: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        logger.error(message, exc_info=error, extra=kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        logger.debug(message, extra=kwargs)

    def step_started(self, step_name: str, **kwargs: Any) -> None:
        logger.info(f"Step started: {step_name}", extra=kwargs)

    def step_completed(self, step_name: str, **kwargs: Any) -> None:
        logger.info(f"Step completed: {step_name}", extra=kwargs)

    def step_failed(self, step_name: str, error: Exception, **kwargs: Any) -> None:
        logger.error(f"Step failed: {step_name}", exc_info=error, extra=kwargs)


@dataclass
class BookProcessingResult:
    """Result from processing a book through the app."""

    success: bool
    book_id: str
    pipeline_result: Optional[PipelineResult] = None
    error: Optional[str] = None
    llm_fallback_used: bool = False
    llm_fallback_improved: bool = False

    @property
    def quality_score(self) -> int:
        """Get quality score from pipeline result."""
        if self.pipeline_result:
            return self.pipeline_result.quality_report.quality_score
        return 0

    @property
    def detection_confidence(self) -> float:
        """Get detection confidence from pipeline result."""
        if self.pipeline_result:
            return self.pipeline_result.detection_confidence
        return 0.0

    @property
    def needs_review(self) -> bool:
        """Check if result needs manual review."""
        if self.pipeline_result:
            return self.pipeline_result.needs_review
        return True

    @property
    def warnings(self) -> list:
        """Get warnings from pipeline result."""
        if self.pipeline_result:
            return self.pipeline_result.warnings
        return []


class BookIngestionApp:
    """
    Main application class for book ingestion.

    Wires up all components and provides a clean API for processing books.
    Supports optional LLM fallback for low-confidence chapter detection.
    """

    def __init__(
        self,
        config: ProcessingConfig,
        repository: Optional[BookRepository] = None,
        llm_fallback: Optional[LLMFallbackPort] = None,
        pipeline_logger: Optional[PipelineLogger] = None,
    ):
        self.config = config
        self._llm_fallback = llm_fallback
        self._logger = pipeline_logger or DefaultLogger()
        self._repository = repository
        self._pipeline = EnhancedPipeline(mode=config.processing_mode)

        # Lazy-loaded components
        self._db = None
        self._file_writer = None

    @classmethod
    def create(
        cls,
        db_path: str | Path,
        output_dir: Optional[str | Path] = None,
        llm_fallback: Optional[LLMFallbackPort] = None,
        processing_mode: ProcessingMode = ProcessingMode.STANDARD,
        llm_fallback_threshold: float = 0.5,
    ) -> "BookIngestionApp":
        """
        Factory method to create a BookIngestionApp instance.

        Args:
            db_path: Path to the SQLite database
            output_dir: Directory for output files (default: derived from db_path)
            llm_fallback: Optional LLM fallback adapter for low-confidence detection
            processing_mode: Processing thoroughness level
            llm_fallback_threshold: Confidence threshold below which LLM is triggered

        Returns:
            Configured BookIngestionApp instance
        """
        db_path = Path(db_path)
        if output_dir is None:
            output_dir = db_path.parent / "processed"
        else:
            output_dir = Path(output_dir)

        config = ProcessingConfig(
            db_path=db_path,
            output_dir=output_dir,
            processing_mode=processing_mode,
            llm_fallback_threshold=llm_fallback_threshold,
        )

        return cls(config=config, llm_fallback=llm_fallback)

    def _get_db(self):
        """Lazy-load database connection."""
        if self._db is None:
            from book_ingestion.storage.database import BookDatabase

            self._db = BookDatabase(str(self.config.db_path))
        return self._db

    def _get_file_writer(self):
        """Lazy-load file writer."""
        if self._file_writer is None:
            from book_ingestion.storage.file_writer import FileWriter

            self._file_writer = FileWriter(str(self.config.output_dir))
        return self._file_writer

    def process(
        self,
        file_path: str | Path,
        title: Optional[str] = None,
        author: Optional[str] = None,
        book_id: Optional[str] = None,
        save_to_storage: bool = True,
        force_fallback: bool = False,
    ) -> BookProcessingResult:
        """
        Process a book file (PDF or EPUB).

        Args:
            file_path: Path to the book file
            title: Optional title override
            author: Optional author override
            book_id: Optional book ID (generated if not provided)
            save_to_storage: Whether to save results to database/files
            force_fallback: Skip anchor/TOC detection and use fixed-size
                splitting with quality gate (used for pipeline retry)

        Returns:
            BookProcessingResult with processing details
        """
        file_path = Path(file_path)
        book_id = book_id or str(uuid.uuid4())

        self._logger.step_started("book_processing", file_path=str(file_path))

        try:
            # Step 1: Convert to text
            self._logger.step_started("conversion")
            text, metadata = self._convert_book(file_path)
            self._logger.step_completed("conversion")

            # Override metadata with provided values
            if title:
                metadata["title"] = title
            if author:
                metadata["author"] = author
            metadata["id"] = book_id
            metadata["source_file"] = str(file_path)

            # Step 2: Run enhanced pipeline
            self._logger.step_started("pipeline")
            pipeline_result = self._pipeline.process_book(
                text=text,
                book_id=book_id,
                external_toc_titles=metadata.get("toc_titles"),
                enhanced_toc=metadata.get("enhanced_toc"),
                force_fallback=force_fallback,
            )
            self._logger.step_completed("pipeline")

            # Step 3: Check if LLM fallback should be triggered
            llm_fallback_used = False
            llm_fallback_improved = False

            if self._should_trigger_llm_fallback(pipeline_result):
                self._logger.step_started("llm_fallback")
                llm_result = self._attempt_llm_fallback(
                    text=text,
                    pipeline_result=pipeline_result,
                    metadata=metadata,
                )
                if llm_result:
                    llm_fallback_used = True
                    llm_fallback_improved = llm_result.confidence_delta > 0
                    # Apply LLM improvements to pipeline result
                    pipeline_result = self._apply_llm_improvements(
                        pipeline_result, llm_result
                    )
                self._logger.step_completed("llm_fallback")

            # Step 4: Save to storage if requested
            if save_to_storage:
                self._logger.step_started("storage")
                self._save_to_storage(
                    metadata=metadata,
                    pipeline_result=pipeline_result,
                    cleaned_text=pipeline_result.cleaned_text,
                )
                self._logger.step_completed("storage")

            self._logger.step_completed(
                "book_processing", book_id=book_id, success=True
            )

            return BookProcessingResult(
                success=True,
                book_id=book_id,
                pipeline_result=pipeline_result,
                llm_fallback_used=llm_fallback_used,
                llm_fallback_improved=llm_fallback_improved,
            )

        except Exception as e:
            self._logger.step_failed("book_processing", error=e)
            return BookProcessingResult(
                success=False,
                book_id=book_id,
                error=str(e),
            )

    def _convert_book(self, file_path: Path) -> tuple[str, Dict]:
        """Convert book file to text and extract metadata.

        For EPUB files with enhanced parsing enabled, metadata will include
        'enhanced_toc' with split points and anchor map for precise chapter detection.
        """
        ext = file_path.suffix.lower()

        if ext == ".pdf":
            from book_ingestion.converters.pdf_converter import PDFConverter

            converter = PDFConverter()
            result = converter.convert(str(file_path))
        elif ext == ".epub":
            from book_ingestion.converters.epub_converter import EPUBConverter

            converter = EPUBConverter()
            # Use enhanced parsing for precise chapter detection
            result = converter.convert(str(file_path), enhanced=True)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

        if not result["success"]:
            raise RuntimeError(result.get("error", "Conversion failed"))

        metadata = result.get("metadata", {})

        # Pass through enhanced_toc and toc_titles if available
        if "enhanced_toc" in result:
            metadata["enhanced_toc"] = result["enhanced_toc"]
        if "toc_titles" in result:
            metadata["toc_titles"] = result["toc_titles"]

        return result["text"], metadata

    def _should_trigger_llm_fallback(self, result: PipelineResult) -> bool:
        """Determine if LLM fallback should be triggered."""
        if self._llm_fallback is None:
            return False

        # Use the adapter's own logic if available
        if hasattr(self._llm_fallback, "should_trigger"):
            return self._llm_fallback.should_trigger(
                result.detection_confidence, result.detection_method
            )

        # Default: trigger if confidence is below threshold
        return result.detection_confidence < self.config.llm_fallback_threshold

    def _attempt_llm_fallback(
        self,
        text: str,
        pipeline_result: PipelineResult,
        metadata: Dict,
    ) -> Optional[LLMFallbackResponse]:
        """Attempt to improve chapter detection using LLM."""
        if self._llm_fallback is None:
            return None

        # Create request with first 10k chars of text
        request = LLMFallbackRequest(
            text_sample=text[:10000],
            detected_chapters=pipeline_result.chapters,
            detection_confidence=pipeline_result.detection_confidence,
            detection_method=pipeline_result.detection_method,
            book_metadata=metadata,
        )

        try:
            return self._llm_fallback.improve_detection(request)
        except Exception as e:
            self._logger.error("LLM fallback failed", error=e)
            return None

    def _apply_llm_improvements(
        self, result: PipelineResult, llm_response: LLMFallbackResponse
    ) -> PipelineResult:
        """Apply LLM improvements to pipeline result.

        Uses merge/split suggestions to modify original chapters, preserving
        essential fields (id, book_id, content) that the LLM doesn't provide.
        """
        # Apply confidence boost if LLM confirmed or improved
        if llm_response.confidence_delta > 0:
            result.detection_confidence = min(
                1.0, result.detection_confidence + llm_response.confidence_delta
            )
            result.recommendations.extend(llm_response.corrections_made)

        # Don't replace chapters wholesale - LLM suggestions lack required fields
        # (id, book_id, content). Instead, use merge/split suggestions on originals.
        # For now, we just use the confidence boost and recommendations.
        # TODO: Implement proper merge/split using should_merge and should_split

        return result

    def _save_to_storage(
        self,
        metadata: Dict,
        pipeline_result: PipelineResult,
        cleaned_text: str,
    ) -> None:
        """Save processed book to storage."""
        db = self._get_db()
        writer = self._get_file_writer()

        # Roll up chapter word counts before inserting book record
        metadata["word_count"] = sum(
            ch.get("word_count", 0) for ch in pipeline_result.chapters
        )

        # Insert book metadata
        db.insert_book(metadata)

        # Write files
        writer.write_book(metadata, pipeline_result.chapters, cleaned_text)

        # Insert chapters
        for chapter in pipeline_result.chapters:
            db.insert_chapter(chapter)

        # Update status
        db.update_book_status(metadata["id"], "completed")
