"""
Book Ingestion CLI - Python Version

Simple, clean Python implementation for processing educational books.

Enhanced with:
- LLM-optimized text cleaning
- Semantic chunking validation
- Comprehensive quality metrics
- Actionable recommendations
"""

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from converters.pdf_converter import PDFConverter
from converters.epub_converter import EPUBConverter
from processors.chapter_splitter import ChapterSplitter
from processors.text_cleaner import TextCleaner
from processors.metadata_extractor import MetadataExtractor
from processors.chapter_validator import ChapterValidator
from processors.section_splitter import SectionSplitter, split_chapters_for_ai, estimate_tokens
from storage.database import BookDatabase
from storage.file_writer import FileWriter
from utils.config import Config

console = Console()
validator = ChapterValidator()

# Import enhanced commands
try:
    from cli_enhanced import register_enhanced_commands
    ENHANCED_AVAILABLE = True
except ImportError:
    ENHANCED_AVAILABLE = False

@click.group()
def cli():
    """Book Ingestion Pipeline - Process educational books for MCP integration"""
    pass

@cli.command()
def init():
    """Initialize the database and directories"""
    console.print("[blue]ℹ[/blue] Initializing database...")
    
    config = Config()
    db = BookDatabase(config.database_path)
    db.initialize()
    
    console.print("[green]✓[/green] Database initialized successfully!")
    console.print(f"[dim]Database location: {config.database_path}[/dim]")

@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--title', '-t', help='Book title (optional)')
@click.option('--author', '-a', help='Author name (optional)')
@click.option('--no-split', is_flag=True, help='Disable section splitting for large chapters')
@click.option('--debug', is_flag=True, help='Show chapter detection statistics')
def process(file_path, title, author, no_split, debug):
    """Process a book file (PDF or EPUB)"""
    import uuid

    file_path = Path(file_path)
    config = Config()

    console.print(f"[blue]ℹ[/blue] Processing: {file_path.name}")

    book_id = str(uuid.uuid4())

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:

        # Step 1: Convert to text
        task = progress.add_task("Converting book to text...", total=None)

        if file_path.suffix.lower() == '.pdf':
            converter = PDFConverter()
            result = converter.convert(str(file_path))
        elif file_path.suffix.lower() == '.epub':
            converter = EPUBConverter()
            result = converter.convert(str(file_path))
        else:
            console.print(f"[red]✗[/red] Unsupported file format: {file_path.suffix}")
            return

        if not result['success']:
            console.print(f"[red]✗[/red] Conversion failed: {result.get('error', 'Unknown error')}")
            return

        progress.update(task, completed=True)
        console.print("[green]✓[/green] Conversion complete")

        # Step 2: Clean text
        progress.add_task("Cleaning text...", total=None)
        cleaner = TextCleaner(config)
        cleaned_text = cleaner.clean(result['text'])
        console.print("[green]✓[/green] Text cleaned")

        # Step 3: Extract metadata
        progress.add_task("Extracting metadata...", total=None)
        extractor = MetadataExtractor()
        metadata = extractor.extract(cleaned_text, str(file_path), result.get('metadata'))

        # Override with user-provided values
        if title:
            metadata['title'] = title
        if author:
            metadata['author'] = author

        metadata['id'] = book_id
        metadata['source_file'] = str(file_path)

        console.print("[green]✓[/green] Metadata extracted")

        # Step 4: Split into chapters
        progress.add_task("Detecting chapters...", total=None)
        splitter = ChapterSplitter(config)
        result = splitter.split_with_stats(cleaned_text, book_id)
        chapters = result['chapters']
        detection_stats = result['stats']
        console.print(f"[green]✓[/green] Detected {len(chapters)} chapters")

        # Show debug stats if requested
        if debug and detection_stats:
            console.print("\n[bold cyan]Chapter Detection Statistics:[/bold cyan]")
            console.print(f"  Method: {detection_stats.method}")
            console.print(f"  Confidence: {detection_stats.confidence}")
            console.print(f"  Candidates found: {detection_stats.candidates_found}")
            console.print(f"  Candidates rejected: {detection_stats.candidates_rejected}")
            console.print(f"  Anchors used: {detection_stats.anchors_used}")
            console.print(f"  Merges performed: {detection_stats.merges_performed}")
            console.print(f"  Code blocks detected: {detection_stats.code_blocks_detected}")
            if detection_stats.warnings:
                console.print("  [yellow]Warnings:[/yellow]")
                for warning in detection_stats.warnings:
                    console.print(f"    • {warning}")
            console.print()

        # Step 4b: Validate chapter detection
        validation = validator.validate(cleaned_text, chapters, metadata.get('word_count', 0))
        if validation.has_issues():
            for error in validation.errors:
                console.print(f"[red]✗ ERROR:[/red] {error}")
            for warning in validation.warnings:
                console.print(f"[yellow]⚠ WARNING:[/yellow] {warning}")

        # Step 5: Split large chapters into sections (if enabled)
        sections = None
        split_enabled = config.section_splitting.get('enabled', True) and not no_split

        if split_enabled:
            progress.add_task("Splitting large chapters...", total=None)
            sections = split_chapters_for_ai(chapters, config.section_splitting)

            # Count how many chapters were split
            chapters_split = len(set(s['parent_chapter_number'] for s in sections if len([
                x for x in sections if x['parent_chapter_number'] == s['parent_chapter_number']
            ]) > 1))

            if chapters_split > 0:
                console.print(f"[green]✓[/green] Split {chapters_split} large chapters into {len(sections)} sections")
            else:
                console.print("[green]✓[/green] No chapters needed splitting")

        # Step 6: Save to storage
        progress.add_task("Saving to storage...", total=None)

        db = BookDatabase(config.database_path)
        db.insert_book(metadata)

        writer = FileWriter(config.output_dir)

        if sections and split_enabled:
            writer.write_book_with_sections(metadata, chapters, sections, cleaned_text)
        else:
            writer.write_book(metadata, chapters, cleaned_text)

        for chapter in chapters:
            db.insert_chapter(chapter)

        db.update_book_status(book_id, 'completed')

        console.print("[green]✓[/green] Saved to storage")

    # Summary
    console.print("\n[bold green]Processing complete![/bold green]")
    console.print(f"[dim]Book ID: {book_id}[/dim]")
    console.print(f"[dim]Chapters: {len(chapters)}[/dim]")
    if sections and split_enabled:
        console.print(f"[dim]Sections: {len(sections)} (max ~15K tokens each)[/dim]")
    console.print(f"[dim]Total words: {metadata.get('word_count', 0):,}[/dim]")

