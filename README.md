# 🐍 Book Ingestion Pipeline - Python Version

A robust Python pipeline for processing educational books (PDF/EPUB) into chapter-segmented markdown files with SQLite storage and semantic search capabilities.

**Current Status:** Production ready with 58 books, 833 chapters, 4.2M words  
**Integration:** Works with [book-mcp-server](../_Projects/book-mcp-server) for semantic search

---

## ✅ Quick Setup (5 minutes)

### Step 1: Create Virtual Environment

```bash
cd /Users/taylorstephens/_Projects/book-ingestion-python

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Initialize Database

```bash
python src/cli.py init
```

### Step 4: Process a Book

```bash
# Process a PDF
python src/cli.py process /path/to/book.pdf

# Process with custom metadata
python src/cli.py process /path/to/book.pdf --title "My Book" --author "John Doe"

# Debug mode (shows chapter detection stats)
python src/cli.py process /path/to/book.pdf --debug
```

### Step 5: List Books

```bash
python src/cli.py list
```

---

## 📁 Project Structure

```
book-ingestion-python/
├── src/
│   ├── cli.py                      # Main CLI entry point
│   ├── cli_enhanced.py             # Enhanced analysis commands
│   │
│   ├── converters/
│   │   ├── pdf_converter.py        # PDF → text (PyMuPDF)
│   │   └── epub_converter.py       # EPUB → text (ebooklib)
│   │
│   ├── processors/
│   │   ├── text_cleaner.py         # Basic text cleaning
│   │   ├── enhanced_text_cleaner.py # LLM-optimized cleaning
│   │   ├── chapter_splitter.py     # Chapter detection
│   │   ├── chapter_detector.py     # Multi-strategy detection
│   │   ├── chapter_validator.py    # Detection validation
│   │   ├── section_splitter.py     # Large chapter splitting
│   │   ├── semantic_chunker.py     # Semantic boundary detection
│   │   ├── chunk_merger.py         # Merge undersized chapters
│   │   ├── code_block_detector.py  # Code block preservation
│   │   ├── detection_diagnostics.py # Debug tools
│   │   ├── metadata_extractor.py   # Book metadata extraction
│   │   ├── profiler.py             # Quality metrics
│   │   ├── pipeline.py             # Processing pipeline
│   │   ├── enhanced_pipeline.py    # Advanced pipeline
│   │   ├── recursive_splitter.py   # Recursive splitting
│   │   └── async_batch.py          # Async processing
│   │
│   ├── storage/
│   │   ├── database.py             # SQLite operations
│   │   └── file_writer.py          # Markdown file output
│   │
│   └── utils/
│       └── config.py               # Configuration management
│
├── scripts/
│   ├── generate_embeddings.py      # Generate semantic embeddings
│   ├── validate_library.py         # Library quality audit
│   └── reprocess_problematic.py    # Reprocess failed books
│
├── migrations/
│   └── add_embeddings.py           # Database schema migration
│
├── tests/
│   └── processors/                 # Unit tests
│       ├── test_chapter_detector.py
│       ├── test_semantic_chunker.py
│       └── ... (10+ test files)
│
├── docs/
│   ├── ENHANCED-CHUNKING.md        # Chunking documentation
│   └── plans/                      # Improvement plans
│       └── CHAPTER-DETECTION-IMPROVEMENTS.md
│
├── data/
│   ├── books/                      # Processed book output
│   │   └── {book-id}/
│   │       ├── metadata.json
│   │       ├── raw/original.txt
│   │       └── chapters/
│   ├── library.db                  # SQLite database
│   └── temp/                       # Temporary files
│
├── config/
│   └── config.json                 # Configuration (optional)
│
├── batch_process.sh                # Batch processing script
├── clear_database.sh               # Database reset script
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

---

## 🚀 CLI Commands

### Core Commands

