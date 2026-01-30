"""
Book Processing Modules

This package contains processors for book ingestion:
- chapter_detector: Detect chapter boundaries
- chapter_splitter: Split text into chapters
- chapter_validator: Validate chapter detection quality
- text_cleaner: Clean and normalize text
- enhanced_text_cleaner: LLM-optimized text cleaning
- profiler: Generate quality profiles
- semantic_chunker: Semantic analysis and validation
- chunk_merger: Merge over-fragmented chapters
- recursive_splitter: LangChain-style recursive splitting
- enhanced_pipeline: Full processing pipeline with validation
"""

from .chapter_splitter import ChapterSplitter
from .chapter_detector import (
    ChapterCandidate,
    CandidateExtractor,
    CandidateScorer,
    AnchorMerger,
    DetectionStats,
    MatchType,
)
from .chapter_validator import ChapterValidator, ValidationResult
from .text_cleaner import TextCleaner, CleaningStats
from .profiler import DataProfiler, BookProfile, QualityReport
from .code_block_detector import CodeBlockDetector

# New modules for improved chunking
from .semantic_chunker import (
    validate_chunking,
    RecursiveTextSplitter as SemanticRecursiveSplitter,
    SemanticChunker,
    ChapterBoundaryValidator,
    SemanticBoundary,
    ChapterValidation,
    SemanticChunkingResult,
)
from .chunk_merger import (
    ChapterMerger,
    MergeCandidate,
    MergeResult,
    merge_undersized_chapters,
)

# Enhanced LangChain-style processors
from .recursive_splitter import (
    RecursiveTextSplitter,
    ChapterAwareSplitter,
    TextChunk,
    SplitResult,
    SeparatorType,
)
from .enhanced_text_cleaner import (
    EnhancedTextCleaner,
    CleaningStats as EnhancedCleaningStats,
    clean_text_for_llm,
)
from .enhanced_pipeline import (
    EnhancedPipeline,
    ProcessingMode,
    PipelineResult,
    ChapterDetectionResult,
    process_book_enhanced,
)

__all__ = [
    # Core processors
    'ChapterSplitter',
    'ChapterCandidate',
    'CandidateExtractor',
    'CandidateScorer',
    'AnchorMerger',
    'DetectionStats',
    'MatchType',
    'ChapterValidator',
    'ValidationResult',
    'TextCleaner',
    'CleaningStats',
    'DataProfiler',
    'BookProfile',
    'QualityReport',
    'CodeBlockDetector',
    
    # Semantic chunking
    'validate_chunking',
    'SemanticRecursiveSplitter',
    'SemanticChunker',
    'ChapterBoundaryValidator',
    'SemanticBoundary',
    'ChapterValidation',
    'SemanticChunkingResult',
    
    # Chunk merging
    'ChapterMerger',
    'MergeCandidate',
    'MergeResult',
    'merge_undersized_chapters',
    
    # LangChain-style recursive splitting
    'RecursiveTextSplitter',
    'ChapterAwareSplitter',
    'TextChunk',
    'SplitResult',
    'SeparatorType',
    
    # Enhanced text cleaning
    'EnhancedTextCleaner',
    'EnhancedCleaningStats',
    'clean_text_for_llm',
    
    # Enhanced pipeline
    'EnhancedPipeline',
    'ProcessingMode',
    'PipelineResult',
    'ChapterDetectionResult',
    'process_book_enhanced',
]