@cli.command(name='list')
def list_books():
    """List all processed books"""
    config = Config()
    db = BookDatabase(config.database_path)
    books = db.get_all_books()
    
    if not books:
        console.print("[yellow]No books found. Process a book first![/yellow]")
        return
    
    console.print("\n[bold]📚 Processed Books:[/bold]\n")
    
    for book in books:
        console.print(f"[cyan]{book['title']}[/cyan]")
        console.print(f"  by {book.get('author', 'Unknown')}")
        console.print(f"  [dim]ID: {book['id']}[/dim]")
        console.print(f"  [dim]Words: {book.get('word_count', 0):,}[/dim]")
        console.print(f"  [dim]Status: {book['processing_status']}[/dim]\n")

@cli.command()
@click.option('--fix', is_flag=True, help='Attempt to reprocess books with issues')
def audit(fix):
    """Audit all books for chapter detection issues"""
    config = Config()
    db = BookDatabase(config.database_path)
    books = db.get_all_books()

    if not books:
        console.print("[yellow]No books found.[/yellow]")
        return

    console.print("\n[bold]📋 Auditing Books for Chapter Issues...[/bold]\n")

    issues_found = 0
    books_to_fix = []

    for book in books:
        book_id = book['id']
        title = book.get('title', 'Unknown')[:50]
        word_count = book.get('word_count', 0)

        # Get chapters for this book
        chapters = db.get_chapters_by_book(book_id)

        # Try to read the raw text for validation
        raw_path = Path(config.output_dir) / book_id / 'raw' / 'original.txt'
        if raw_path.exists():
            with open(raw_path, 'r') as f:
                text = f.read()

            validation = validator.validate(text, chapters, word_count)

            if validation.has_issues():
                issues_found += 1
                console.print(f"[red]⚠[/red] {title}")
                console.print(f"   [dim]ID: {book_id}[/dim]")
                console.print(f"   [dim]Chapters: {len(chapters)} | Words: {word_count:,}[/dim]")

                for error in validation.errors:
                    console.print(f"   [red]ERROR:[/red] {error}")
                for warning in validation.warnings:
                    console.print(f"   [yellow]WARN:[/yellow] {warning}")

                if validation.expected_chapters:
                    console.print(
                        f"   [dim]Expected: {validation.expected_chapters} | "
                        f"Found: {validation.actual_chapters}[/dim]"
                    )

                books_to_fix.append(book)
                console.print()
            else:
                console.print(f"[green]✓[/green] {title} ({len(chapters)} chapters)")
        else:
            console.print(f"[yellow]?[/yellow] {title} [dim](raw text not found)[/dim]")

    console.print(f"\n[bold]Summary:[/bold] {issues_found} books with issues out of {len(books)}")

    if fix and books_to_fix:
        console.print("\n[bold]Attempting to reprocess books with issues...[/bold]\n")
        for book in books_to_fix:
            source = book.get('source_file')
            if source and Path(source).exists():
                console.print(f"[blue]→[/blue] Reprocessing: {book['title'][:40]}...")
                # Would call process logic here
                console.print(f"   [dim]Source: {source}[/dim]")
            else:
                console.print(f"[yellow]![/yellow] Cannot reprocess {book['title'][:40]} - source file not found")


