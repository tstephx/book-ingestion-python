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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_checkpoints (
                source_hash TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                raw_text_path TEXT,
                chapters_json TEXT,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    def save_checkpoint(self, checkpoint):
        """Save or update a processing checkpoint"""
        import json
        cursor = self.conn.cursor()
        chapters_json = json.dumps(checkpoint.get('chapters')) if checkpoint.get('chapters') else None

        cursor.execute("""
            INSERT INTO processing_checkpoints
                (source_hash, book_id, stage, raw_text_path, chapters_json, error, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(source_hash) DO UPDATE SET
                stage = excluded.stage,
                raw_text_path = excluded.raw_text_path,
                chapters_json = excluded.chapters_json,
                error = excluded.error,
                updated_at = CURRENT_TIMESTAMP
        """, (
            checkpoint['source_hash'],
            checkpoint['book_id'],
            checkpoint['stage'],
            checkpoint.get('raw_text_path'),
            chapters_json,
            checkpoint.get('error')
        ))
        self.conn.commit()

    def get_checkpoint(self, source_hash):
        """Get a checkpoint by source hash"""
        import json
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM processing_checkpoints WHERE source_hash = ?",
            (source_hash,)
        )
        row = cursor.fetchone()
        if not row:
            return None

        result = dict(row)
        if result.get('chapters_json'):
            result['chapters'] = json.loads(result['chapters_json'])
        return result

    def delete_checkpoint(self, source_hash):
        """Delete a checkpoint"""
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM processing_checkpoints WHERE source_hash = ?",
            (source_hash,)
        )
        self.conn.commit()

    def get_incomplete_checkpoints(self):
        """Get all checkpoints that haven't completed"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM processing_checkpoints WHERE stage != 'completed' ORDER BY updated_at DESC"
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_processed_filenames(self):
        """Get set of filenames (basename only) that have been processed"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT source_file FROM books WHERE processing_status = 'completed'")
        filenames = set()
        for row in cursor.fetchall():
            if row['source_file']:
                # Extract just the filename from the full path
                filename = Path(row['source_file']).name
                filenames.add(filename)
        return filenames

    def close(self):
        """Close database connection"""
        self.conn.close()
