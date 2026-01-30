"""Book Repository Protocol for storage abstraction."""

from typing import Protocol, List, Dict, Optional


class BookRepository(Protocol):
    """
    Protocol for book storage operations.

    Abstracts the storage layer so implementations can use SQLite,
    PostgreSQL, or any other storage backend.
    """

    def insert_book(self, metadata: Dict) -> None:
        """Insert book metadata into the repository."""
        ...

    def insert_chapter(self, chapter: Dict) -> None:
        """Insert a chapter into the repository."""
        ...

    def get_book(self, book_id: str) -> Optional[Dict]:
        """Retrieve a book by its ID."""
        ...

    def get_chapters_by_book(self, book_id: str) -> List[Dict]:
        """Retrieve all chapters for a book."""
        ...

    def update_book_status(self, book_id: str, status: str) -> None:
        """Update the processing status of a book."""
        ...

    def get_all_books(self) -> List[Dict]:
        """Retrieve all books in the repository."""
        ...

    def book_exists(self, book_id: str) -> bool:
        """Check if a book with the given ID exists."""
        ...

    def get_processed_filenames(self) -> set:
        """Get set of filenames that have already been processed."""
        ...
