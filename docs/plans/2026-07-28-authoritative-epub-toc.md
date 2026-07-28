# Authoritative EPUB TOC Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent reliable publisher TOCs from being diluted by heuristic chapter candidates and restore accurate book-level word counts.

**Architecture:** Make `CandidateExtractor` treat three or more resolved chapter-level EPUB anchors as authoritative, while preserving the existing mixed fallback for sparse anchor maps. Restore the chapter-sum rollup at the application storage boundary.

**Tech Stack:** Python 3.12, pytest, EbookLib data types, SQLite storage.

### Task 1: Restore the book word-count rollup

**Files:**
- Modify: `book_ingestion/bootstrap.py`
- Test: `tests/processors/test_pipeline.py::TestBootstrapWordCount::test_save_to_storage_sets_word_count_from_chapter_sum`

**Step 1: Verify the existing regression fails**

Run:

```bash
python -m pytest tests/processors/test_pipeline.py::TestBootstrapWordCount::test_save_to_storage_sets_word_count_from_chapter_sum -q
```

Expected: FAIL because the stored value is `0` instead of `20000`.

**Step 2: Write the minimal implementation**

Immediately before `db.insert_book(metadata)`, assign:

```python
metadata["word_count"] = sum(
    chapter.get("word_count", 0) for chapter in pipeline_result.chapters
)
```

**Step 3: Verify the regression passes**

Run the same focused test. Expected: PASS.

**Step 4: Commit**

```bash
git add book_ingestion/bootstrap.py
git commit -m "fix: persist chapter-sum book word counts"
```

### Task 2: Reproduce heuristic leakage beside a reliable EPUB TOC

**Files:**
- Modify: `tests/converters/test_enhanced_epub.py`

**Step 1: Write the failing regression**

Create a synthetic text with three major regional chapters, a title-case
back-matter heading, and matching `EnhancedTOC` split points plus
`AnchorLocation` records. Call `CandidateExtractor.extract()` and assert:

```python
assert [candidate.title for candidate in candidates] == [
    "1: Plan Your Visit",
    "2: Northern Region",
    "3: Southern Region",
]
assert all(candidate.match_type == MatchType.EPUB_ANCHOR for candidate in candidates)
```

**Step 2: Verify the regression fails**

Run:

```bash
python -m pytest tests/converters/test_enhanced_epub.py::TestIntegrationWithChapterDetector::test_reliable_epub_anchors_exclude_heuristic_headings -q
```

Expected: FAIL because the title-case back-matter candidate is also returned.

### Task 3: Make reliable EPUB anchors authoritative

**Files:**
- Modify: `book_ingestion/processors/chapter_detector.py`
- Test: `tests/converters/test_enhanced_epub.py`

**Step 1: Write the minimal implementation**

Add a named reliability threshold to `CandidateExtractor`:

```python
MIN_RELIABLE_EPUB_ANCHORS = 3
```

In the existing `if anchor_candidates:` branch, return `anchor_candidates`
immediately when their count meets the threshold. Leave the current
non-overlapping heuristic merge unchanged below it for sparse anchor maps.

**Step 2: Verify the focused regression passes**

Run the test from Task 2. Expected: PASS.

**Step 3: Verify related suites**

Run:

```bash
python -m pytest tests/converters/test_enhanced_epub.py tests/processors/test_chapter_detector.py tests/processors/test_chapter_splitter.py -q
```

Expected: all tests PASS.

**Step 4: Commit**

```bash
git add tests/converters/test_enhanced_epub.py book_ingestion/processors/chapter_detector.py
git commit -m "fix: trust reliable EPUB chapter anchors"
```

### Task 4: Verify and integrate

**Files:**
- Modify: `book_ingestion/processors/chapter_splitter.py`
- Modify: `book_ingestion/processors/enhanced_pipeline.py`
- Test: `tests/processors/test_quality_resplit.py`
- Test: `tests/processors/test_enhanced_pipeline.py`

**Step 1: Preserve the post-clean size invariant**

Add failing regressions showing that:

- punctuation normalization cannot leave an anchor-derived chapter over the
  quality cap;
- a single oversized paragraph is split below the cap without duplicate part
  titles; and
- dense content is balanced instead of producing a tiny final remainder.

Expose the existing quality-limit pass through a public method and apply it
after cleaning anchor-derived chapters. Balance dense word chunks and normalize
repeated part suffixes.

**Step 2: Run the full suite**

Run all tests with the project environment. Record any baseline-only
semantic-model failure separately; no other failure is acceptable.

**Step 3: Dry-run the audited EPUB**

Process the source with `save_to_storage=False` and no forced fallback.
Expected: `epub_anchor`, high confidence, no heuristic regional-imprint title.

**Step 4: Review the diff**

Check `git diff --check`, inspect the branch diff, and verify no
source-specific text entered production code.

**Step 5: Merge locally**

Merge the branch into local `main` after verification.

### Task 5: Reingest and audit live

**Files:**
- Live pipeline database and managed output only.

**Step 1: Create a fresh SQLite backup**

Use the project-supported backup mechanism before live reingestion.

**Step 2: Restart the worker**

Restart the LaunchAgent so the long-running process imports the merged library.

**Step 3: Reingest without forced fallback**

Run `agentic-pipeline reingest` for the pending Fodor's pipeline without
`--force-fallback`.

**Step 4: Wait for a terminal review state**

Poll with bounded status checks until it reaches `pending_approval`,
`needs_retry`, or a terminal failure.

**Step 5: Audit read-only**

Verify detection method, validation result, chapter titles/counts, stored book
word count, source coverage, audit records, and absence of embeddings. Do not
approve the book.
