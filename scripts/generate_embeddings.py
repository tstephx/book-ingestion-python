#!/usr/bin/env python3
"""
Generate embeddings for all book chapters

This script generates semantic embeddings for all chapters in the library
that don't already have embeddings. Uses batch processing for efficiency.

Usage:
    python scripts/generate_embeddings.py [--force] [--batch-size 32]
    
Options:
    --force: Regenerate all embeddings (even if they exist)
    --batch-size: Number of chapters to process at once (default: 32)
"""

import sys
import argparse
import logging
from pathlib import Path
import time
import io

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import numpy as np
from sentence_transformers import SentenceTransformer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

def load_chapter_content(file_path):
    """Load chapter content from file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
        return None

def generate_embeddings(db_path, force=False, batch_size=32):
    """Generate embeddings for all chapters
    
    Args:
        db_path: Path to SQLite database
        force: If True, regenerate all embeddings
        batch_size: Number of chapters to process at once
    """
    logger.info("Loading embedding model...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    logger.info("✓ Model loaded successfully")
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get chapters needing embeddings
    if force:
        cursor.execute("""
            SELECT id, file_path, title, chapter_number
            FROM chapters
            ORDER BY id
        """)
        logger.info("Force mode: Regenerating ALL embeddings")
    else:
        cursor.execute("""
            SELECT id, file_path, title, chapter_number
            FROM chapters
            WHERE embedding IS NULL
            ORDER BY id
        """)
        logger.info("Processing chapters without embeddings")
    
    chapters = cursor.fetchall()
    
    if not chapters:
        logger.info("✓ All chapters already have embeddings!")
        conn.close()
        return
    
    logger.info(f"Found {len(chapters)} chapters to process")
    
    # Process in batches
    total_chapters = len(chapters)
    processed = 0
    errors = 0
    start_time = time.time()
    
    for i in range(0, total_chapters, batch_size):
        batch = chapters[i:i + batch_size]
        batch_texts = []
        batch_metadata = []
        
        # Load content for batch
        for chapter in batch:
            content = load_chapter_content(chapter['file_path'])
            if content:
                batch_texts.append(content)
                batch_metadata.append({
                    'id': chapter['id'],
                    'title': chapter['title'],
                    'chapter_number': chapter['chapter_number']
                })
            else:
                errors += 1
                logger.warning(
                    f"Skipping chapter {chapter['chapter_number']}: "
                    f"{chapter['title']} (read error)"
                )
        
        if not batch_texts:
            continue
        
        # Generate embeddings for batch
        logger.info(
            f"Processing batch {i//batch_size + 1}/{(total_chapters + batch_size - 1)//batch_size} "
            f"({len(batch_texts)} chapters)..."
        )
        
        embeddings = model.encode(
            batch_texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        
        # Store embeddings in database
        for metadata, embedding in zip(batch_metadata, embeddings):
            # Serialize embedding as numpy array in BLOB
            embedding_blob = io.BytesIO()
            np.save(embedding_blob, embedding)
            embedding_bytes = embedding_blob.getvalue()
            
            cursor.execute("""
                UPDATE chapters
                SET embedding = ?,
                    embedding_model = ?
                WHERE id = ?
            """, (
                embedding_bytes,
                'all-MiniLM-L6-v2',
                metadata['id']
            ))
            
            processed += 1
            
            # Progress indicator
            if processed % 10 == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (total_chapters - processed) / rate if rate > 0 else 0
                logger.info(
                    f"Progress: {processed}/{total_chapters} "
                    f"({processed/total_chapters*100:.1f}%) - "
                    f"{rate:.1f} ch/s - ETA: {eta:.0f}s"
                )
        
        # Commit batch
        conn.commit()
    
    # Final summary
    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("✓ Embedding generation complete!")
    logger.info(f"  Processed: {processed} chapters")
    logger.info(f"  Errors: {errors} chapters")
    logger.info(f"  Time: {elapsed:.1f} seconds ({processed/elapsed:.1f} ch/s)")
    logger.info(f"  Model: all-MiniLM-L6-v2 (384 dimensions)")
    logger.info("=" * 60)
    
    conn.close()

def main():
    parser = argparse.ArgumentParser(
        description="Generate semantic embeddings for book chapters"
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Regenerate all embeddings (even if they exist)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=32,
        help='Batch size for processing (default: 32)'
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default=None,
        help='Path to database (default: ../book-ingestion-python/data/library.db)'
    )
    
    args = parser.parse_args()
    
    # Determine database path
    if args.db_path:
        db_path = Path(args.db_path)
    else:
        # Default: look for database in book-ingestion-python project
        script_dir = Path(__file__).parent
        db_path = script_dir.parent.parent / 'book-ingestion-python' / 'data' / 'library.db'
    
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        logger.error("Please specify --db-path or ensure database exists at default location")
        sys.exit(1)
    
    logger.info(f"Database: {db_path}")
    
    try:
        generate_embeddings(db_path, force=args.force, batch_size=args.batch_size)
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
