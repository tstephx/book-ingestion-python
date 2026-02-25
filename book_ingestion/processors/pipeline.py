"""Resumable processing pipeline with checkpoints"""

import hashlib
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from ..storage.database import BookDatabase
from ..utils.config import Config
from .text_cleaner import TextCleaner
from .chapter_splitter import ChapterSplitter
from .metadata_extractor import MetadataExtractor


class ProcessingStage(Enum):
    """Processing pipeline stages"""
    PENDING = "pending"
    CONVERTING = "converting"
    CLEANING = "cleaning"
    SPLITTING = "splitting"
    SAVING = "saving"
    COMPLETED = "completed"
    FAILED = "failed"

    def __lt__(self, other):
        if not isinstance(other, ProcessingStage):
            return NotImplemented
        order = list(ProcessingStage)
        return order.index(self) < order.index(other)

    def __le__(self, other):
        return self == other or self < other


@dataclass
class ProcessingCheckpoint:
    """Checkpoint state for resumable processing"""
    book_id: str
    stage: ProcessingStage
    source_hash: str
    source_file: Optional[str] = None
    raw_text_path: Optional[str] = None
    chapters: Optional[List[Dict]] = None
    metadata: Optional[Dict] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage"""
        return {
            'book_id': self.book_id,
            'stage': self.stage.value,
            'source_hash': self.source_hash,
            'source_file': self.source_file,
            'raw_text_path': self.raw_text_path,
            'chapters': self.chapters,
            'error': self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProcessingCheckpoint':
        """Create from dictionary (database row)"""
        return cls(
            book_id=data['book_id'],
            stage=ProcessingStage(data['stage']),
            source_hash=data['source_hash'],
            source_file=data.get('source_file'),
            raw_text_path=data.get('raw_text_path'),
            chapters=data.get('chapters'),
            error=data.get('error'),
        )


@dataclass
class PipelineResult:
    """Result of pipeline processing"""
    success: bool
    checkpoint: ProcessingCheckpoint
    book_id: Optional[str] = None
    chapters: Optional[List[Dict]] = None
    metadata: Optional[Dict] = None
    error: Optional[str] = None
    resumed: bool = False


class ProcessingPipeline:
    """Resumable processing pipeline with checkpoints"""

    def __init__(self, db: BookDatabase, config: Config,
                 progress_callback: Optional[Callable[[ProcessingStage, str], None]] = None):
        self.db = db
        self.config = config
        self.progress_callback = progress_callback

        # Initialize processors
        self.cleaner = TextCleaner(config)
        self.splitter = ChapterSplitter(config)
        self.metadata_extractor = MetadataExtractor()

        # Converter will be set based on file type
        self._converter = None

    def _report_progress(self, stage: ProcessingStage, message: str):
        """Report progress if callback is set"""
        if self.progress_callback:
            self.progress_callback(stage, message)

    def _calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file for change detection"""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _get_converter(self, file_path: Path):
        """Get appropriate converter for file type"""
        suffix = file_path.suffix.lower()
        if suffix == '.pdf':
            from ..converters.pdf_converter import PDFConverter
            return PDFConverter()
        elif suffix == '.epub':
            from ..converters.epub_converter import EPUBConverter
            return EPUBConverter()
        else:
            raise ValueError(f"Unsupported file format: {suffix}")

    def process(self, file_path: Path, force: bool = False) -> PipelineResult:
        """
        Process a book file with checkpoint support.

        Args:
            file_path: Path to book file (PDF or EPUB)
            force: If True, reprocess even if already completed

        Returns:
            PipelineResult with processing outcome
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Calculate source hash for change detection
        source_hash = self._calculate_hash(file_path)

        # Check for existing checkpoint
        existing = self.db.get_checkpoint(source_hash)
        resumed = False

        if existing:
            checkpoint = ProcessingCheckpoint.from_dict(existing)

            # Skip if already completed (unless force=True)
            if checkpoint.stage == ProcessingStage.COMPLETED and not force:
                return PipelineResult(
                    success=True,
                    checkpoint=checkpoint,
                    book_id=checkpoint.book_id,
                    chapters=checkpoint.chapters,
                    resumed=True
                )

            resumed = True
            self._report_progress(checkpoint.stage, f"Resuming from {checkpoint.stage.value}")
        else:
            # Create new checkpoint
            checkpoint = ProcessingCheckpoint(
                book_id=str(uuid.uuid4()),
                stage=ProcessingStage.PENDING,
                source_hash=source_hash,
                source_file=str(file_path)
            )

        try:
            # Stage 1: Converting
            if checkpoint.stage <= ProcessingStage.CONVERTING:
                checkpoint = self._convert(file_path, checkpoint)
                self.db.save_checkpoint(checkpoint.to_dict())

            # Stage 2: Cleaning
            if checkpoint.stage <= ProcessingStage.CLEANING:
                checkpoint = self._clean(checkpoint)
                self.db.save_checkpoint(checkpoint.to_dict())

            # Stage 3: Splitting
            if checkpoint.stage <= ProcessingStage.SPLITTING:
                checkpoint = self._split(checkpoint)
                self.db.save_checkpoint(checkpoint.to_dict())

            # Stage 4: Saving
            if checkpoint.stage <= ProcessingStage.SAVING:
                checkpoint = self._save(checkpoint)
                self.db.save_checkpoint(checkpoint.to_dict())

            return PipelineResult(
                success=True,
                checkpoint=checkpoint,
                book_id=checkpoint.book_id,
                chapters=checkpoint.chapters,
                metadata=checkpoint.metadata,
                resumed=resumed
            )

        except Exception as e:
            checkpoint.stage = ProcessingStage.FAILED
            checkpoint.error = str(e)
            self.db.save_checkpoint(checkpoint.to_dict())

            return PipelineResult(
                success=False,
                checkpoint=checkpoint,
                error=str(e),
                resumed=resumed
            )

    def _convert(self, file_path: Path, checkpoint: ProcessingCheckpoint) -> ProcessingCheckpoint:
        """Convert file to text"""
        self._report_progress(ProcessingStage.CONVERTING, "Converting to text...")

        converter = self._get_converter(file_path)
        result = converter.convert(str(file_path))

        if not result['success']:
            raise RuntimeError(f"Conversion failed: {result.get('error', 'Unknown error')}")

        # Save raw text to temp location
        raw_text_dir = Path(self.config.output_dir) / checkpoint.book_id / 'raw'
        raw_text_dir.mkdir(parents=True, exist_ok=True)
        raw_text_path = raw_text_dir / 'converted.txt'

        with open(raw_text_path, 'w', encoding='utf-8') as f:
            f.write(result['text'])

        # Extract initial metadata
        checkpoint.metadata = result.get('metadata', {})
        checkpoint.raw_text_path = str(raw_text_path)
        checkpoint.stage = ProcessingStage.CONVERTING
        checkpoint.source_file = str(file_path)

        return checkpoint

    def _clean(self, checkpoint: ProcessingCheckpoint) -> ProcessingCheckpoint:
        """Clean the converted text"""
        self._report_progress(ProcessingStage.CLEANING, "Cleaning text...")

        # Read raw text
        with open(checkpoint.raw_text_path, 'r', encoding='utf-8') as f:
            raw_text = f.read()

        # Clean text
        result = self.cleaner.clean_with_stats(raw_text)
        cleaned_text = result['text']

        # Save cleaned text
        cleaned_path = Path(checkpoint.raw_text_path).parent / 'original.txt'
        with open(cleaned_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_text)

        # Update metadata with word count
        if checkpoint.metadata is None:
            checkpoint.metadata = {}
        checkpoint.metadata['word_count'] = len(cleaned_text.split())

        checkpoint.stage = ProcessingStage.CLEANING

        return checkpoint

    def _split(self, checkpoint: ProcessingCheckpoint) -> ProcessingCheckpoint:
        """Split text into chapters"""
        self._report_progress(ProcessingStage.SPLITTING, "Detecting chapters...")

        # Read cleaned text
        cleaned_path = Path(checkpoint.raw_text_path).parent / 'original.txt'
        with open(cleaned_path, 'r', encoding='utf-8') as f:
            cleaned_text = f.read()

        # Split into chapters
        result = self.splitter.split_with_stats(cleaned_text, checkpoint.book_id)
        checkpoint.chapters = result['chapters']

        # Extract/update metadata
        metadata = self.metadata_extractor.extract(
            cleaned_text,
            checkpoint.source_file,
            checkpoint.metadata
        )
        metadata['id'] = checkpoint.book_id
        metadata['source_file'] = checkpoint.source_file
        checkpoint.metadata = metadata

        checkpoint.stage = ProcessingStage.SPLITTING

        return checkpoint

    def _save(self, checkpoint: ProcessingCheckpoint) -> ProcessingCheckpoint:
        """Save to database and file system"""
        self._report_progress(ProcessingStage.SAVING, "Saving to storage...")

        from ..storage.file_writer import FileWriter

        # Read cleaned text for file writing
        cleaned_path = Path(checkpoint.raw_text_path).parent / 'original.txt'
        with open(cleaned_path, 'r', encoding='utf-8') as f:
            cleaned_text = f.read()

        # Set word_count from chapter sum (authoritative source)
        checkpoint.metadata['word_count'] = sum(
            ch.get('word_count', 0) for ch in checkpoint.chapters
        )

        # Insert book record
        self.db.insert_book(checkpoint.metadata)

        # Write files
        writer = FileWriter(self.config.output_dir)
        writer.write_book(checkpoint.metadata, checkpoint.chapters, cleaned_text)

        # Insert chapter records
        for chapter in checkpoint.chapters:
            self.db.insert_chapter(chapter)

        # Update status
        self.db.update_book_status(checkpoint.book_id, 'completed')

        checkpoint.stage = ProcessingStage.COMPLETED

        return checkpoint

    def get_incomplete_jobs(self) -> List[ProcessingCheckpoint]:
        """Get all incomplete processing jobs"""
        rows = self.db.get_incomplete_checkpoints()
        return [ProcessingCheckpoint.from_dict(row) for row in rows]

    def resume_job(self, source_hash: str) -> Optional[PipelineResult]:
        """Resume a specific incomplete job by source hash"""
        checkpoint_data = self.db.get_checkpoint(source_hash)
        if not checkpoint_data:
            return None

        checkpoint = ProcessingCheckpoint.from_dict(checkpoint_data)
        if not checkpoint.source_file:
            return PipelineResult(
                success=False,
                checkpoint=checkpoint,
                error="Source file path not found in checkpoint"
            )

        source_path = Path(checkpoint.source_file)
        if not source_path.exists():
            return PipelineResult(
                success=False,
                checkpoint=checkpoint,
                error=f"Source file no longer exists: {source_path}"
            )

        return self.process(source_path)

    def clear_checkpoint(self, source_hash: str):
        """Clear a checkpoint to allow reprocessing"""
        self.db.delete_checkpoint(source_hash)
