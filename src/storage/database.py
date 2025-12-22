"""SQLite database operations"""

import sqlite3
from pathlib import Path

class BookDatabase:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
    
    def initialize(self):
        """Create database schema"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS books (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                author TEXT,
                word_count INTEGER,
                source_file TEXT,
                processing_status TEXT DEFAULT 'pending',
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chapters (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                chapter_number INTEGER NOT NULL,
                title TEXT,
                file_path TEXT NOT NULL,
                word_count INTEGER,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            )
        """)
        
        self.conn.commit()
    
    def insert_book(self, book):
        """Insert a book record"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO books (id, title, author, word_count, source_file, processing_status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            book['id'],
            book.get('title', 'Unknown'),
            book.get('author'),
            book.get('word_count', 0),
            book.get('source_file'),
            book.get('processing_status', 'processing')
        ))
        self.conn.commit()
    
    def insert_chapter(self, chapter):
        """Insert a chapter record"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO chapters (id, book_id, chapter_number, title, file_path, word_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            chapter['id'],
            chapter['book_id'],
            chapter['chapter_number'],
            chapter['title'],
            chapter.get('file_path', ''),
            chapter['word_count']
        ))
        self.conn.commit()
    
    def update_book_status(self, book_id, status):
        """Update book processing status"""
        cursor = self.conn.cursor()
        cursor.execute("UPDATE books SET processing_status = ? WHERE id = ?", (status, book_id))
        self.conn.commit()
    
    def get_all_books(self):
        """Get all books"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM books ORDER BY added_date DESC")
        return [dict(row) for row in cursor.fetchall()]

    def get_book(self, book_id):
        """Get a single book by ID"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_chapters_by_book(self, book_id):
        """Get all chapters for a book"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM chapters WHERE book_id = ? ORDER BY chapter_number",
            (book_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def close(self):
        """Close database connection"""
        self.conn.close()