```bash
# Initialize database
python src/cli.py init

# Process a single book
python src/cli.py process book.pdf
python src/cli.py process book.epub -t "Title" -a "Author"
python src/cli.py process book.pdf --debug          # Show detection stats
python src/cli.py process book.pdf --no-split       # Disable section splitting

# List all books
python src/cli.py list

# Audit library for issues
python src/cli.py audit
python src/cli.py audit --fix                       # Attempt to fix issues

# Get help
python src/cli.py --help
```

### Enhanced Analysis Commands

```bash
# Deep analysis of a specific book
python src/cli.py analyze <book-id>
python src/cli.py analyze <book-id> --mode thorough
python src/cli.py analyze <book-id> --semantic      # Include semantic analysis
python src/cli.py analyze <book-id> --output report.md

# Reprocess a book with new detection
python src/cli.py reprocess <book-id>
python src/cli.py reprocess <book-id> --strategy toc_deep

# Validate entire library
python src/cli.py validate
```

---

## 📦 Batch Processing

Process multiple books at once:

```bash
# Make script executable
chmod +x batch_process.sh

# Process all books in a directory
./batch_process.sh /path/to/books/directory

# Example
./batch_process.sh ~/Documents/ebooks/python-books
```

**Output:**
```
📚 Batch Processing Complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Processed: 15 books
❌ Failed: 2 books
📚 Total: 17 books
```

---

## 🔧 Utility Scripts

### Generate Embeddings (for Semantic Search)

```bash
cd /Users/taylorstephens/_Projects/book-ingestion-python
source venv/bin/activate

# Generate embeddings for new chapters only
python scripts/generate_embeddings.py

# Force regenerate all embeddings
python scripts/generate_embeddings.py --force

# Custom batch size
python scripts/generate_embeddings.py --batch-size 64
```

### Validate Library Quality

```bash
# Generate quality report
python scripts/validate_library.py

# Save report to file
python scripts/validate_library.py --output report.md

# Auto-fix undersized chapters
python scripts/validate_library.py --fix-undersized
```

### Reprocess Problematic Books

```bash
# Reprocess books with quality issues
python scripts/reprocess_problematic.py
```

---

## 🔗 Integration with book-mcp-server

This pipeline works in tandem with [book-mcp-server](../_Projects/book-mcp-server) for semantic search:

### Workflow

1. **Process books** with this pipeline
2. **Generate embeddings** for semantic search
3. **Use MCP server** for queries in Claude

```bash
# 1. Process new books
./batch_process.sh /path/to/new/books

# 2. Generate embeddings
python scripts/generate_embeddings.py

# 3. Restart Claude Desktop to use updated library
```

### Database Location

Both projects share the same database:
```
/Users/taylorstephens/_Projects/book-ingestion-python/data/library.db
```

---

## 🎯 Output Structure

After processing, each book creates:

```
data/books/{book-id}/
├── metadata.json           # Book info (title, author, word count)
├── raw/
│   └── original.txt        # Full cleaned text
└── chapters/
    ├── 01-intro.md         # Chapter 1
    ├── 02-basics.md        # Chapter 2
    ├── 02-basics-section-1.md  # Section (if split)
    ├── 02-basics-section-2.md
    └── ...
```

### Section Splitting

Large chapters (>15K tokens) are automatically split into sections for AI readability:
- Target: ~15,000 tokens per section
- Preserves semantic boundaries
- Maintains parent chapter reference

---

## 📊 Database Schema

```sql
-- Books table
CREATE TABLE books (
    id TEXT PRIMARY KEY,
    title TEXT,
    author TEXT,
    word_count INTEGER,
    source_file TEXT,
    processing_status TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Chapters table
CREATE TABLE chapters (
    id TEXT PRIMARY KEY,
    book_id TEXT,
    chapter_number INTEGER,
    title TEXT,
    content TEXT,
    word_count INTEGER,
    file_path TEXT,
    embedding BLOB,              -- Semantic embeddings
    embedding_model TEXT,        -- Model used (all-MiniLM-L6-v2)
    FOREIGN KEY (book_id) REFERENCES books(id)
);
```

