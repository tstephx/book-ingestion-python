# 🐍 Book Ingestion Pipeline - Python Version

Simple, clean Python implementation for processing educational books.

## ✅ Quick Setup (5 minutes)

### Step 1: Create Virtual Environment

```bash
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

# With custom metadata
python src/cli.py process /path/to/book.pdf --title "My Book" --author "John Doe"
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
│   ├── cli.py                  # Main CLI
│   ├── converters/
│   │   ├── pdf_converter.py   # PDF → text
│   │   └── epub_converter.py  # EPUB → text
│   ├── processors/
│   │   ├── text_cleaner.py    # Clean text
│   │   ├── chapter_splitter.py # Split chapters
│   │   └── metadata_extractor.py
│   ├── storage/
│   │   ├── database.py        # SQLite operations
│   │   └── file_writer.py     # Write files
│   └── utils/
│       └── config.py          # Configuration
├── data/
│   ├── books/                 # Processed books
│   ├── temp/                  # Temporary files
│   └── library.db             # SQLite database
├── config/
│   └── config.json            # Configuration (optional)
├── requirements.txt           # Dependencies
└── README.md                  # This file
```

---

## 🚀 Commands

```bash
# Initialize
python src/cli.py init

# Process a book
python src/cli.py process book.pdf

# Process with metadata
python src/cli.py process book.pdf -t "Title" -a "Author"

# List all books
python src/cli.py list

# Get help
python src/cli.py --help
```

---

## 📦 Dependencies

- **pymupdf** - PDF parsing (excellent quality)
- **ebooklib** - EPUB parsing
- **beautifulsoup4** - HTML parsing
- **click** - CLI framework
- **rich** - Beautiful terminal output
- **sqlite3** - Built into Python!

---

## 🎯 Output Structure

After processing, you'll find:

```
data/books/{book-id}/
├── metadata.json         # Book info
├── raw/
│   └── original.txt     # Full text
└── chapters/
    ├── 01-intro.md      # Chapter 1
    ├── 02-basics.md     # Chapter 2
    └── ...
```

---

## 💡 Advantages Over TypeScript Version

1. **No build step** - Just run `.py` files
2. **No node_modules drama** - Simple `pip install`
3. **Better PDF libraries** - PyMuPDF is excellent
4. **Built-in SQLite** - No external dependencies
5. **Simpler code** - ~500 lines vs 2000+ lines
6. **Better for data processing** - Python's strength

---

## 🐛 Troubleshooting

### Virtual environment not activating?

```bash
# Make sure you're in the project directory
cd book-ingestion-python

# Try this instead
. venv/bin/activate
```

### Import errors (ModuleNotFoundError)?

This often happens when your system Python version changes after creating the venv (e.g., after a brew upgrade or pyenv switch). The packages are installed for one Python version but the interpreter is another.

**Check for version mismatch:**
```bash
./venv/bin/python --version
./venv/bin/pip --version
```

If the versions don't match (e.g., pip says python3.13 but python says 3.12), **recreate the venv:**

```bash
# Remove the corrupted venv
rm -rf venv

# Recreate with current Python
python3 -m venv venv

# Reinstall dependencies
source venv/bin/activate
pip install -r requirements.txt
```

**Simple import error fix:**
```bash
# Make sure you're in the virtual environment
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### No chapters detected?

This is normal for some books. The system will automatically split into 2500-word sections.

---

## ✨ Next Steps

After successful setup:

1. ✅ Process a test book
2. ✅ Check `data/books/` for output
3. ✅ Query database: `sqlite3 data/library.db "SELECT * FROM books;"`
4. ➡️ Build MCP Server (next phase)
5. ➡️ Add RAG integration
6. ➡️ Implement ELI5 generation

---

## 📞 Support

All working? Great! Ready to process books.

Having issues? Check:
1. Virtual environment is activated
2. All dependencies installed
3. Running from project root
4. Python 3.10+ installed

---

**Version**: 1.0.0
**Python**: 3.10+
**Status**: Ready to use!
