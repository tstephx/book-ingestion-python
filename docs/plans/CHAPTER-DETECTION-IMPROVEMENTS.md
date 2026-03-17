---
status: active
tags: [project/book-ingestion-python, format/plan]
type: note
created: '2025-12-22'
modified: '2025-12-22'
---

# Chapter Detection Improvements

This document describes the improvements made to the book-ingestion-python project for better chapter detection and validation, based on LangChain best practices.

## Overview

The improvements address three main issues identified in the book ingestion pipeline:

1. **Over-fragmentation**: Too many small "chapters" being detected (e.g., 56 detected vs 12 actual)
2. **Missing quality validation**: No metrics to detect detection problems
3. **Semantic boundary alignment**: Chapter boundaries don't align with topic changes

## New Modules

### 1. Semantic Chunker (`src/processors/semantic_chunker.py`)

LangChain-inspired chunking with semantic analysis.

#### Key Classes

**`RecursiveTextSplitter`** - LangChain-style recursive text splitter
```python
from src.processors.semantic_chunker import RecursiveTextSplitter

splitter = RecursiveTextSplitter(
    chunk_size=1500,      # Target chunk size in characters
    chunk_overlap=200,    # Overlap between chunks
    separators=["\n\n", "\n", ". ", " ", ""]  # Priority order
)

chunks = splitter.split_text(text)
```

**`SemanticChunker`** - Embedding-based topic detection
```python
from src.processors.semantic_chunker import SemanticChunker

# Requires: pip install sentence-transformers
chunker = SemanticChunker(
    buffer_size=200,              # Words per comparison chunk
    breakpoint_threshold=0.7,     # Similarity below = topic change
    use_percentile=True,          # Use dynamic threshold
    percentile_threshold=0.9      # 90th percentile for topic shifts
)

boundaries = chunker.detect_boundaries(text)
# Returns list of SemanticBoundary objects with:
# - position, line_index
# - similarity_score
# - is_significant (topic shift detected)
```

**`ChapterBoundaryValidator`** - Validates detected chapters
```python
from src.processors.semantic_chunker import ChapterBoundaryValidator

validator = ChapterBoundaryValidator(use_semantic=True)
result = validator.validate_chapters(text, chapters)

# Result includes:
# - chapter_validations: list of ChapterValidation objects
# - overall_confidence: 0-1 score
# - recommendations: list of suggested fixes
# - statistics: dict with validation metrics
```

**`validate_chunking()`** - Quick validation function
```python
from src.processors.semantic_chunker import validate_chunking

result = validate_chunking(chapters)
# Returns: {
#   "valid": bool,
#   "issue": str or None,
#   "metrics": {chapter_count, avg_words, total_words, min_words, max_words}
# }
```

### 2. Chunk Merger (`src/processors/chunk_merger.py`)

Intelligent chapter merging for over-fragmented content.

#### Key Classes

**`ChapterMerger`** - Main merger class
```python
from src.processors.chunk_merger import ChapterMerger

merger = ChapterMerger()

# Check if merging is needed
if merger.should_merge_chapters(chapters):
    # Find merge candidates
    candidates = merger.find_merge_candidates(chapters)
    
    # Perform merges
    result = merger.merge_chapters(chapters, max_merges=5)
    
    # Or auto-merge to target size
    result = merger.auto_merge(chapters, target_avg_words=8000)
```

**`MergeCandidate`** - Potential merge pair
```python
@dataclass
class MergeCandidate:
    first_index: int           # Index of first chapter
    second_index: int          # Index of second chapter
    combined_word_count: int   # Words after merge
    merge_score: float         # 0-1, higher = better candidate
    merge_reasons: List[str]   # Why merge is recommended
```

**`MergeResult`** - Result of merge operation
```python
@dataclass
class MergeResult:
    original_count: int
    merged_count: int
    merges_performed: int
    merge_details: List[Tuple[int, int]]
    chapters: List[Dict]
    quality_improvement: float
```

#### Convenience Function
```python
from src.processors.chunk_merger import merge_undersized_chapters

# Simple API for common case
merged = merge_undersized_chapters(
    chapters,
    min_words=2000,     # Merge chapters under this size
    max_combined=20000  # Don't exceed this when merging
)
```

## New Scripts

### 1. Library Validation (`scripts/validate_library.py`)

Analyze all books for quality issues.

```bash
# Validate all books
python scripts/validate_library.py

# Single book
python scripts/validate_library.py --book-id <uuid>

# Export report
python scripts/validate_library.py --export report.md

# Include semantic analysis (slower)
python scripts/validate_library.py --semantic
```

Output includes:
- Summary statistics
- Books with issues (table)
- Over-fragmented books (priority list)
- Recommendations

### 2. Reprocess Problematic Books (`scripts/reprocess_problematic.py`)

Fix books with quality issues.

```bash
# List problematic books
python scripts/reprocess_problematic.py --list

# Preview fixes (dry run)
python scripts/reprocess_problematic.py --book-id <uuid> --dry-run

# Fix single book
python scripts/reprocess_problematic.py --book-id <uuid>

# Fix all problematic books
python scripts/reprocess_problematic.py --fix-all

# Skip confirmation
python scripts/reprocess_problematic.py --fix-all --no-confirm
```