---

## 📦 Dependencies

```
# Core
pymupdf>=1.23.0        # PDF parsing (excellent quality)
ebooklib>=0.18         # EPUB parsing
beautifulsoup4>=4.12.0 # HTML parsing
lxml>=4.9.0            # XML parsing

# Text Processing
nltk>=3.8.0            # Natural language processing
spacy>=3.7.0           # Advanced NLP

# CLI
click>=8.1.0           # Command-line interface
rich>=13.7.0           # Beautiful terminal output
tqdm>=4.66.0           # Progress bars

# Utilities
python-magic>=0.4.27   # File type detection

# Semantic Search (for embeddings)
sentence-transformers>=2.2.0  # Embedding generation
numpy>=1.24.0                 # Vector operations
```

---

## 🐛 Troubleshooting

### Virtual environment not activating?

```bash
# Make sure you're in the project directory
cd /Users/taylorstephens/_Projects/book-ingestion-python

# Try this instead
. venv/bin/activate
```

### Import errors (ModuleNotFoundError)?

This often happens when Python version changes after creating the venv.

```bash
# Check for version mismatch
./venv/bin/python --version
./venv/bin/pip --version

# If mismatched, recreate venv
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### No chapters detected?

Some books have unusual structure. The system uses fallback strategies:
1. TOC-based detection (most reliable)
2. Header pattern matching
3. Fixed-size splitting (last resort)

Use `--debug` flag to see detection statistics:
```bash
python src/cli.py process book.pdf --debug
```

### Chapter detection creating too many chapters?

Use the audit command to identify issues:
```bash
python src/cli.py audit
```

Then reprocess with a specific strategy:
```bash
python src/cli.py reprocess <book-id> --strategy toc_deep
```

---

## 🎓 Quality Metrics

The pipeline tracks quality metrics for each book:

| Metric | Target | Warning Threshold |
|--------|--------|-------------------|
| Avg chapter size | 3,000-15,000 words | <2,000 or >20,000 |
| Chapter count | 5-40 | >50 (oversplit) |
| Quality score | 75-100 | <50 (needs review) |

### Quality Score Factors:
- Chapter size distribution (variance)
- Metadata completeness
- Code block preservation
- Section split quality

---

## ✨ Features

### ✅ Implemented
- PDF and EPUB conversion
- Multi-strategy chapter detection
- LLM-optimized text cleaning
- Section splitting for large chapters
- Semantic embedding generation
- Quality validation and profiling
- Batch processing
- Integration with MCP server

### 🔄 In Progress
- Improved chapter detection (see docs/plans/)
- Async batch processing optimization

### 📋 Planned
- Incremental processing (resume failed jobs)
- Metadata enrichment (ISBN, publisher)
- Hybrid search (keyword + semantic)

---

## 📞 Support

### Check Status
```bash
python src/cli.py list
python src/cli.py audit
```

### Run Tests
```bash
pytest tests/ -v
```

### View Logs
Processing logs appear in terminal with Rich formatting.

### Common Issues

| Issue | Solution |
|-------|----------|
| No chapters detected | Use `--debug` flag, try manual title/author |
| Too many chapters | Run `audit --fix` or `reprocess` |
| Embeddings missing | Run `scripts/generate_embeddings.py` |
| Import errors | Recreate venv (see troubleshooting) |

---

## 📚 Documentation

- [Enhanced Chunking](docs/ENHANCED-CHUNKING.md) - Semantic chunking details
- [Chapter Detection Improvements](docs/plans/CHAPTER-DETECTION-IMPROVEMENTS.md) - Planned improvements
- [book-mcp-server README](../_Projects/book-mcp-server/README.md) - MCP integration

---

**Version:** 2.0.0  
**Python:** 3.10+  
**Status:** Production Ready ✅  
**Last Updated:** December 2024