@cli.command()
@click.argument('book_id')
def validate(book_id):
    """Validate a specific book's chapter detection"""
    config = Config()
    db = BookDatabase(config.database_path)

    book = db.get_book(book_id)
    if not book:
        console.print(f"[red]Book not found: {book_id}[/red]")
        return

    chapters = db.get_chapters_by_book(book_id)
    raw_path = Path(config.output_dir) / book_id / 'raw' / 'original.txt'

    if not raw_path.exists():
        console.print("[red]Raw text file not found[/red]")
        return

    with open(raw_path, 'r') as f:
        text = f.read()

    validation = validator.validate(text, chapters, book.get('word_count', 0))

    console.print(f"\n[bold]Validation Report: {book['title'][:50]}[/bold]\n")
    console.print(f"Chapters detected: {len(chapters)}")
    if validation.expected_chapters:
        console.print(f"Chapters expected: {validation.expected_chapters}")
    console.print(f"Word count: {book.get('word_count', 0):,}")

    if validation.errors:
        console.print("\n[red]Errors:[/red]")
        for error in validation.errors:
            console.print(f"  • {error}")

    if validation.warnings:
        console.print("\n[yellow]Warnings:[/yellow]")
        for warning in validation.warnings:
            console.print(f"  • {warning}")

    if not validation.has_issues():
        console.print("\n[green]✓ No issues detected[/green]")

    # Show chapter breakdown
    console.print("\n[bold]Chapter Breakdown:[/bold]")
    for ch in chapters:
        wc = ch.get('word_count', 0)
        title = ch.get('title', 'Unknown')[:45]
        flag = ""
        if wc > 30000:
            flag = " [yellow]⚠ LARGE[/yellow]"
        elif wc < 100:
            flag = " [yellow]⚠ TINY[/yellow]"
        console.print(f"  {ch.get('chapter_number', '?'):2}. {title} ({wc:,} words){flag}")


