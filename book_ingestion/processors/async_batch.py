"""Async batch processing for multiple books"""

import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Awaitable
import time


@dataclass
class BatchResult:
    """Result for a single book in a batch"""
    file_path: str
    success: bool
    book_id: Optional[str] = None
    chapters_count: Optional[int] = None
    word_count: Optional[int] = None
    error: Optional[str] = None
    processing_time: float = 0.0


@dataclass
class BatchSummary:
    """Summary of batch processing results"""
    total_books: int
    successful: int
    failed: int
    total_chapters: int
    total_words: int
    total_time: float
    results: List[BatchResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_books == 0:
            return 0.0
        return self.successful / self.total_books

    def get_failures(self) -> List[BatchResult]:
        return [r for r in self.results if not r.success]


class AsyncBatchProcessor:
    """
    Async batch processor for processing multiple books concurrently.

    Uses a process pool for CPU-bound work and async coordination
    for managing multiple jobs.
    """

    def __init__(self, max_workers: int = 4):
        """
        Initialize the batch processor.

        Args:
            max_workers: Maximum number of concurrent processing jobs
        """
        self.max_workers = max_workers
        self._executor: Optional[ProcessPoolExecutor] = None

    def _get_executor(self) -> ProcessPoolExecutor:
        """Get or create the process pool executor"""
        if self._executor is None:
            self._executor = ProcessPoolExecutor(max_workers=self.max_workers)
        return self._executor

    async def process_books(
        self,
        book_paths: List[Path],
        progress_callback: Optional[Callable[[Path, BatchResult], Awaitable[None]]] = None,
        config_dict: Optional[Dict[str, Any]] = None
    ) -> BatchSummary:
        """
        Process multiple books concurrently.

        Args:
            book_paths: List of paths to book files
            progress_callback: Optional async callback called after each book completes
            config_dict: Optional config dictionary to pass to workers

        Returns:
            BatchSummary with results for all books
        """
        start_time = time.time()
        semaphore = asyncio.Semaphore(self.max_workers)

        async def process_with_semaphore(path: Path) -> BatchResult:
            async with semaphore:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self._get_executor(),
                    _process_single_book,
                    str(path),
                    config_dict
                )
                if progress_callback:
                    await progress_callback(path, result)
                return result

        # Process all books concurrently (limited by semaphore)
        tasks = [process_with_semaphore(p) for p in book_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to BatchResults
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(BatchResult(
                    file_path=str(book_paths[i]),
                    success=False,
                    error=str(result)
                ))
            else:
                processed_results.append(result)

        return self._summarize_results(processed_results, time.time() - start_time)

    def process_books_sync(
        self,
        book_paths: List[Path],
        progress_callback: Optional[Callable[[Path, BatchResult], None]] = None,
        config_dict: Optional[Dict[str, Any]] = None
    ) -> BatchSummary:
        """
        Synchronous version of batch processing.

        Useful when you don't have an async context.

        Args:
            book_paths: List of paths to book files
            progress_callback: Optional callback called after each book completes
            config_dict: Optional config dictionary to pass to workers

        Returns:
            BatchSummary with results for all books
        """
        start_time = time.time()
        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(_process_single_book, str(path), config_dict): path
                for path in book_paths
            }

            for future in futures:
                path = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    if progress_callback:
                        progress_callback(path, result)
                except Exception as e:
                    result = BatchResult(
                        file_path=str(path),
                        success=False,
                        error=str(e)
                    )
                    results.append(result)
                    if progress_callback:
                        progress_callback(path, result)

        return self._summarize_results(results, time.time() - start_time)

    def _summarize_results(self, results: List[BatchResult], total_time: float) -> BatchSummary:
        """Summarize batch processing results"""
        successful = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        total_chapters = sum(r.chapters_count or 0 for r in results if r.success)
        total_words = sum(r.word_count or 0 for r in results if r.success)

        return BatchSummary(
            total_books=len(results),
            successful=successful,
            failed=failed,
            total_chapters=total_chapters,
            total_words=total_words,
            total_time=total_time,
            results=results
        )

    def shutdown(self):
        """Shutdown the executor"""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()


def _process_single_book(file_path: str, config_dict: Optional[Dict[str, Any]] = None) -> BatchResult:
    """
    Process a single book file.

    This function runs in a separate process.

    Args:
        file_path: Path to the book file
        config_dict: Optional config dictionary

    Returns:
        BatchResult with processing outcome
    """
    import time
    start_time = time.time()

    try:
        # Import here to avoid issues with process pool
        from ..utils.config import Config
        from ..storage.database import BookDatabase
        from .pipeline import ProcessingPipeline

        # Create config
        if config_dict:
            config = Config()
            # Apply any overrides from config_dict
            for key, value in config_dict.items():
                if hasattr(config, key):
                    setattr(config, key, value)
        else:
            config = Config()

        # Create database connection (each process needs its own)
        db = BookDatabase(config.database_path)
        db.initialize()

        # Process the book
        pipeline = ProcessingPipeline(db, config)
        result = pipeline.process(Path(file_path))

        db.close()

        processing_time = time.time() - start_time

        if result.success:
            return BatchResult(
                file_path=file_path,
                success=True,
                book_id=result.book_id,
                chapters_count=len(result.chapters) if result.chapters else 0,
                word_count=result.metadata.get('word_count', 0) if result.metadata else 0,
                processing_time=processing_time
            )
        else:
            return BatchResult(
                file_path=file_path,
                success=False,
                error=result.error,
                processing_time=processing_time
            )

    except Exception as e:
        return BatchResult(
            file_path=file_path,
            success=False,
            error=str(e),
            processing_time=time.time() - start_time
        )


async def process_directory(
    directory: Path,
    extensions: List[str] = None,
    max_workers: int = 4,
    progress_callback: Optional[Callable[[Path, BatchResult], Awaitable[None]]] = None
) -> BatchSummary:
    """
    Convenience function to process all books in a directory.

    Args:
        directory: Directory containing book files
        extensions: List of file extensions to process (default: ['.pdf', '.epub'])
        max_workers: Maximum concurrent workers
        progress_callback: Optional progress callback

    Returns:
        BatchSummary with results
    """
    if extensions is None:
        extensions = ['.pdf', '.epub']

    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f"Not a directory: {directory}")

    # Find all matching files
    book_paths = []
    for ext in extensions:
        book_paths.extend(directory.glob(f"*{ext}"))
        book_paths.extend(directory.glob(f"**/*{ext}"))

    # Remove duplicates while preserving order
    seen = set()
    unique_paths = []
    for path in book_paths:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)

    if not unique_paths:
        return BatchSummary(
            total_books=0,
            successful=0,
            failed=0,
            total_chapters=0,
            total_words=0,
            total_time=0.0,
            results=[]
        )

    processor = AsyncBatchProcessor(max_workers=max_workers)
    try:
        return await processor.process_books(unique_paths, progress_callback)
    finally:
        processor.shutdown()
