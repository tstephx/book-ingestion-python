"""
Enhanced CLI commands for book validation and analysis.

Add to existing CLI by importing these commands.
"""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from pathlib import Path
from typing import Optional

console = Console()


def register_enhanced_commands(cli):
    """Register enhanced commands with the main CLI group"""
    
    @cli.command()
    @click.argument('book_id')
    @click.option('--mode', '-m', type=click.Choice(['quick', 'standard', 'thorough']), 
                  default='standard', help='Analysis thoroughness level')
    @click.option('--semantic/--no-semantic', default=True, 
                  help='Enable semantic boundary analysis')
    @click.option('--output', '-o', type=click.Path(), help='Save report to file')
    def analyze(book_id, mode, semantic, output):
        """Deep analysis of a book's chapter detection quality.
        
        Provides comprehensive quality metrics including:
        - Text cleaning statistics
        - Chapter size distribution
        - Semantic boundary alignment
        - Quality score and recommendations
        """
        from utils.config import Config
        from storage.database import BookDatabase
        from processors.enhanced_pipeline import EnhancedPipeline, ProcessingMode
        from processors.semantic_chunker import validate_chunking, ChapterBoundaryValidator
        from processors.profiler import DataProfiler
        
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
        
        console.print(f"\n[bold cyan]📊 Deep Analysis: {book['title'][:50]}[/bold cyan]\n")
        
        with open(raw_path, 'r') as f:
            text = f.read()
        
        # Quick validation check
        console.print("[bold]1. Quick Validation[/bold]")
        quick_result = validate_chunking(chapters)
        
        if quick_result['valid']:
            console.print("   [green]✓ Passes basic validation[/green]")
        else:
            console.print(f"   [red]✗ Issue: {quick_result['issue']}[/red]")
            if quick_result.get('message'):
                console.print(f"   [dim]{quick_result['message']}[/dim]")
        
        metrics = quick_result['metrics']
        console.print(f"   Chapters: {metrics['chapter_count']}")
        console.print(f"   Avg words: {metrics['avg_words']:,.0f}")
        console.print(f"   Range: {metrics.get('min_words', 0):,} - {metrics.get('max_words', 0):,}")
        
        # Data profiling
        console.print("\n[bold]2. Quality Profile[/bold]")
        profiler = DataProfiler()
        profile = profiler.profile_book(book, chapters)
        quality = profiler.assess_quality(profile)
        
        # Quality score with color
        score = quality.quality_score
        score_color = "green" if score >= 75 else "yellow" if score >= 50 else "red"
        console.print(f"   Quality Score: [{score_color}]{score}/100[/{score_color}]")
        
        if quality.warnings:
            console.print("\n   [yellow]Warnings:[/yellow]")
            for warning in quality.warnings:
                console.print(f"   ⚠️  {warning}")
        
        if quality.info:
            console.print("\n   [blue]Info:[/blue]")
            for info in quality.info:
                console.print(f"   ℹ️  {info}")
        
        # Semantic analysis (if enabled and mode is thorough)
        if semantic and mode == 'thorough':
            console.print("\n[bold]3. Semantic Boundary Analysis[/bold]")
            try:
                validator = ChapterBoundaryValidator(use_semantic=True)
                semantic_result = validator.validate_chapters(text, chapters)
                
                console.print(f"   Overall confidence: {semantic_result.overall_confidence:.0%}")
                console.print(f"   Chapters with semantic boundary: {semantic_result.statistics.get('chapters_with_semantic_boundary', 0)}/{len(chapters)}")
                
                if semantic_result.recommendations:
                    console.print("\n   [cyan]Recommendations:[/cyan]")
                    for rec in semantic_result.recommendations[:5]:  # Limit to 5
                        console.print(f"   💡 {rec}")
                        
            except ImportError:
                console.print("   [yellow]Semantic analysis requires sentence-transformers[/yellow]")
                console.print("   [dim]Install with: pip install sentence-transformers[/dim]")
            except Exception as e:
                console.print(f"   [red]Semantic analysis failed: {e}[/red]")
        
        # Chapter size distribution table
        console.print("\n[bold]4. Chapter Size Distribution[/bold]")
        
        table = Table(show_header=True, header_style="bold")
        table.add_column("#", justify="right", width=4)
        table.add_column("Title", width=40)
        table.add_column("Words", justify="right", width=10)
        table.add_column("Status", width=12)
        
        target_min = 3000
        target_max = 15000
        
        for ch in chapters:
            ch_num = ch.get('chapter_number', '?')
            title = ch.get('title', 'Unknown')[:38]
            words = ch.get('word_count', 0)
            
            if words < target_min:
                status = "[yellow]Under[/yellow]"
            elif words > target_max:
                status = "[red]Over[/red]"
            else:
                status = "[green]Good[/green]"
            
            table.add_row(str(ch_num), title, f"{words:,}", status)
        
        console.print(table)
        
        # Recommendations summary
        console.print("\n[bold]5. Action Items[/bold]")
        
        recommendations = []
        
        if not quick_result['valid']:
            if quick_result['issue'] == 'over-fragmentation':
                recommendations.append("Consider merging small chapters that are fragments of larger chapters")
            elif quick_result['issue'] == 'under-fragmentation':
                recommendations.append("Large chapters may need additional splitting")
        
        if score < 75:
            recommendations.append("Review chapter detection patterns for this book format")
        
        undersized = sum(1 for ch in chapters if ch.get('word_count', 0) < target_min)
        if undersized > len(chapters) * 0.3:
            recommendations.append(f"{undersized} chapters are undersized - consider batch merging")
        
        oversized = sum(1 for ch in chapters if ch.get('word_count', 0) > target_max)
        if oversized > 0:
            recommendations.append(f"{oversized} chapters exceed target size - use section splitting")
        
        if recommendations:
            for rec in recommendations:
                console.print(f"   → {rec}")
        else:
            console.print("   [green]✓ No action items - book is well-processed[/green]")
        
        # Save report if requested
        if output:
            report = profiler.generate_report(profile)
            Path(output).write_text(report)
            console.print(f"\n[dim]Report saved to: {output}[/dim]")
    
    @cli.command()
    @click.option('--min-score', '-s', type=int, default=0, 
                  help='Minimum quality score to show')
    @click.option('--issues-only', is_flag=True, 
                  help='Only show books with issues')
    @click.option('--format', '-f', type=click.Choice(['table', 'detailed']), 
                  default='table', help='Output format')
    def quality_report(min_score, issues_only, format):
        """Generate quality report for all processed books.
        
        Shows quality metrics, scores, and identifies books needing attention.
        """
        from utils.config import Config
        from storage.database import BookDatabase
        from processors.profiler import DataProfiler
        from processors.semantic_chunker import validate_chunking
        
        config = Config()
        db = BookDatabase(config.database_path)
        books = db.get_all_books()
        
        if not books:
            console.print("[yellow]No books found.[/yellow]")
            return
        
        console.print(f"\n[bold cyan]📊 Library Quality Report[/bold cyan]\n")
        
        profiler = DataProfiler()
        results = []
        
        for book in books:
            book_id = book['id']
            chapters = db.get_chapters_by_book(book_id)
            
            profile = profiler.profile_book(book, chapters)
            quality = profiler.assess_quality(profile)
            quick = validate_chunking(chapters)
            
            results.append({
                'book': book,
                'profile': profile,
                'quality': quality,
                'quick': quick,
            })
        
        # Filter results
        if min_score > 0:
            results = [r for r in results if r['quality'].quality_score >= min_score]
        
        if issues_only:
            results = [r for r in results 
                      if not r['quick']['valid'] or r['quality'].quality_score < 75]
        
        if not results:
            console.print("[green]All books pass quality checks![/green]")
            return
        
        # Sort by quality score
        results.sort(key=lambda x: x['quality'].quality_score)
        
        if format == 'table':
            table = Table(show_header=True, header_style="bold")
            table.add_column("Title", width=35)
            table.add_column("Chapters", justify="right", width=8)
            table.add_column("Words", justify="right", width=10)
            table.add_column("Avg Ch", justify="right", width=8)
            table.add_column("Score", justify="right", width=6)
            table.add_column("Status", width=15)
            
            for r in results:
                book = r['book']
                profile = r['profile']
                quality = r['quality']
                quick = r['quick']
                
                title = book.get('title', 'Unknown')[:33]
                score = quality.quality_score
                score_str = f"[{'green' if score >= 75 else 'yellow' if score >= 50 else 'red'}]{score}[/]"
                
                status = ""
                if not quick['valid']:
                    status = f"[red]{quick['issue']}[/red]"
                elif quality.warnings:
                    status = "[yellow]warnings[/yellow]"
                else:
                    status = "[green]OK[/green]"
                
                table.add_row(
                    title,
                    str(profile.total_chapters),
                    f"{profile.total_words:,}",
                    f"{profile.avg_chapter_words:,.0f}",
                    score_str,
                    status
                )
            
            console.print(table)
        
        else:  # detailed format
            for r in results:
                book = r['book']
                quality = r['quality']
                quick = r['quick']
                
                score = quality.quality_score
                score_color = "green" if score >= 75 else "yellow" if score >= 50 else "red"
                
                console.print(f"\n[bold]{book.get('title', 'Unknown')[:50]}[/bold]")
                console.print(f"   Score: [{score_color}]{score}/100[/{score_color}]")
                
                if not quick['valid']:
                    console.print(f"   [red]Issue: {quick['issue']}[/red]")
                
                for warning in quality.warnings[:3]:
                    console.print(f"   ⚠️ {warning}")
        
        # Summary
        total = len(results)
        good = sum(1 for r in results if r['quality'].quality_score >= 75)
        fair = sum(1 for r in results if 50 <= r['quality'].quality_score < 75)
        poor = sum(1 for r in results if r['quality'].quality_score < 50)
        
        console.print(f"\n[bold]Summary:[/bold]")
        console.print(f"   Total: {total} books")
        console.print(f"   [green]Good (≥75):[/green] {good}")
        console.print(f"   [yellow]Fair (50-74):[/yellow] {fair}")
        console.print(f"   [red]Poor (<50):[/red] {poor}")
    
    @cli.command()
    @click.argument('book_id')
    @click.option('--dry-run', is_flag=True, help='Show what would be merged without making changes')
    @click.option('--min-words', type=int, default=3000, help='Minimum words per chapter')
    def merge_chapters(book_id, dry_run, min_words):
        """Merge small chapters that appear to be over-fragmented.
        
        Identifies chapters below the minimum word threshold and suggests
        or performs merges with adjacent chapters.
        """
        from utils.config import Config
        from storage.database import BookDatabase
        
        config = Config()
        db = BookDatabase(config.database_path)
        
        book = db.get_book(book_id)
        if not book:
            console.print(f"[red]Book not found: {book_id}[/red]")
            return
        
        chapters = db.get_chapters_by_book(book_id)
        if not chapters:
            console.print("[yellow]No chapters found[/yellow]")
            return
        
        console.print(f"\n[bold cyan]Analyzing chapters for merging: {book['title'][:40]}[/bold cyan]\n")
        
        # Find merge candidates
        merge_candidates = []
        for i, ch in enumerate(chapters):
            word_count = ch.get('word_count', 0)
            if word_count < min_words:
                merge_candidates.append({
                    'index': i,
                    'chapter': ch,
                    'word_count': word_count,
                })
        
        if not merge_candidates:
            console.print(f"[green]✓ All chapters meet minimum word count ({min_words})[/green]")
            return
        
        console.print(f"Found {len(merge_candidates)} chapters below {min_words} words:\n")
        
        # Plan merges (prefer merging with previous chapter)
        merge_plan = []
        skip_indices = set()
        
        for candidate in merge_candidates:
            idx = candidate['index']
            if idx in skip_indices:
                continue
            
            ch = candidate['chapter']
            words = candidate['word_count']
            
            # Determine merge direction
            if idx > 0 and (idx - 1) not in skip_indices:
                # Merge with previous
                prev_ch = chapters[idx - 1]
                combined = prev_ch.get('word_count', 0) + words
                merge_plan.append({
                    'merge_into': idx - 1,
                    'merge_from': idx,
                    'combined_words': combined,
                    'title_keep': prev_ch.get('title'),
                    'title_drop': ch.get('title'),
                })
                skip_indices.add(idx)
            elif idx < len(chapters) - 1:
                # Merge with next
                next_ch = chapters[idx + 1]
                combined = words + next_ch.get('word_count', 0)
                merge_plan.append({
                    'merge_into': idx,
                    'merge_from': idx + 1,
                    'combined_words': combined,
                    'title_keep': ch.get('title'),
                    'title_drop': next_ch.get('title'),
                })
                skip_indices.add(idx + 1)
        
        # Show merge plan
        table = Table(show_header=True, header_style="bold")
        table.add_column("Action", width=8)
        table.add_column("Keep", width=25)
        table.add_column("Merge", width=25)
        table.add_column("Result", justify="right", width=12)
        
        for plan in merge_plan:
            table.add_row(
                "Merge",
                plan['title_keep'][:23] if plan['title_keep'] else "?",
                f"← {plan['title_drop'][:21]}" if plan['title_drop'] else "?",
                f"{plan['combined_words']:,} words"
            )
        
        console.print(table)
        
        if dry_run:
            console.print(f"\n[dim]Dry run - no changes made. Remove --dry-run to apply merges.[/dim]")
            return
        
        # TODO: Implement actual merge logic
        console.print(f"\n[yellow]Merge execution not yet implemented.[/yellow]")
        console.print("[dim]Use this analysis to manually adjust chapter boundaries.[/dim]")
    
    @cli.command()
    @click.argument('file_path', type=click.Path(exists=True))
    @click.option('--mode', '-m', type=click.Choice(['quick', 'standard', 'thorough']), 
                  default='standard', help='Processing mode')
    def preview(file_path, mode):
        """Preview chapter detection without saving to database.
        
        Useful for testing detection quality before full processing.
        """
        from converters.pdf_converter import PDFConverter
        from converters.epub_converter import EPUBConverter
        from processors.enhanced_pipeline import EnhancedPipeline, ProcessingMode
        from processors.enhanced_text_cleaner import EnhancedTextCleaner
        from utils.config import Config
        import uuid
        
        file_path = Path(file_path)
        config = Config()
        
        console.print(f"\n[bold cyan]Preview: {file_path.name}[/bold cyan]\n")
        
        # Convert file
        console.print("[dim]Converting...[/dim]")
        
        if file_path.suffix.lower() == '.pdf':
            converter = PDFConverter()
            result = converter.convert(str(file_path))
        elif file_path.suffix.lower() == '.epub':
            converter = EPUBConverter()
            result = converter.convert(str(file_path))
        else:
            console.print(f"[red]Unsupported format: {file_path.suffix}[/red]")
            return
        
        if not result.get('success'):
            console.print(f"[red]Conversion failed: {result.get('error')}[/red]")
            return
        
        text = result['text']
        external_toc = result.get('toc_titles', [])
        
        console.print(f"[green]✓[/green] Converted: {len(text):,} characters")
        
        # Run enhanced pipeline
        console.print("[dim]Analyzing...[/dim]")
        
        processing_mode = ProcessingMode(mode)
        pipeline = EnhancedPipeline(mode=processing_mode)
        
        book_id = str(uuid.uuid4())[:8]  # Short ID for preview
        pipeline_result = pipeline.process_book(
            text, 
            book_id, 
            external_toc_titles=external_toc
        )
        
        # Display results
        console.print(f"\n[bold]Detection Results[/bold]")
        console.print(f"   Method: {pipeline_result.detection_method}")
        console.print(f"   Confidence: {pipeline_result.detection_confidence:.0%}")
        console.print(f"   Chapters: {len(pipeline_result.chapters)}")
        console.print(f"   Quality Score: {pipeline_result.quality_report.quality_score}/100")
        
        # Text cleaning stats
        stats = pipeline_result.cleaning_stats
        console.print(f"\n[bold]Text Cleaning[/bold]")
        console.print(f"   Bytes saved: {stats.bytes_saved:,} ({stats.reduction_percent:.1f}%)")
        console.print(f"   Smart quotes: {stats.smart_quotes_replaced}")
        console.print(f"   Page numbers: {stats.page_numbers_removed}")
        
        # Chapter list
        console.print(f"\n[bold]Chapters Detected[/bold]")
        
        table = Table(show_header=True, header_style="bold")
        table.add_column("#", justify="right", width=4)
        table.add_column("Title", width=45)
        table.add_column("Words", justify="right", width=10)
        
        for ch in pipeline_result.chapters:
            table.add_row(
                str(ch.get('chapter_number', '?')),
                ch.get('title', 'Unknown')[:43],
                f"{ch.get('word_count', 0):,}"
            )
        
        console.print(table)
        
        # Warnings and recommendations
        if pipeline_result.warnings:
            console.print(f"\n[bold yellow]Warnings[/bold yellow]")
            for warning in pipeline_result.warnings:
                console.print(f"   ⚠️ {warning}")
        
        if pipeline_result.recommendations:
            console.print(f"\n[bold cyan]Recommendations[/bold cyan]")
            for rec in pipeline_result.recommendations:
                console.print(f"   💡 {rec}")
        
        # Summary
        console.print(f"\n[bold]Summary[/bold]")
        if pipeline_result.is_valid:
            console.print("   [green]✓ Ready for processing[/green]")
        elif pipeline_result.needs_review:
            console.print("   [yellow]⚠ Needs review before processing[/yellow]")
        else:
            console.print("   [red]✗ Issues detected - review recommended[/red]")
    
    return cli