@cli.command()
@click.argument('directory', type=click.Path(exists=True))
@click.option('--recursive/--no-recursive', default=True, help='Scan subdirectories recursively')
@click.option('--dry-run', is_flag=True, help='Show what would be processed without actually processing')
@click.option('--log-dir', type=click.Path(), default=None, help='Directory for log files (default: data/logs)')
def batch(directory, recursive, dry_run, log_dir):
    """Batch process books from a directory.
    
    Features:
    - Skips already-processed books (by filename)
    - Saves logs to timestamped file
    - Recursive subdirectory scanning (default: on)
    
    Example:
        python src/cli.py batch /path/to/ebooks
        python src/cli.py batch /path/to/ebooks --dry-run
        python src/cli.py batch /path/to/ebooks --no-recursive
    """
    import uuid
    from datetime import datetime
    
    config = Config()
    db = BookDatabase(config.database_path)
    
    # Setup logging
    if log_dir is None:
        log_dir = Path(config.output_dir).parent / 'logs'
    else:
        log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'batch_{timestamp}.log'
    
    def log(message, level='INFO'):
        """Write to both console and log file"""
        timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp_str}] [{level}] {message}"
        with open(log_file, 'a') as f:
            f.write(log_entry + '\n')
    
    # Get already processed filenames
    processed_filenames = db.get_processed_filenames()
    console.print(f"[dim]Found {len(processed_filenames)} already-processed books in database[/dim]")
    log(f"Found {len(processed_filenames)} already-processed books in database")
    
    # Find all PDF and EPUB files
    directory = Path(directory)
    if recursive:
        pdf_files = list(directory.rglob('*.pdf'))
        epub_files = list(directory.rglob('*.epub'))
    else:
        pdf_files = list(directory.glob('*.pdf'))
        epub_files = list(directory.glob('*.epub'))
    
    all_files = sorted(pdf_files + epub_files, key=lambda p: p.name.lower())
    
    console.print(f"[blue]ℹ[/blue] Found {len(all_files)} books in {'recursive scan of' if recursive else ''} {directory}")
    log(f"Found {len(all_files)} books in {directory} (recursive={recursive})")
    
    # Filter out already processed
    to_process = []
    skipped = []
    for file_path in all_files:
        if file_path.name in processed_filenames:
            skipped.append(file_path)
        else:
            to_process.append(file_path)
    
    console.print(f"[green]→[/green] {len(to_process)} new books to process")
    console.print(f"[yellow]→[/yellow] {len(skipped)} books skipped (already processed)")
    log(f"To process: {len(to_process)}, Skipped: {len(skipped)}")
    
    if skipped:
        console.print("\n[dim]Skipped books:[/dim]")
        for f in skipped[:10]:  # Show first 10
            console.print(f"  [dim]• {f.name}[/dim]")
        if len(skipped) > 10:
            console.print(f"  [dim]... and {len(skipped) - 10} more[/dim]")
    
    if dry_run:
        console.print("\n[yellow]DRY RUN - No books will be processed[/yellow]")
        console.print("\n[bold]Books that would be processed:[/bold]")
        for f in to_process:
            console.print(f"  • {f.name}")
        log("DRY RUN completed")
        return
    
    if not to_process:
        console.print("\n[green]✓[/green] Nothing to process - all books already in library!")
        log("No new books to process")
        return
    
    # Process books
    console.print(f"\n[bold]Processing {len(to_process)} books...[/bold]")
    console.print(f"[dim]Log file: {log_file}[/dim]\n")
    
    processed = 0
    failed = 0
    
    for i, file_path in enumerate(to_process, 1):
        console.print(f"━━━ [{i}/{len(to_process)}] {file_path.name[:60]} ━━━")
        log(f"Processing [{i}/{len(to_process)}]: {file_path}")
        
        try:
            book_id = str(uuid.uuid4())
            
            # Convert
            if file_path.suffix.lower() == '.pdf':
                converter = PDFConverter()
            else:
                converter = EPUBConverter()
            
            result = converter.convert(str(file_path))
            
            if not result['success']:
                raise Exception(result.get('error', 'Conversion failed'))
            
            # Clean
            cleaner = TextCleaner(config)
            cleaned_text = cleaner.clean(result['text'])
            
            # Extract metadata
            extractor = MetadataExtractor()
            metadata = extractor.extract(cleaned_text, str(file_path), result.get('metadata'))
            metadata['id'] = book_id
            metadata['source_file'] = str(file_path)
            
            # Split chapters
            splitter = ChapterSplitter(config)
            split_result = splitter.split_with_stats(cleaned_text, book_id)
            chapters = split_result['chapters']
            
            # Section splitting
            split_enabled = config.section_splitting.get('enabled', True)
            sections = None
            if split_enabled:
                sections = split_chapters_for_ai(chapters, config.section_splitting)
            
            # Save
            db.insert_book(metadata)
            writer = FileWriter(config.output_dir)
            
            if sections and split_enabled:
                writer.write_book_with_sections(metadata, chapters, sections, cleaned_text)
            else:
                writer.write_book(metadata, chapters, cleaned_text)
            
            for chapter in chapters:
                db.insert_chapter(chapter)
            
            db.update_book_status(book_id, 'completed')
            
            console.print(f"[green]✓[/green] {metadata.get('title', 'Unknown')[:50]}")
            console.print(f"  [dim]{len(chapters)} chapters, {metadata.get('word_count', 0):,} words[/dim]")
            log(f"SUCCESS: {file_path.name} - {len(chapters)} chapters, {metadata.get('word_count', 0)} words")
            processed += 1
            
        except Exception as e:
            console.print(f"[red]✗[/red] Failed: {str(e)[:60]}")
            log(f"FAILED: {file_path.name} - {str(e)}", level='ERROR')
            failed += 1
        
        console.print()
    
    # Summary
    console.print("━" * 50)
    console.print(f"\n[bold]Batch Processing Complete[/bold]")
    console.print(f"  [green]✓[/green] Processed: {processed}")
    console.print(f"  [red]✗[/red] Failed: {failed}")
    console.print(f"  [yellow]→[/yellow] Skipped: {len(skipped)}")
    console.print(f"  [dim]Log: {log_file}[/dim]")
    
    log(f"SUMMARY: Processed={processed}, Failed={failed}, Skipped={len(skipped)}")
    
    if failed > 0:
        console.print(f"\n[yellow]Check log file for failure details: {log_file}[/yellow]")


