"""Tests for processing pipeline with checkpoints"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from book_ingestion.processors.pipeline import (
    ProcessingStage,
    ProcessingCheckpoint,
    ProcessingPipeline,
    PipelineResult
)
from book_ingestion.storage.database import BookDatabase
from book_ingestion.utils.config import Config


class TestProcessingStage:
    def test_stage_ordering(self):
        """Stages should be comparable"""
        assert ProcessingStage.PENDING < ProcessingStage.CONVERTING
        assert ProcessingStage.CONVERTING < ProcessingStage.CLEANING
        assert ProcessingStage.CLEANING < ProcessingStage.SPLITTING
        assert ProcessingStage.SPLITTING < ProcessingStage.SAVING
        assert ProcessingStage.SAVING < ProcessingStage.COMPLETED

    def test_stage_equality(self):
        assert ProcessingStage.PENDING <= ProcessingStage.PENDING
        assert ProcessingStage.PENDING <= ProcessingStage.CONVERTING


class TestProcessingCheckpoint:
    def test_checkpoint_creation(self):
        checkpoint = ProcessingCheckpoint(
            book_id="test-123",
            stage=ProcessingStage.PENDING,
            source_hash="abc123"
        )
        assert checkpoint.book_id == "test-123"
        assert checkpoint.stage == ProcessingStage.PENDING
        assert checkpoint.source_hash == "abc123"

    def test_checkpoint_to_dict(self):
        checkpoint = ProcessingCheckpoint(
            book_id="test-123",
            stage=ProcessingStage.CLEANING,
            source_hash="abc123",
            raw_text_path="/tmp/raw.txt"
        )
        data = checkpoint.to_dict()
        assert data['book_id'] == "test-123"
        assert data['stage'] == "cleaning"
        assert data['source_hash'] == "abc123"
        assert data['raw_text_path'] == "/tmp/raw.txt"

    def test_checkpoint_from_dict(self):
        data = {
            'book_id': "test-456",
            'stage': "splitting",
            'source_hash': "def456",
            'raw_text_path': "/tmp/raw.txt",
            'chapters': [{'id': '1', 'title': 'Test'}]
        }
        checkpoint = ProcessingCheckpoint.from_dict(data)
        assert checkpoint.book_id == "test-456"
        assert checkpoint.stage == ProcessingStage.SPLITTING
        assert checkpoint.chapters == [{'id': '1', 'title': 'Test'}]


class TestProcessingPipeline:
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = BookDatabase(str(db_path))
            db.initialize()
            yield db, tmpdir
            db.close()

    @pytest.fixture
    def mock_config(self, temp_db):
        """Create mock config"""
        db, tmpdir = temp_db
        config = MagicMock()
        config.output_dir = tmpdir
        config.database_path = str(Path(tmpdir) / "test.db")
        config.text_cleaning = {
            'normalize_whitespace': True,
            'remove_page_numbers': True
        }
        config.section_splitting = {'enabled': False}
        return config

    def test_calculate_hash(self, temp_db, mock_config):
        """Should calculate consistent file hash"""
        db, tmpdir = temp_db
        pipeline = ProcessingPipeline(db, mock_config)

        # Create a test file
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("Hello World")

        hash1 = pipeline._calculate_hash(test_file)
        hash2 = pipeline._calculate_hash(test_file)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length

    def test_hash_changes_with_content(self, temp_db, mock_config):
        """Hash should change when file content changes"""
        db, tmpdir = temp_db
        pipeline = ProcessingPipeline(db, mock_config)

        test_file = Path(tmpdir) / "test.txt"

        test_file.write_text("Hello World")
        hash1 = pipeline._calculate_hash(test_file)

        test_file.write_text("Hello World Modified")
        hash2 = pipeline._calculate_hash(test_file)

        assert hash1 != hash2

    def test_checkpoint_persistence(self, temp_db, mock_config):
        """Checkpoints should persist to database"""
        db, tmpdir = temp_db

        checkpoint = {
            'book_id': 'test-123',
            'stage': 'converting',
            'source_hash': 'hash123',
            'raw_text_path': '/tmp/test.txt',
            'chapters': None,
            'error': None
        }

        db.save_checkpoint(checkpoint)
        loaded = db.get_checkpoint('hash123')

        assert loaded is not None
        assert loaded['book_id'] == 'test-123'
        assert loaded['stage'] == 'converting'

    def test_checkpoint_update(self, temp_db, mock_config):
        """Checkpoints should be updateable"""
        db, tmpdir = temp_db

        # Save initial checkpoint
        checkpoint = {
            'book_id': 'test-123',
            'stage': 'converting',
            'source_hash': 'hash123',
        }
        db.save_checkpoint(checkpoint)

        # Update checkpoint
        checkpoint['stage'] = 'cleaning'
        db.save_checkpoint(checkpoint)

        loaded = db.get_checkpoint('hash123')
        assert loaded['stage'] == 'cleaning'

    def test_get_incomplete_checkpoints(self, temp_db, mock_config):
        """Should retrieve incomplete checkpoints"""
        db, tmpdir = temp_db

        # Save one completed and one incomplete
        db.save_checkpoint({
            'book_id': 'complete-1',
            'stage': 'completed',
            'source_hash': 'hash1',
        })
        db.save_checkpoint({
            'book_id': 'incomplete-1',
            'stage': 'cleaning',
            'source_hash': 'hash2',
        })

        incomplete = db.get_incomplete_checkpoints()
        assert len(incomplete) == 1
        assert incomplete[0]['book_id'] == 'incomplete-1'

    def test_progress_callback(self, temp_db, mock_config):
        """Progress callback should be called"""
        db, tmpdir = temp_db
        progress_calls = []

        def on_progress(stage, message):
            progress_calls.append((stage, message))

        pipeline = ProcessingPipeline(db, mock_config, progress_callback=on_progress)

        # Trigger a progress report
        pipeline._report_progress(ProcessingStage.CONVERTING, "Test message")

        assert len(progress_calls) == 1
        assert progress_calls[0][0] == ProcessingStage.CONVERTING
        assert progress_calls[0][1] == "Test message"

    def test_file_not_found_raises(self, temp_db, mock_config):
        """Should raise FileNotFoundError for missing files"""
        db, tmpdir = temp_db
        pipeline = ProcessingPipeline(db, mock_config)

        with pytest.raises(FileNotFoundError):
            pipeline.process(Path("/nonexistent/file.pdf"))

    def test_unsupported_format_raises(self, temp_db, mock_config):
        """Should raise ValueError for unsupported formats"""
        db, tmpdir = temp_db
        pipeline = ProcessingPipeline(db, mock_config)

        test_file = Path(tmpdir) / "test.docx"
        test_file.write_text("test")

        result = pipeline.process(test_file)
        assert result.success is False
        assert "Unsupported file format" in result.error

    def test_clear_checkpoint(self, temp_db, mock_config):
        """Should be able to clear a checkpoint"""
        db, tmpdir = temp_db

        db.save_checkpoint({
            'book_id': 'test-123',
            'stage': 'cleaning',
            'source_hash': 'hash123',
        })

        db.delete_checkpoint('hash123')
        assert db.get_checkpoint('hash123') is None


class TestSaveStepWordCount:
    def test_save_sets_word_count_from_chapter_sum(self, tmp_path):
        """_save must write sum(chapter.word_count) into books.word_count, not raw text length."""
        import sqlite3
        from book_ingestion.processors.pipeline import (
            ProcessingCheckpoint, ProcessingPipeline, ProcessingStage
        )
        from book_ingestion.storage.database import BookDatabase

        db_path = tmp_path / "test.db"
        db = BookDatabase(str(db_path))
        db.initialize()

        # Write a minimal cleaned text file
        raw_text_path = tmp_path / "raw.txt"
        cleaned_path = tmp_path / "original.txt"
        cleaned_path.write_text("some words here")  # 3 words — must NOT appear in books.word_count

        config = MagicMock()
        config.output_dir = str(tmp_path)
        config.database_path = str(db_path)

        pipeline = ProcessingPipeline.__new__(ProcessingPipeline)
        pipeline.db = db
        pipeline.config = config
        pipeline.progress_callback = None

        chapters = [
            {"id": "c1", "book_id": "b1", "chapter_number": 1, "title": "Ch 1",
             "file_path": "c1.txt", "word_count": 12000},
            {"id": "c2", "book_id": "b1", "chapter_number": 2, "title": "Ch 2",
             "file_path": "c2.txt", "word_count": 8000},
        ]
        checkpoint = ProcessingCheckpoint(
            book_id="b1",
            stage=ProcessingStage.SPLITTING,
            source_hash="x",
            raw_text_path=str(raw_text_path),
        )
        checkpoint.metadata = {"id": "b1", "title": "Test Book", "author": "Author"}
        checkpoint.chapters = chapters

        with patch("book_ingestion.storage.file_writer.FileWriter") as MockWriter:
            MockWriter.return_value.write_book = MagicMock()
            pipeline._save(checkpoint)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT word_count FROM books WHERE id = 'b1'").fetchone()
        conn.close()

        assert row is not None
        assert row[0] == 20000, f"Expected word_count=20000 (sum of chapters), got {row[0]}"


class TestBootstrapWordCount:
    def test_save_to_storage_sets_word_count_from_chapter_sum(self, tmp_path):
        """_save_to_storage must write sum(chapter.word_count) into books.word_count."""
        import sqlite3
        from book_ingestion.bootstrap import BookIngestionApp
        from book_ingestion.processors.pipeline import PipelineResult, ProcessingCheckpoint, ProcessingStage
        from book_ingestion.storage.database import BookDatabase

        db_path = tmp_path / "test.db"
        db = BookDatabase(str(db_path))
        db.initialize()

        config = MagicMock()
        config.output_dir = str(tmp_path)
        config.database_path = str(db_path)

        app = BookIngestionApp.__new__(BookIngestionApp)
        app.config = config
        app._db = db

        chapters = [
            {"id": "c1", "book_id": "b2", "chapter_number": 1, "title": "Ch 1",
             "file_path": "c1.txt", "word_count": 15000},
            {"id": "c2", "book_id": "b2", "chapter_number": 2, "title": "Ch 2",
             "file_path": "c2.txt", "word_count": 5000},
        ]
        checkpoint = ProcessingCheckpoint(
            book_id="b2", stage=ProcessingStage.COMPLETED, source_hash="y"
        )
        pipeline_result = PipelineResult(
            success=True, checkpoint=checkpoint, book_id="b2", chapters=chapters
        )
        metadata = {"id": "b2", "title": "Bootstrap Book", "author": "Author"}

        mock_writer = MagicMock()
        app._get_file_writer = lambda: mock_writer
        app._save_to_storage(metadata, pipeline_result, "cleaned text")

        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT word_count FROM books WHERE id = 'b2'").fetchone()
        conn.close()

        assert row is not None
        assert row[0] == 20000, f"Expected word_count=20000 (sum of chapters), got {row[0]}"


class TestPipelineResult:
    def test_successful_result(self):
        checkpoint = ProcessingCheckpoint(
            book_id="test-123",
            stage=ProcessingStage.COMPLETED,
            source_hash="abc123"
        )
        result = PipelineResult(
            success=True,
            checkpoint=checkpoint,
            book_id="test-123",
            chapters=[{'id': '1'}]
        )
        assert result.success is True
        assert result.book_id == "test-123"
        assert len(result.chapters) == 1

    def test_failed_result(self):
        checkpoint = ProcessingCheckpoint(
            book_id="test-123",
            stage=ProcessingStage.FAILED,
            source_hash="abc123"
        )
        result = PipelineResult(
            success=False,
            checkpoint=checkpoint,
            error="Something went wrong"
        )
        assert result.success is False
        assert result.error == "Something went wrong"
