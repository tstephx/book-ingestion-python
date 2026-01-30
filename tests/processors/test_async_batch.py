"""Tests for async batch processing"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

from book_ingestion.processors.async_batch import (
    BatchResult,
    BatchSummary,
    AsyncBatchProcessor,
    process_directory,
    _process_single_book
)


def run_async(coro):
    """Helper to run async functions in tests"""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestBatchResult:
    def test_successful_result(self):
        result = BatchResult(
            file_path="/path/to/book.pdf",
            success=True,
            book_id="test-123",
            chapters_count=10,
            word_count=50000,
            processing_time=5.5
        )
        assert result.success is True
        assert result.book_id == "test-123"
        assert result.error is None

    def test_failed_result(self):
        result = BatchResult(
            file_path="/path/to/book.pdf",
            success=False,
            error="Conversion failed"
        )
        assert result.success is False
        assert result.error == "Conversion failed"
        assert result.book_id is None


class TestBatchSummary:
    def test_summary_creation(self):
        results = [
            BatchResult(file_path="a.pdf", success=True, chapters_count=5, word_count=10000),
            BatchResult(file_path="b.pdf", success=True, chapters_count=8, word_count=20000),
            BatchResult(file_path="c.pdf", success=False, error="Failed"),
        ]
        summary = BatchSummary(
            total_books=3,
            successful=2,
            failed=1,
            total_chapters=13,
            total_words=30000,
            total_time=10.5,
            results=results
        )
        assert summary.total_books == 3
        assert summary.successful == 2
        assert summary.failed == 1
        assert summary.total_chapters == 13
        assert summary.total_words == 30000

    def test_success_rate(self):
        summary = BatchSummary(
            total_books=10,
            successful=8,
            failed=2,
            total_chapters=0,
            total_words=0,
            total_time=0
        )
        assert summary.success_rate == 0.8

    def test_success_rate_empty(self):
        summary = BatchSummary(
            total_books=0,
            successful=0,
            failed=0,
            total_chapters=0,
            total_words=0,
            total_time=0
        )
        assert summary.success_rate == 0.0

    def test_get_failures(self):
        results = [
            BatchResult(file_path="a.pdf", success=True),
            BatchResult(file_path="b.pdf", success=False, error="Error 1"),
            BatchResult(file_path="c.pdf", success=False, error="Error 2"),
        ]
        summary = BatchSummary(
            total_books=3,
            successful=1,
            failed=2,
            total_chapters=0,
            total_words=0,
            total_time=0,
            results=results
        )
        failures = summary.get_failures()
        assert len(failures) == 2
        assert all(not f.success for f in failures)


class TestAsyncBatchProcessor:
    def test_init(self):
        processor = AsyncBatchProcessor(max_workers=2)
        assert processor.max_workers == 2
        assert processor._executor is None

    def test_context_manager(self):
        with AsyncBatchProcessor(max_workers=2) as processor:
            assert processor.max_workers == 2

    def test_summarize_results(self):
        processor = AsyncBatchProcessor()
        results = [
            BatchResult(file_path="a.pdf", success=True, chapters_count=5, word_count=10000),
            BatchResult(file_path="b.pdf", success=False, error="Failed"),
        ]
        summary = processor._summarize_results(results, 5.0)

        assert summary.total_books == 2
        assert summary.successful == 1
        assert summary.failed == 1
        assert summary.total_chapters == 5
        assert summary.total_words == 10000
        assert summary.total_time == 5.0

    def test_process_books_with_mock(self):
        """Test processing with mocked single book processor"""
        with patch('book_ingestion.processors.async_batch._process_single_book') as mock_process:
            mock_process.return_value = BatchResult(
                file_path="test.pdf",
                success=True,
                book_id="test-123",
                chapters_count=10,
                word_count=50000
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                # Create test files
                test_file = Path(tmpdir) / "test.pdf"
                test_file.write_text("fake pdf")

                processor = AsyncBatchProcessor(max_workers=2)
                # Use ThreadPoolExecutor for testing since ProcessPoolExecutor
                # can have issues with mock
                from concurrent.futures import ThreadPoolExecutor
                processor._executor = ThreadPoolExecutor(max_workers=2)

                async def run_test():
                    return await processor.process_books([test_file])

                summary = run_async(run_test())
                processor.shutdown()

                # Verify we processed 1 book
                assert summary.total_books == 1

    def test_sync_process_with_mock(self):
        """Test synchronous processing with mock"""
        with patch('book_ingestion.processors.async_batch._process_single_book') as mock_process:
            mock_process.return_value = BatchResult(
                file_path="test.pdf",
                success=True,
                book_id="test-123",
                chapters_count=10,
                word_count=50000
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                # Create test files
                test_files = []
                for i in range(3):
                    f = Path(tmpdir) / f"test{i}.pdf"
                    f.write_text("fake pdf")
                    test_files.append(f)

                processor = AsyncBatchProcessor(max_workers=2)
                summary = processor.process_books_sync(test_files)

                assert summary.total_books == 3
                assert summary.successful == 3
                assert summary.failed == 0

    def test_sync_process_with_callback(self):
        """Test that progress callback is called"""
        callback_calls = []

        def on_progress(path, result):
            callback_calls.append((path, result))

        with patch('book_ingestion.processors.async_batch._process_single_book') as mock_process:
            mock_process.return_value = BatchResult(
                file_path="test.pdf",
                success=True
            )

            with tempfile.TemporaryDirectory() as tmpdir:
                test_file = Path(tmpdir) / "test.pdf"
                test_file.write_text("fake pdf")

                processor = AsyncBatchProcessor(max_workers=1)
                processor.process_books_sync([test_file], progress_callback=on_progress)

                assert len(callback_calls) == 1

    def test_sync_process_handles_exceptions(self):
        """Test that exceptions are caught and converted to failed results"""
        with patch('book_ingestion.processors.async_batch._process_single_book') as mock_process:
            mock_process.side_effect = RuntimeError("Processing failed")

            with tempfile.TemporaryDirectory() as tmpdir:
                test_file = Path(tmpdir) / "test.pdf"
                test_file.write_text("fake pdf")

                processor = AsyncBatchProcessor(max_workers=1)
                summary = processor.process_books_sync([test_file])

                assert summary.total_books == 1
                assert summary.failed == 1
                assert "Processing failed" in summary.results[0].error


class TestProcessDirectory:
    def test_invalid_directory_raises(self):
        with pytest.raises(ValueError, match="Not a directory"):
            run_async(process_directory(Path("/nonexistent/path")))

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = run_async(process_directory(Path(tmpdir)))
            assert summary.total_books == 0

    def test_finds_pdf_and_epub_files(self):
        async def mock_process_books(self, paths, callback=None, config_dict=None):
            return BatchSummary(
                total_books=len(paths),
                successful=len(paths),
                failed=0,
                total_chapters=30,
                total_words=100000,
                total_time=5.0
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "book1.pdf").write_text("pdf")
            (Path(tmpdir) / "book2.epub").write_text("epub")
            (Path(tmpdir) / "book3.txt").write_text("txt")  # Should be ignored

            with patch.object(AsyncBatchProcessor, 'process_books', mock_process_books):
                summary = run_async(process_directory(Path(tmpdir)))

            # Verify only pdf and epub were processed (2 books)
            assert summary.total_books == 2


class TestProcessSingleBook:
    def test_returns_batch_result_on_error(self):
        """Test that errors are caught and returned as BatchResult"""
        # This tests the error handling path without actually processing
        result = _process_single_book("/nonexistent/file.pdf")
        assert isinstance(result, BatchResult)
        assert result.success is False
        assert result.error is not None