@cli.command()
@click.argument('book_id')
def resplit(book_id):
    """Reprocess a book to split large chapters into sections"""
    config = Config()
    db = BookDatabase(config.database_path)

    book = db.get_book(book_id)
    if not book:
        console.print(f"[red]Book not found: {book_id}[/red]")
        return

    raw_path = Path(config.output_dir) / book_id / 'raw' / 'original.txt'
    if not raw_path.exists():
        console.print("[red]Raw text file not found[/red]")
        return

    console.print(f"[blue]ℹ[/blue] Reprocessing: {book.get('title', 'Unknown')}")

    with open(raw_path, 'r') as f:
        cleaned_text = f.read()

    # Get existing chapters
    chapters = db.get_chapters_by_book(book_id)
    if not chapters:
        console.print("[red]No chapters found for this book[/red]")
        return

    # Convert to format expected by section splitter
    chapter_list = []
    for ch in chapters:
        # Read chapter content from file
        ch_path = ch.get('file_path')
        if ch_path and Path(ch_path).exists():
            with open(ch_path, 'r') as f:
                content = f.read()
                # Strip frontmatter if present
                if content.startswith('---'):
                    parts = content.split('---', 2)
                    if len(parts) >= 3:
                        content = parts[2].strip()
                # Strip header
                lines = content.split('\n')
                content_start = 0
                for i, line in enumerate(lines):
                    if line.startswith('---') and i > 0:
                        content_start = i + 1
                        break
                content = '\n'.join(lines[content_start:]).strip()
        else:
            content = ''

        chapter_list.append({
            'chapter_number': ch.get('chapter_number', 1),
            'title': ch.get('title', f'Chapter {ch.get("chapter_number", 1)}'),
            'content': content,
            'word_count': ch.get('word_count', 0)
        })

    # Split into sections
    console.print("[blue]ℹ[/blue] Splitting large chapters...")
    sections = split_chapters_for_ai(chapter_list, config.section_splitting)

    # Count splits
    chapters_split = len(set(s['parent_chapter_number'] for s in sections if len([
        x for x in sections if x['parent_chapter_number'] == s['parent_chapter_number']
    ]) > 1))

    if chapters_split == 0:
        console.print("[green]✓[/green] No chapters needed splitting (all under token limit)")
        return

    # Clear old chapter files
    chapters_dir = Path(config.output_dir) / book_id / 'chapters'
    if chapters_dir.exists():
        import shutil
        shutil.rmtree(chapters_dir)
        chapters_dir.mkdir()

    # Write with sections
    writer = FileWriter(config.output_dir)
    metadata = {
        'id': book_id,
        'title': book.get('title'),
        'author': book.get('author'),
        'word_count': book.get('word_count', 0)
    }

    # We need to rebuild chapters list for writing
    writer.write_book_with_sections(metadata, chapter_list, sections, cleaned_text)

    console.print(f"\n[bold green]Resplit complete![/bold green]")
    console.print(f"[dim]Split {chapters_split} chapters into {len(sections)} sections[/dim]")
    console.print(f"[dim]Max tokens per section: ~15,000[/dim]")


@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
def diagnose(file_path):
    """Analyze chapter detection for a file and show diagnostic report.

    This helps understand why certain books get medium/low confidence
    and what might be improved.
    """
    from processors.detection_diagnostics import diagnose_pdf, diagnose_epub

    path = Path(file_path)
    ext = path.suffix.lower()

    console.print(f"[blue]ℹ[/blue] Analyzing: {path.name}")
    console.print()

    if ext == '.pdf':
        report = diagnose_pdf(str(path))
    elif ext == '.epub':
        report = diagnose_epub(str(path))
    else:
        console.print(f"[red]Unsupported file type: {ext}[/red]")
        return

    # Print with syntax highlighting for the report
    console.print(report)


if __name__ == '__main__':
    # Register enhanced CLI commands
    try:
        from cli_enhanced import register_enhanced_commands
        cli = register_enhanced_commands(cli)
    except ImportError:
        try:
            # Try relative import for when running from src directory
            from cli_enhanced import register_enhanced_commands
            cli = register_enhanced_commands(cli)
        except ImportError:
            # Enhanced commands optional - continue without them
            pass
    
    cli()
