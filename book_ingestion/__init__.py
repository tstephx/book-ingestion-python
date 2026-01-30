"""
Book Ingestion - A library for ingesting, processing, and extracting metadata from ebooks.

Core API:
    from book_ingestion import EnhancedPipeline, PipelineResult, ProcessingMode
    from book_ingestion import DataProfiler, BookProfile, QualityReport

Advanced (lazy-loaded):
    from book_ingestion import PDFConverter, EPUBConverter
    from book_ingestion import SemanticChunker
    from book_ingestion import BookIngestionApp
"""

__version__ = "0.1.0"

# Core exports - always available
from book_ingestion.processors.enhanced_pipeline import (
    EnhancedPipeline,
    PipelineResult,
    ProcessingMode,
    ChapterDetectionResult,
)
from book_ingestion.processors.profiler import (
    DataProfiler,
    BookProfile,
    QualityReport,
)

# Lazy loading for heavy dependencies
def __getattr__(name: str):
    """Lazy load heavy modules to avoid importing torch/spacy at import time."""

    # Converters (require pymupdf, ebooklib)
    if name == "PDFConverter":
        from book_ingestion.converters.pdf_converter import PDFConverter
        return PDFConverter

    if name == "EPUBConverter":
        from book_ingestion.converters.epub_converter import EPUBConverter
        return EPUBConverter

    # Semantic chunking (requires torch/sentence-transformers)
    if name == "SemanticChunker":
        from book_ingestion.processors.semantic_chunker import SemanticChunker
        return SemanticChunker

    # Bootstrap/app (composition root)
    if name == "BookIngestionApp":
        from book_ingestion.bootstrap import BookIngestionApp
        return BookIngestionApp

    # Chapter processing
    if name == "ChapterSplitter":
        from book_ingestion.processors.chapter_splitter import ChapterSplitter
        return ChapterSplitter

    if name == "ChapterValidator":
        from book_ingestion.processors.chapter_validator import ChapterValidator
        return ChapterValidator

    if name == "TextCleaner":
        from book_ingestion.processors.text_cleaner import TextCleaner
        return TextCleaner

    if name == "EnhancedTextCleaner":
        from book_ingestion.processors.enhanced_text_cleaner import EnhancedTextCleaner
        return EnhancedTextCleaner

    # Metadata
    if name == "MetadataExtractor":
        from book_ingestion.processors.metadata_extractor import MetadataExtractor
        return MetadataExtractor

    # Storage
    if name == "BookDatabase":
        from book_ingestion.storage.database import BookDatabase
        return BookDatabase

    if name == "FileWriter":
        from book_ingestion.storage.file_writer import FileWriter
        return FileWriter

    # Config
    if name == "Config":
        from book_ingestion.utils.config import Config
        return Config

    raise AttributeError(f"module 'book_ingestion' has no attribute {name!r}")


__all__ = [
    # Version
    "__version__",
    # Core (always loaded)
    "EnhancedPipeline",
    "PipelineResult",
    "ProcessingMode",
    "ChapterDetectionResult",
    "DataProfiler",
    "BookProfile",
    "QualityReport",
    # Lazy-loaded
    "PDFConverter",
    "EPUBConverter",
    "SemanticChunker",
    "BookIngestionApp",
    "ChapterSplitter",
    "ChapterValidator",
    "TextCleaner",
    "EnhancedTextCleaner",
    "MetadataExtractor",
    "BookDatabase",
    "FileWriter",
    "Config",
]
