#!/usr/bin/env python3
"""
Add embeddings column to chapters table for semantic search

This migration adds:
- embedding BLOB column to store 384-dim vectors (numpy arrays)
- embedding_model TEXT column to track which model generated it
"""

import sqlite3
import sys
from pathlib import Path

def add_embeddings_column(db_path):
    """Add embeddings column to chapters table"""
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(chapters)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'embedding' in columns:
        print("✓ Embeddings column already exists")
        conn.close()
        return
    
    # Add embedding column (stores numpy array as BLOB)
    print("Adding 'embedding' column...")
    cursor.execute("""
        ALTER TABLE chapters
        ADD COLUMN embedding BLOB
    """)
    
    # Add embedding_model column to track model version
    print("Adding 'embedding_model' column...")
    cursor.execute("""
        ALTER TABLE chapters
        ADD COLUMN embedding_model TEXT
    """)
    
    conn.commit()
    conn.close()
    
    print("✓ Migration complete!")
    print("\nNext steps:")
    print("1. Install dependencies: pip install sentence-transformers numpy")
    print("2. Generate embeddings: python scripts/generate_embeddings.py")

if __name__ == "__main__":
    # Default database path
    db_path = Path(__file__).parent.parent / "data" / "library.db"
    
    # Allow custom path via command line
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
    
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)
    
    add_embeddings_column(db_path)