## Quality Thresholds

### Target Chapter Sizes
| Metric | Minimum | Ideal | Maximum |
|--------|---------|-------|---------|
| Words per chapter | 2,000 | 8,000 | 20,000 |
| Chapters per book | 3 | varies | 40 |
| Words per 100K | 3-5 chapters | ~10 | 15 |

### Validation Checks

1. **Over-fragmentation**: avg_words < 2,000
2. **Under-fragmentation**: avg_words > 25,000
3. **Suspicious count**: >40 chapters with avg < 5,000
4. **Too few chapters**: < expected based on word count

## Configuration

New options in `config/config.json`:

```json
{
  "quality_validation": {
    "min_avg_words": 2000,
    "max_avg_words": 25000,
    "max_chapter_count": 40,
    "min_chapter_count": 3,
    "warn_on_over_fragmentation": true,
    "auto_merge_threshold": 0.3
  },
  "semantic_chunking": {
    "enabled": false,
    "buffer_size": 200,
    "breakpoint_threshold": 0.7,
    "use_percentile": true,
    "percentile_threshold": 0.9,
    "model": "all-MiniLM-L6-v2"
  }
}
```

## Usage Examples

### Example 1: Validate a Book's Chapters

```python
from src.processors.semantic_chunker import validate_chunking

chapters = [
    {'word_count': 5000, 'title': 'Chapter 1'},
    {'word_count': 6000, 'title': 'Chapter 2'},
    # ...
]

result = validate_chunking(chapters)
if not result['valid']:
    print(f"Issue: {result['issue']}")
    print(f"Avg words: {result['metrics']['avg_words']}")
```

### Example 2: Fix Over-Fragmented Book

```python
from src.processors.chunk_merger import ChapterMerger

merger = ChapterMerger()
chapters = get_book_chapters(book_id)  # Your function

if merger.should_merge_chapters(chapters):
    result = merger.auto_merge(chapters)
    print(f"Merged {result.original_count} -> {result.merged_count} chapters")
    print(f"Quality improved by {result.quality_improvement:.0f} avg words")
    
    # Save merged chapters
    save_chapters(result.chapters)
```

### Example 3: Semantic Validation

```python
from src.processors.semantic_chunker import ChapterBoundaryValidator

validator = ChapterBoundaryValidator(use_semantic=True)
result = validator.validate_chapters(full_text, chapters)

for validation in result.chapter_validations:
    if not validation.is_valid:
        print(f"Chapter {validation.chapter_index}: {validation.merge_reason}")

for rec in result.recommendations:
    print(f"Recommendation: {rec}")
```

## Dependencies

### Required
- All existing dependencies from requirements.txt

### Optional (for semantic analysis)
```bash
pip install sentence-transformers numpy
```

Without sentence-transformers, semantic analysis is disabled but all other features work.

## Testing

Run tests for new modules:

```bash
# All tests
pytest tests/processors/

# Specific modules
pytest tests/processors/test_semantic_chunker.py
pytest tests/processors/test_chunk_merger.py

# With coverage
pytest --cov=src/processors tests/processors/
```

## Integration with Existing Pipeline

The new modules integrate with the existing pipeline:

1. **During ingestion**: Add validation after chapter detection
2. **Post-processing**: Run validate_library.py to find issues
3. **Fixing**: Use reprocess_problematic.py to fix detected issues

### Recommended Workflow

```bash
# 1. Process new books
./batch_process.sh /path/to/books

# 2. Validate library
python scripts/validate_library.py --export quality_report.md

# 3. Review problematic books
python scripts/reprocess_problematic.py --list

# 4. Fix issues
python scripts/reprocess_problematic.py --fix-all

# 5. Regenerate embeddings (if using book-mcp-server)
cd ../book-mcp-server
python scripts/generate_embeddings.py
```

## Architecture

```
src/processors/
├── semantic_chunker.py     # NEW: Semantic analysis
│   ├── RecursiveTextSplitter
│   ├── SemanticChunker
│   ├── ChapterBoundaryValidator
│   └── validate_chunking()
├── chunk_merger.py         # NEW: Chapter merging
│   ├── ChapterMerger
│   ├── MergeCandidate
│   └── MergeResult
├── chapter_splitter.py     # EXISTING
├── chapter_detector.py     # EXISTING
├── chapter_validator.py    # EXISTING
├── text_cleaner.py         # EXISTING (enhanced)
└── profiler.py             # EXISTING

scripts/
├── validate_library.py     # NEW: Quality analysis
└── reprocess_problematic.py # NEW: Fix issues
```

## Related Documentation

- [ARCHITECTURE-REVIEW.md](../ARCHITECTURE-REVIEW.md) - Semantic search architecture
- [SEMANTIC-SEARCH-COMPLETE.md](../SEMANTIC-SEARCH-COMPLETE.md) - MCP server implementation
- [book-ingestion-analysis.md](../book-ingestion-analysis.md) - Original analysis
