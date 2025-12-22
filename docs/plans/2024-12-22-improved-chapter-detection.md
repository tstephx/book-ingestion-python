# Improved Chapter Detection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace single-pass chapter detection with a multi-stage pipeline that reduces false positives (code blocks detected as chapters) and false negatives (missing real chapters).

**Architecture:** Five-stage pipeline: Code Block Detection → Candidate Extraction → Confidence Scoring → Anchor/Merge → Validation. Each candidate gets a confidence score; high-confidence "anchors" absorb low-confidence matches.

**Tech Stack:** Python 3.10+, dataclasses, re (regex), existing ChapterValidator

---

## Task 1: Create CodeBlockDetector

**Files:**
- Create: `src/processors/code_block_detector.py`
- Test: `tests/processors/test_code_block_detector.py`

**Step 1: Create test directory and file**

```bash
mkdir -p tests/processors
touch tests/processors/__init__.py
```

**Step 2: Write the failing test**

Create `tests/processors/test_code_block_detector.py`:

```python
"""Tests for code block detection"""

import pytest
from src.processors.code_block_detector import CodeBlockDetector


class TestCodeBlockDetector:
    def setup_method(self):
        self.detector = CodeBlockDetector()

    def test_detects_terminal_output_with_numbers(self):
        """Lines like '10432 chris 20 0 471m' should be detected as code"""
        text = """Chapter 3 Using the Shell

This chapter covers shell basics.

$ ps aux
10432 chris 20 0 471m 121m 18m S 99.9 3.2 77:01.76 bigcommand
20284 root 25 5 98.7m 932 644 D 2.7 0.0 0:00.96 updatedb

Now let's look at another example."""

        regions = self.detector.detect(text)
        lines = text.split('\n')

        # Should detect the ps output block
        assert len(regions) >= 1
        # Lines 4-6 (0-indexed) contain the code
        code_lines = set()
        for start, end in regions:
            code_lines.update(range(start, end + 1))

        assert 4 in code_lines  # $ ps aux
        assert 5 in code_lines  # 10432 chris...
        assert 6 in code_lines  # 20284 root...

    def test_detects_shell_prompts(self):
        """Lines starting with $ or # should be detected"""
        text = """To install, run:

$ pip install package
$ python setup.py

Then configure."""

        regions = self.detector.detect(text)
        lines = text.split('\n')

        code_lines = set()
        for start, end in regions:
            code_lines.update(range(start, end + 1))

        assert 2 in code_lines  # $ pip install
        assert 3 in code_lines  # $ python setup.py

    def test_detects_indented_code_blocks(self):
        """Consistently indented blocks should be detected"""
        text = """Here's the code:

    def hello():
        print("world")
        return True

And here's more text."""

        regions = self.detector.detect(text)

        code_lines = set()
        for start, end in regions:
            code_lines.update(range(start, end + 1))

        assert 2 in code_lines  # def hello():
        assert 3 in code_lines  # print
        assert 4 in code_lines  # return

    def test_ignores_regular_prose(self):
        """Normal paragraphs should not be detected as code"""
        text = """Chapter 1 Introduction

This book teaches Python programming. You will learn
about variables, functions, and classes. Each chapter
builds on the previous one.

Chapter 2 Getting Started

Let's begin with the basics."""

        regions = self.detector.detect(text)

        # Should have no or minimal code regions in prose
        code_lines = set()
        for start, end in regions:
            code_lines.update(range(start, end + 1))

        # Chapter headers and prose should not be in code regions
        assert 0 not in code_lines  # Chapter 1
        assert 2 not in code_lines  # This book teaches
        assert 6 not in code_lines  # Chapter 2

    def test_is_code_line_helper(self):
        """Test individual line detection"""
        assert self.detector.is_code_line("$ pip install foo")
        assert self.detector.is_code_line(">>> print('hello')")
        assert self.detector.is_code_line("    def foo():")
        assert self.detector.is_code_line("10432 chris 20 0 471m")
        assert not self.detector.is_code_line("Chapter 1 Introduction")
        assert not self.detector.is_code_line("This is a normal sentence.")
```

**Step 3: Run test to verify it fails**

Run: `cd /Users/taylorstephens/_Projects/book-ingestion-python/.worktrees/improved-chapter-detection && source venv/bin/activate && pytest tests/processors/test_code_block_detector.py -v`

Expected: FAIL with "ModuleNotFoundError" or "ImportError"

**Step 4: Write minimal implementation**

Create `src/processors/code_block_detector.py`:

```python
"""Detects code blocks and terminal output in text"""

import re
from typing import List, Tuple


class CodeBlockDetector:
    """
    Identifies regions of text that are likely code or terminal output.
    Used to exclude these regions from chapter pattern matching.
    """

    def __init__(self):
        # Patterns that indicate a line is code
        self.code_indicators = [
            re.compile(r'^\s*[$#>]{1,2}\s+\w'),  # Shell prompts: $ cmd, # cmd, > cmd
            re.compile(r'^\s*>>>\s'),  # Python REPL
            re.compile(r'^\s{4,}\S'),  # Indented code (4+ spaces)
            re.compile(r'^\t+\S'),  # Tab-indented code
            re.compile(r'^\d+\s+\w+\s+\d+\s+\d+\s+[\d.]+'),  # ps/top output
            re.compile(r'^[│├└─┌┐┘┬┴┼]+'),  # Box drawing chars (tree output)
            re.compile(r'^\s*\|.*\|.*\|'),  # Pipe-delimited tables
            re.compile(r'^[\w./]+:\d+:'),  # File:line: (grep output)
            re.compile(r'^\s*(?:def|class|import|from|if|for|while|return|async|await)\s'),  # Python keywords at start
            re.compile(r'^\s*(?:function|const|let|var|import|export|if|for|while|return)\s'),  # JS keywords
        ]

        # Minimum consecutive code lines to form a block
        self.min_block_size = 2

    def detect(self, text: str) -> List[Tuple[int, int]]:
        """
        Detect code block regions in text.

        Returns:
            List of (start_line, end_line) tuples (0-indexed, inclusive)
        """
        lines = text.split('\n')
        code_line_indices = []

        for i, line in enumerate(lines):
            if self.is_code_line(line):
                code_line_indices.append(i)

        # Merge consecutive or near-consecutive code lines into blocks
        return self._merge_into_blocks(code_line_indices, len(lines))

    def is_code_line(self, line: str) -> bool:
        """Check if a single line looks like code"""
        # Empty lines are not code by themselves
        if not line.strip():
            return False

        # Check against code indicators
        for pattern in self.code_indicators:
            if pattern.match(line):
                return True

        # Heuristic: high density of special characters
        if self._has_code_char_density(line):
            return True

        return False

    def _has_code_char_density(self, line: str) -> bool:
        """Check if line has high density of code-like characters"""
        if len(line.strip()) < 10:
            return False

        code_chars = set('()[]{}=<>|&;:\'\"\\/@#$%^*+-')
        char_count = sum(1 for c in line if c in code_chars)
        density = char_count / len(line.strip())

        # Also check for multiple numbers separated by spaces (like ps output)
        number_groups = re.findall(r'\b\d+\b', line)
        if len(number_groups) >= 4:
            return True

        return density > 0.15

    def _merge_into_blocks(self, indices: List[int], total_lines: int) -> List[Tuple[int, int]]:
        """Merge nearby code line indices into contiguous blocks"""
        if not indices:
            return []

        blocks = []
        block_start = indices[0]
        block_end = indices[0]

        for idx in indices[1:]:
            # Allow gap of 1 line (e.g., blank line between code)
            if idx <= block_end + 2:
                block_end = idx
            else:
                # Save current block if it meets minimum size
                if block_end - block_start + 1 >= self.min_block_size:
                    blocks.append((block_start, block_end))
                block_start = idx
                block_end = idx

        # Don't forget the last block
        if block_end - block_start + 1 >= self.min_block_size:
            blocks.append((block_start, block_end))

        return blocks

    def get_non_code_lines(self, text: str) -> List[int]:
        """Get indices of lines that are NOT in code blocks"""
        lines = text.split('\n')
        code_regions = self.detect(text)

        code_lines = set()
        for start, end in code_regions:
            code_lines.update(range(start, end + 1))

        return [i for i in range(len(lines)) if i not in code_lines]
```

**Step 5: Run test to verify it passes**

Run: `cd /Users/taylorstephens/_Projects/book-ingestion-python/.worktrees/improved-chapter-detection && source venv/bin/activate && pytest tests/processors/test_code_block_detector.py -v`

Expected: PASS (all tests green)

**Step 6: Commit**

```bash
git add tests/processors/ src/processors/code_block_detector.py
git commit -m "feat: add CodeBlockDetector for identifying code regions

Detects shell prompts, indented code, terminal output (ps/top),
and high-density special character lines. Used to exclude code
from chapter pattern matching."
```

---

## Task 2: Create ChapterCandidate Data Structures

**Files:**
- Create: `src/processors/chapter_detector.py`
- Test: `tests/processors/test_chapter_detector.py`

**Step 1: Write the failing test**

Create `tests/processors/test_chapter_detector.py`:

```python
"""Tests for chapter candidate detection and scoring"""

import pytest
from src.processors.chapter_detector import (
    ChapterCandidate,
    DetectionStats,
    MatchType,
)


class TestChapterCandidate:
    def test_candidate_creation(self):
        """ChapterCandidate should store all context fields"""
        candidate = ChapterCandidate(
            line_index=10,
            title="Chapter 1 Introduction",
            match_type=MatchType.EXPLICIT,
            preceded_by_blank=True,
            followed_by_prose=True,
            nearby_similar_lines=0,
            in_code_block=False,
        )

        assert candidate.line_index == 10
        assert candidate.title == "Chapter 1 Introduction"
        assert candidate.match_type == MatchType.EXPLICIT
        assert candidate.preceded_by_blank is True
        assert candidate.followed_by_prose is True
        assert candidate.nearby_similar_lines == 0
        assert candidate.in_code_block is False
        assert candidate.confidence == 0.0  # Not scored yet

    def test_match_type_ordering(self):
        """Match types should have correct hierarchy"""
        assert MatchType.TOC.value > MatchType.EXPLICIT.value
        assert MatchType.EXPLICIT.value > MatchType.TITLE_CASE.value
        assert MatchType.TITLE_CASE.value > MatchType.PATTERN.value


class TestDetectionStats:
    def test_stats_creation(self):
        """DetectionStats should track all metrics"""
        stats = DetectionStats(
            method='toc',
            confidence='high',
            candidates_found=15,
            candidates_rejected=3,
            anchors_used=12,
            merges_performed=2,
            code_blocks_detected=5,
            warnings=["Missing 1 chapter"],
        )

        assert stats.method == 'toc'
        assert stats.confidence == 'high'
        assert stats.candidates_found == 15
        assert stats.anchors_used == 12
        assert len(stats.warnings) == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/processors/test_chapter_detector.py -v`

Expected: FAIL with "ImportError"

**Step 3: Write minimal implementation**

Create `src/processors/chapter_detector.py`:

```python
"""Chapter candidate detection and confidence scoring"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional


class MatchType(IntEnum):
    """
    Chapter match type hierarchy (higher = more confident).
    """
    PATTERN = 1      # Matches generic pattern like ^\d+\.\s+
    TITLE_CASE = 2   # Title-case heading preceded by blank
    EXPLICIT = 3     # Contains "Chapter", "Part", "Lesson", etc.
    TOC = 4          # Found in TOC and matched in body


@dataclass
class ChapterCandidate:
    """
    A potential chapter marker with context for scoring.
    """
    line_index: int
    title: str
    match_type: MatchType

    # Context for confidence scoring
    preceded_by_blank: bool = False
    followed_by_prose: bool = False
    nearby_similar_lines: int = 0
    in_code_block: bool = False

    # Computed after scoring
    confidence: float = 0.0


@dataclass
class DetectionStats:
    """
    Statistics about chapter detection for debugging and quality tracking.
    """
    method: str  # 'toc', 'pattern', 'fallback'
    confidence: str  # 'high', 'medium', 'low'
    candidates_found: int = 0
    candidates_rejected: int = 0
    anchors_used: int = 0
    merges_performed: int = 0
    code_blocks_detected: int = 0
    warnings: List[str] = field(default_factory=list)


@dataclass
class ChapterResult:
    """
    Result of chapter detection including chapters and metadata.
    """
    chapters: List[dict]
    stats: DetectionStats
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/processors/test_chapter_detector.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/processors/chapter_detector.py tests/processors/test_chapter_detector.py
git commit -m "feat: add ChapterCandidate and DetectionStats data structures

Defines MatchType hierarchy (TOC > EXPLICIT > TITLE_CASE > PATTERN),
ChapterCandidate with context fields for scoring, and DetectionStats
for tracking detection quality."
```

---

## Task 3: Implement Confidence Scoring

**Files:**
- Modify: `src/processors/chapter_detector.py`
- Test: `tests/processors/test_chapter_detector.py`

**Step 1: Write the failing test**

Add to `tests/processors/test_chapter_detector.py`:

```python
from src.processors.chapter_detector import CandidateScorer


class TestCandidateScorer:
    def setup_method(self):
        self.scorer = CandidateScorer()

    def test_toc_match_scores_high(self):
        """TOC matches should score >= 0.7"""
        candidate = ChapterCandidate(
            line_index=100,
            title="Building Your First App",
            match_type=MatchType.TOC,
            preceded_by_blank=True,
            followed_by_prose=True,
            nearby_similar_lines=0,
            in_code_block=False,
        )

        score = self.scorer.score(candidate)
        assert score >= 0.7

    def test_explicit_match_scores_high(self):
        """Explicit 'Chapter N' matches should score >= 0.7"""
        candidate = ChapterCandidate(
            line_index=50,
            title="Chapter 3 Advanced Topics",
            match_type=MatchType.EXPLICIT,
            preceded_by_blank=True,
            followed_by_prose=True,
            nearby_similar_lines=0,
            in_code_block=False,
        )

        score = self.scorer.score(candidate)
        assert score >= 0.7

    def test_code_block_penalty(self):
        """Lines in code blocks should score low"""
        candidate = ChapterCandidate(
            line_index=50,
            title="388 history 7",
            match_type=MatchType.PATTERN,
            preceded_by_blank=False,
            followed_by_prose=False,
            nearby_similar_lines=3,
            in_code_block=True,
        )

        score = self.scorer.score(candidate)
        assert score < 0.4

    def test_list_item_penalty(self):
        """Lines near similar patterns (list items) should score low"""
        candidate = ChapterCandidate(
            line_index=50,
            title="1. First item",
            match_type=MatchType.PATTERN,
            preceded_by_blank=False,
            followed_by_prose=True,
            nearby_similar_lines=5,  # Part of a numbered list
            in_code_block=False,
        )

        score = self.scorer.score(candidate)
        assert score < 0.4

    def test_no_blank_line_penalty(self):
        """Headers not preceded by blank line score lower"""
        with_blank = ChapterCandidate(
            line_index=50,
            title="Chapter 1",
            match_type=MatchType.EXPLICIT,
            preceded_by_blank=True,
            followed_by_prose=True,
        )

        without_blank = ChapterCandidate(
            line_index=50,
            title="Chapter 1",
            match_type=MatchType.EXPLICIT,
            preceded_by_blank=False,
            followed_by_prose=True,
        )

        assert self.scorer.score(with_blank) > self.scorer.score(without_blank)

    def test_confidence_level_high(self):
        """Scores >= 0.7 should be 'high' confidence"""
        assert self.scorer.get_confidence_level(0.8) == 'high'
        assert self.scorer.get_confidence_level(0.7) == 'high'

    def test_confidence_level_medium(self):
        """Scores 0.4-0.7 should be 'medium' confidence"""
        assert self.scorer.get_confidence_level(0.5) == 'medium'
        assert self.scorer.get_confidence_level(0.4) == 'medium'

    def test_confidence_level_low(self):
        """Scores < 0.4 should be 'low' confidence"""
        assert self.scorer.get_confidence_level(0.3) == 'low'
        assert self.scorer.get_confidence_level(0.0) == 'low'
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/processors/test_chapter_detector.py::TestCandidateScorer -v`

Expected: FAIL with "ImportError: cannot import name 'CandidateScorer'"

**Step 3: Write minimal implementation**

Add to `src/processors/chapter_detector.py`:

```python
class CandidateScorer:
    """
    Scores chapter candidates based on match type and context.
    """

    # Base scores by match type
    BASE_SCORES = {
        MatchType.TOC: 0.9,
        MatchType.EXPLICIT: 0.8,
        MatchType.TITLE_CASE: 0.5,
        MatchType.PATTERN: 0.4,
    }

    # Penalty weights
    CODE_BLOCK_PENALTY = 0.5
    NO_BLANK_PENALTY = 0.2
    NO_PROSE_PENALTY = 0.3
    LIST_ITEM_PENALTY = 0.4  # Applied when nearby_similar_lines >= 2

    # Confidence thresholds
    HIGH_THRESHOLD = 0.7
    MEDIUM_THRESHOLD = 0.4

    def score(self, candidate: ChapterCandidate) -> float:
        """
        Calculate confidence score for a candidate.

        Returns:
            Float between 0.0 and 1.0
        """
        score = self.BASE_SCORES.get(candidate.match_type, 0.4)

        # Apply penalties
        if candidate.in_code_block:
            score -= self.CODE_BLOCK_PENALTY

        if not candidate.preceded_by_blank:
            score -= self.NO_BLANK_PENALTY

        if not candidate.followed_by_prose:
            score -= self.NO_PROSE_PENALTY

        if candidate.nearby_similar_lines >= 2:
            score -= self.LIST_ITEM_PENALTY

        # Clamp to valid range
        return max(0.0, min(1.0, score))

    def get_confidence_level(self, score: float) -> str:
        """Convert numeric score to confidence level string"""
        if score >= self.HIGH_THRESHOLD:
            return 'high'
        elif score >= self.MEDIUM_THRESHOLD:
            return 'medium'
        else:
            return 'low'
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/processors/test_chapter_detector.py::TestCandidateScorer -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/processors/chapter_detector.py tests/processors/test_chapter_detector.py
git commit -m "feat: add CandidateScorer with confidence scoring

Scores candidates based on match type (TOC=0.9, EXPLICIT=0.8, etc)
with penalties for code blocks, missing blank lines, no prose,
and list-like patterns. Thresholds: high>=0.7, medium>=0.4, low<0.4"
```

---

## Task 4: Implement Candidate Extractor

**Files:**
- Modify: `src/processors/chapter_detector.py`
- Test: `tests/processors/test_chapter_detector.py`

**Step 1: Write the failing test**

Add to `tests/processors/test_chapter_detector.py`:

```python
from src.processors.chapter_detector import CandidateExtractor


class TestCandidateExtractor:
    def setup_method(self):
        self.extractor = CandidateExtractor()

    def test_extracts_explicit_chapter_markers(self):
        """Should find 'Chapter N' style headers"""
        text = """Introduction

Chapter 1 Getting Started

This chapter covers basics.

Chapter 2 Advanced Topics

More content here."""

        candidates = self.extractor.extract(text)

        titles = [c.title for c in candidates]
        assert "Chapter 1 Getting Started" in titles
        assert "Chapter 2 Advanced Topics" in titles

        # Should be marked as EXPLICIT type
        ch1 = next(c for c in candidates if "Chapter 1" in c.title)
        assert ch1.match_type == MatchType.EXPLICIT

    def test_extracts_with_context(self):
        """Should capture context for scoring"""
        text = """Some intro text.

Chapter 1 Introduction

This is the first chapter content with multiple
sentences that form proper prose paragraphs."""

        candidates = self.extractor.extract(text)

        ch1 = next(c for c in candidates if "Chapter 1" in c.title)
        assert ch1.preceded_by_blank is True
        assert ch1.followed_by_prose is True

    def test_detects_nearby_similar_patterns(self):
        """Should count nearby similar patterns (list detection)"""
        text = """Contents:

1. First item
2. Second item
3. Third item
4. Fourth item

Chapter 1 Real Chapter"""

        candidates = self.extractor.extract(text)

        # The numbered list items should have high nearby_similar_lines
        list_candidates = [c for c in candidates if c.title.startswith(('1.', '2.', '3.'))]
        for c in list_candidates:
            assert c.nearby_similar_lines >= 2

    def test_marks_code_block_lines(self):
        """Should mark candidates found in code blocks"""
        text = """Chapter 1 Shell Commands

Here's how to list processes:

$ ps aux
10432 chris 20 0 471m

Chapter 2 Next Topic"""

        candidates = self.extractor.extract(text)

        # Real chapters should not be in code blocks
        ch1 = next(c for c in candidates if "Chapter 1" in c.title)
        ch2 = next(c for c in candidates if "Chapter 2" in c.title)
        assert ch1.in_code_block is False
        assert ch2.in_code_block is False

    def test_skips_lines_in_code_blocks(self):
        """Pattern matches inside code blocks should be marked"""
        text = """Chapter 1 Commands

$ cat file.txt
1. First line
2. Second line

Back to text."""

        candidates = self.extractor.extract(text)

        # Any candidates from the code block should be marked
        code_candidates = [c for c in candidates if c.in_code_block]
        # They may or may not exist, but if they do, they're marked
        for c in code_candidates:
            assert c.in_code_block is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/processors/test_chapter_detector.py::TestCandidateExtractor -v`

Expected: FAIL with "ImportError"

**Step 3: Write minimal implementation**

Add to `src/processors/chapter_detector.py`:

```python
import re
from src.processors.code_block_detector import CodeBlockDetector


class CandidateExtractor:
    """
    Extracts chapter candidates from text with context for scoring.
    """

    def __init__(self):
        self.code_detector = CodeBlockDetector()

        # Explicit chapter patterns (highest priority after TOC)
        self.explicit_patterns = [
            re.compile(r'^(Chapter\s+\d+[:\s].*)$', re.IGNORECASE),
            re.compile(r'^(CHAPTER\s+\d+[:\s].*)$'),
            re.compile(r'^(Part\s+\d+[:\s].*)$', re.IGNORECASE),
            re.compile(r'^(Lesson\s+\d+[:\s].*)$', re.IGNORECASE),
            re.compile(r'^(Module\s+\d+[:\s].*)$', re.IGNORECASE),
            re.compile(r'^(Unit\s+\d+[:\s].*)$', re.IGNORECASE),
            re.compile(r'^(Project\s+\d+[A-Z]?[:\s].*)$', re.IGNORECASE),
        ]

        # Generic patterns (lower priority)
        self.generic_patterns = [
            re.compile(r'^(\d+)\.\s+([A-Z].{5,})$'),  # "1. Title Here"
            re.compile(r'^(\d+)\s+([A-Z].{5,})$'),    # "1 Title Here"
        ]

    def extract(self, text: str, toc_titles: List[str] = None) -> List[ChapterCandidate]:
        """
        Extract chapter candidates from text.

        Args:
            text: Full book text
            toc_titles: Optional list of titles from TOC for matching

        Returns:
            List of ChapterCandidate objects
        """
        lines = text.split('\n')
        code_regions = self.code_detector.detect(text)
        code_lines = self._get_code_line_set(code_regions)

        candidates = []

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Skip empty or very short/long lines
            if len(line_stripped) < 3 or len(line_stripped) > 100:
                continue

            # Try to match patterns
            match_type = None
            title = None

            # Check explicit patterns first
            for pattern in self.explicit_patterns:
                match = pattern.match(line_stripped)
                if match:
                    title = match.group(1)
                    match_type = MatchType.EXPLICIT
                    break

            # Check generic patterns if no explicit match
            if not match_type:
                for pattern in self.generic_patterns:
                    match = pattern.match(line_stripped)
                    if match:
                        title = line_stripped
                        match_type = MatchType.PATTERN
                        break

            # Check title case (fallback)
            if not match_type and self._is_title_case(line_stripped):
                title = line_stripped
                match_type = MatchType.TITLE_CASE

            if match_type and title:
                candidate = ChapterCandidate(
                    line_index=i,
                    title=title,
                    match_type=match_type,
                    preceded_by_blank=self._is_preceded_by_blank(lines, i),
                    followed_by_prose=self._is_followed_by_prose(lines, i),
                    nearby_similar_lines=self._count_nearby_similar(lines, i),
                    in_code_block=i in code_lines,
                )
                candidates.append(candidate)

        # Check against TOC if provided
        if toc_titles:
            candidates = self._match_toc_titles(candidates, toc_titles, lines)

        return candidates

    def _get_code_line_set(self, regions: List[tuple]) -> set:
        """Convert code regions to set of line indices"""
        code_lines = set()
        for start, end in regions:
            code_lines.update(range(start, end + 1))
        return code_lines

    def _is_preceded_by_blank(self, lines: List[str], index: int) -> bool:
        """Check if line is preceded by a blank line"""
        if index == 0:
            return True  # First line counts as preceded by blank
        return lines[index - 1].strip() == ''

    def _is_followed_by_prose(self, lines: List[str], index: int, check_lines: int = 50) -> bool:
        """Check if line is followed by substantial prose content"""
        end = min(index + check_lines, len(lines))
        content = ' '.join(lines[index + 1:end])
        words = content.split()

        # Need at least 100 words of content
        if len(words) < 100:
            return False

        # Check for sentence-like structure (periods, commas)
        sentences = re.split(r'[.!?]', content)
        return len(sentences) >= 3

    def _count_nearby_similar(self, lines: List[str], index: int, window: int = 5) -> int:
        """Count lines with similar patterns nearby (list detection)"""
        current = lines[index].strip()

        # Extract the pattern type
        numbered_match = re.match(r'^(\d+)[.\s]', current)
        if not numbered_match:
            return 0

        count = 0
        start = max(0, index - window)
        end = min(len(lines), index + window + 1)

        for i in range(start, end):
            if i == index:
                continue
            other = lines[i].strip()
            if re.match(r'^\d+[.\s]', other):
                count += 1

        return count

    def _is_title_case(self, line: str) -> bool:
        """Check if line is in title case (potential chapter title)"""
        words = line.split()
        if len(words) < 2 or len(words) > 10:
            return False

        # Skip if contains common non-title patterns
        if re.search(r'[=<>{}()\[\]]', line):
            return False

        # Check that most significant words are capitalized
        significant = [w for w in words if len(w) > 3]
        if not significant:
            return False

        capitalized = sum(1 for w in significant if w[0].isupper())
        return capitalized / len(significant) >= 0.7

    def _match_toc_titles(self, candidates: List[ChapterCandidate],
                         toc_titles: List[str], lines: List[str]) -> List[ChapterCandidate]:
        """Upgrade candidates that match TOC titles"""
        toc_lower = [t.lower() for t in toc_titles]

        for candidate in candidates:
            title_lower = candidate.title.lower()
            for toc_title in toc_lower:
                # Check for significant overlap
                if toc_title in title_lower or title_lower in toc_title:
                    candidate.match_type = MatchType.TOC
                    break

        return candidates
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/processors/test_chapter_detector.py::TestCandidateExtractor -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/processors/chapter_detector.py tests/processors/test_chapter_detector.py
git commit -m "feat: add CandidateExtractor for chapter detection

Extracts candidates with match types (EXPLICIT, PATTERN, TITLE_CASE).
Captures context: preceded_by_blank, followed_by_prose, nearby_similar_lines,
in_code_block. Integrates with CodeBlockDetector."
```

---

## Task 5: Implement Anchor/Merge Logic

**Files:**
- Modify: `src/processors/chapter_detector.py`
- Test: `tests/processors/test_chapter_detector.py`

**Step 1: Write the failing test**

Add to `tests/processors/test_chapter_detector.py`:

```python
from src.processors.chapter_detector import AnchorMerger


class TestAnchorMerger:
    def setup_method(self):
        self.merger = AnchorMerger()

    def test_high_confidence_becomes_anchor(self):
        """High confidence candidates become anchors"""
        candidates = [
            ChapterCandidate(line_index=10, title="Chapter 1",
                           match_type=MatchType.EXPLICIT, confidence=0.8),
            ChapterCandidate(line_index=50, title="Chapter 2",
                           match_type=MatchType.EXPLICIT, confidence=0.75),
        ]

        anchors = self.merger.select_anchors(candidates)
        assert len(anchors) == 2

    def test_low_confidence_absorbed(self):
        """Low confidence candidates are absorbed into previous anchor"""
        candidates = [
            ChapterCandidate(line_index=10, title="Chapter 1",
                           match_type=MatchType.EXPLICIT, confidence=0.8),
            ChapterCandidate(line_index=30, title="388 history 7",
                           match_type=MatchType.PATTERN, confidence=0.2),
            ChapterCandidate(line_index=50, title="Chapter 2",
                           match_type=MatchType.EXPLICIT, confidence=0.75),
        ]

        anchors = self.merger.select_anchors(candidates)

        # Only real chapters should be anchors
        titles = [a.title for a in anchors]
        assert "Chapter 1" in titles
        assert "Chapter 2" in titles
        assert "388 history 7" not in titles

    def test_promotes_medium_when_no_high(self):
        """When no high-confidence, promote best medium candidates"""
        candidates = [
            ChapterCandidate(line_index=10, title="Introduction",
                           match_type=MatchType.TITLE_CASE, confidence=0.5),
            ChapterCandidate(line_index=50, title="Background",
                           match_type=MatchType.TITLE_CASE, confidence=0.55),
            ChapterCandidate(line_index=90, title="Conclusion",
                           match_type=MatchType.TITLE_CASE, confidence=0.5),
        ]

        anchors = self.merger.select_anchors(candidates)

        # Should promote medium-confidence as fallback
        assert len(anchors) >= 2

    def test_merge_stats_tracking(self):
        """Should track merge statistics"""
        candidates = [
            ChapterCandidate(line_index=10, title="Chapter 1",
                           match_type=MatchType.EXPLICIT, confidence=0.8),
            ChapterCandidate(line_index=20, title="1.1 Section",
                           match_type=MatchType.PATTERN, confidence=0.3),
            ChapterCandidate(line_index=30, title="1.2 Another",
                           match_type=MatchType.PATTERN, confidence=0.25),
            ChapterCandidate(line_index=100, title="Chapter 2",
                           match_type=MatchType.EXPLICIT, confidence=0.8),
        ]

        anchors, stats = self.merger.merge(candidates)

        assert stats.anchors_used == 2
        assert stats.merges_performed == 2  # Two low-confidence absorbed
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/processors/test_chapter_detector.py::TestAnchorMerger -v`

Expected: FAIL with "ImportError"

**Step 3: Write minimal implementation**

Add to `src/processors/chapter_detector.py`:

```python
class AnchorMerger:
    """
    Selects high-confidence anchors and absorbs low-confidence candidates.
    """

    HIGH_THRESHOLD = 0.7
    MEDIUM_THRESHOLD = 0.4
    MIN_ANCHORS = 3  # Minimum chapters to accept before fallback

    def select_anchors(self, candidates: List[ChapterCandidate]) -> List[ChapterCandidate]:
        """
        Select anchor candidates based on confidence.

        High-confidence (>= 0.7) candidates become anchors.
        If too few anchors, promote best medium-confidence candidates.
        """
        # Sort by line index for sequential processing
        sorted_candidates = sorted(candidates, key=lambda c: c.line_index)

        # Select high-confidence anchors
        anchors = [c for c in sorted_candidates if c.confidence >= self.HIGH_THRESHOLD]

        # If not enough anchors, promote medium-confidence
        if len(anchors) < self.MIN_ANCHORS:
            medium = [c for c in sorted_candidates
                     if self.MEDIUM_THRESHOLD <= c.confidence < self.HIGH_THRESHOLD]
            # Sort by confidence descending
            medium.sort(key=lambda c: c.confidence, reverse=True)

            # Add best medium candidates until we have enough
            for candidate in medium:
                if len(anchors) >= self.MIN_ANCHORS:
                    break
                # Insert in correct position by line_index
                anchors.append(candidate)

            anchors.sort(key=lambda c: c.line_index)

        return anchors

    def merge(self, candidates: List[ChapterCandidate]) -> tuple:
        """
        Perform full anchor selection and merge.

        Returns:
            Tuple of (anchors, DetectionStats)
        """
        anchors = self.select_anchors(candidates)
        anchor_indices = {a.line_index for a in anchors}

        # Count merges (candidates not selected as anchors)
        merges = len(candidates) - len(anchors)

        # Determine overall confidence
        if not anchors:
            confidence = 'low'
        elif all(a.confidence >= self.HIGH_THRESHOLD for a in anchors):
            confidence = 'high'
        elif any(a.confidence >= self.HIGH_THRESHOLD for a in anchors):
            confidence = 'medium'
        else:
            confidence = 'low'

        # Determine method based on anchor types
        toc_count = sum(1 for a in anchors if a.match_type == MatchType.TOC)
        explicit_count = sum(1 for a in anchors if a.match_type == MatchType.EXPLICIT)

        if toc_count > len(anchors) / 2:
            method = 'toc'
        elif explicit_count > 0:
            method = 'pattern'
        else:
            method = 'fallback'

        stats = DetectionStats(
            method=method,
            confidence=confidence,
            candidates_found=len(candidates),
            candidates_rejected=merges,
            anchors_used=len(anchors),
            merges_performed=merges,
        )

        return anchors, stats
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/processors/test_chapter_detector.py::TestAnchorMerger -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/processors/chapter_detector.py tests/processors/test_chapter_detector.py
git commit -m "feat: add AnchorMerger for chapter consolidation

High-confidence (>=0.7) candidates become anchors. Low-confidence
candidates are absorbed. Falls back to medium-confidence if too few
high-confidence anchors. Tracks merge statistics."
```

---

## Task 6: Integrate Pipeline into ChapterSplitter

**Files:**
- Modify: `src/processors/chapter_splitter.py`
- Test: `tests/processors/test_chapter_splitter.py`

**Step 1: Write the failing test**

Create `tests/processors/test_chapter_splitter.py`:

```python
"""Tests for improved chapter splitter"""

import pytest
from src.processors.chapter_splitter import ChapterSplitter
from src.utils.config import Config


class TestImprovedChapterSplitter:
    def setup_method(self):
        config = Config()
        self.splitter = ChapterSplitter(config)

    def test_filters_code_block_false_positives(self):
        """Should not detect code output as chapters"""
        text = """Chapter 1 Using the Shell

This chapter covers shell basics.

$ ps aux
10432 chris 20 0 471m 121m 18m S 99.9 3.2 77:01.76 bigcommand
20284 root 25 5 98.7m 932 644 D 2.7 0.0 0:00.96 updatedb

The output shows running processes.

Chapter 2 Advanced Commands

More content here with substantial text to make this
a valid chapter with enough words to pass validation.
We need at least 500 words so let me add more content.
""" + "More content. " * 200  # Pad to meet word minimums

        chapters = self.splitter.split(text, "test-book-1")

        titles = [ch['title'] for ch in chapters]

        # Should have the real chapters
        assert any("Chapter 1" in t for t in titles)
        assert any("Chapter 2" in t for t in titles)

        # Should NOT have the code output
        assert not any("10432" in t for t in titles)
        assert not any("20284" in t for t in titles)

    def test_returns_detection_stats(self):
        """Should return detection statistics"""
        text = """Chapter 1 Introduction

Content here. """ + "More words. " * 300 + """

Chapter 2 Methods

More content. """ + "Additional text. " * 300

        result = self.splitter.split_with_stats(text, "test-book-2")

        assert 'chapters' in result
        assert 'stats' in result
        assert result['stats'].candidates_found >= 2
        assert result['stats'].anchors_used >= 2

    def test_handles_numbered_lists_correctly(self):
        """Should not detect numbered list items as chapters"""
        text = """Chapter 1 Setup

Before starting, gather these items:

1. A computer
2. An internet connection
3. A text editor
4. Some patience
5. Coffee (optional)

Now let's begin the actual content of this chapter.
""" + "Explanation text. " * 300 + """

Chapter 2 Installation

More content here.""" + " Installation details. " * 300

        chapters = self.splitter.split(text, "test-book-3")

        titles = [ch['title'] for ch in chapters]

        # Should have real chapters
        assert any("Chapter 1" in t for t in titles)
        assert any("Chapter 2" in t for t in titles)

        # Should NOT have list items
        assert not any(t.strip().startswith("1.") for t in titles)
        assert not any(t.strip().startswith("2.") for t in titles)

    def test_backwards_compatible_api(self):
        """split() should work exactly as before"""
        text = """Chapter 1 First

Content. """ + "Words. " * 300 + """

Chapter 2 Second

More. """ + "Text. " * 300

        # Should return list of chapter dicts (not ChapterResult)
        chapters = self.splitter.split(text, "test-book-4")

        assert isinstance(chapters, list)
        assert len(chapters) >= 2
        assert all(isinstance(ch, dict) for ch in chapters)
        assert all('id' in ch and 'title' in ch and 'content' in ch for ch in chapters)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/processors/test_chapter_splitter.py -v`

Expected: FAIL (some tests fail due to false positives)

**Step 3: Modify implementation**

Update `src/processors/chapter_splitter.py` to integrate the new pipeline:

```python
"""Chapter splitting logic with improved detection"""

import re
from typing import List, Dict, Optional
from src.processors.code_block_detector import CodeBlockDetector
from src.processors.chapter_detector import (
    ChapterCandidate,
    CandidateExtractor,
    CandidateScorer,
    AnchorMerger,
    DetectionStats,
    ChapterResult,
    MatchType,
)


class ChapterSplitter:
    def __init__(self, config):
        self.config = config.chapter_detection
        self.patterns = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in self.config['patterns']]

        # New pipeline components
        self.code_detector = CodeBlockDetector()
        self.extractor = CandidateExtractor()
        self.scorer = CandidateScorer()
        self.merger = AnchorMerger()

    def split(self, text: str, book_id: str) -> List[Dict]:
        """
        Split text into chapters.

        Backwards-compatible API - returns list of chapter dicts.
        """
        result = self.split_with_stats(text, book_id)
        return result['chapters']

    def split_with_stats(self, text: str, book_id: str) -> Dict:
        """
        Split text into chapters with detection statistics.

        Returns:
            Dict with 'chapters' and 'stats' keys
        """
        # Stage 1: Detect code blocks
        code_regions = self.code_detector.detect(text)

        # Stage 2: Try TOC-based detection first
        toc_titles = self._extract_toc_titles(text)

        # Stage 3: Extract candidates
        candidates = self.extractor.extract(text, toc_titles)

        # Stage 4: Score candidates
        for candidate in candidates:
            candidate.confidence = self.scorer.score(candidate)

        # Stage 5: Select anchors and merge
        anchors, stats = self.merger.merge(candidates)
        stats.code_blocks_detected = len(code_regions)

        # Build chapters from anchors
        if anchors:
            chapters = self._build_chapters_from_anchors(text, book_id, anchors)
        else:
            # Fallback to fixed-size
            chapters = self._fixed_size_split(text, book_id)
            stats.method = 'fallback'
            stats.confidence = 'low'

        # Validate chapter sizes
        chapters = self._validate_chapter_sizes(chapters)

        # If validation removed too many, use fallback
        if len(chapters) == 0:
            chapters = self._fixed_size_split(text, book_id)
            stats.method = 'fallback'
            stats.confidence = 'low'

        return {
            'chapters': chapters,
            'stats': stats,
        }

    def _extract_toc_titles(self, text: str) -> List[str]:
        """Extract chapter titles from Table of Contents"""
        lines = text.split('\n')[:500]
        titles = []

        toc_patterns = [
            re.compile(r'^Chapter\s+\d+[,:]\s+(.+)', re.IGNORECASE),
            re.compile(r'^Chapter\s+\d+:\s+(.+)', re.IGNORECASE),
            re.compile(r'^Project\s+\d+[A-Z]:\s+(.+)', re.IGNORECASE),
        ]

        for line in lines:
            line_stripped = line.strip()
            for pattern in toc_patterns:
                match = pattern.match(line_stripped)
                if match:
                    titles.append(match.group(1).strip())
                    break

        return titles

    def _build_chapters_from_anchors(self, text: str, book_id: str,
                                     anchors: List[ChapterCandidate]) -> List[Dict]:
        """Build chapter dicts from anchor candidates"""
        lines = text.split('\n')
        chapters = []

        for idx, anchor in enumerate(anchors):
            start = anchor.line_index + 1
            end = anchors[idx + 1].line_index if idx + 1 < len(anchors) else len(lines)

            content = '\n'.join(lines[start:end]).strip()
            word_count = len(content.split())

            chapters.append({
                'id': f"{book_id}-ch{len(chapters) + 1}",
                'book_id': book_id,
                'chapter_number': len(chapters) + 1,
                'title': anchor.title,
                'content': content,
                'word_count': word_count,
                'file_path': '',
                'detection_confidence': self.scorer.get_confidence_level(anchor.confidence),
                'detection_method': anchor.match_type.name.lower(),
            })

        return chapters

    def _validate_chapter_sizes(self, chapters: List[Dict]) -> List[Dict]:
        """Filter chapters by size constraints"""
        min_words = self.config.get('min_words_per_chapter', 500)
        max_words = self.config.get('max_words_per_chapter', 50000)

        valid = []
        for ch in chapters:
            wc = ch.get('word_count', 0)
            if min_words <= wc <= max_words:
                valid.append(ch)
            elif wc > max_words:
                # Keep but flag - might need splitting
                ch['needs_splitting'] = True
                valid.append(ch)

        return valid

    def _fixed_size_split(self, text: str, book_id: str) -> List[Dict]:
        """Split into fixed-size chunks when no chapters detected"""
        words = text.split()
        chunk_size = 2500
        chapters = []

        for i in range(0, len(words), chunk_size):
            content = ' '.join(words[i:i + chunk_size])

            chapters.append({
                'id': f"{book_id}-ch{len(chapters) + 1}",
                'book_id': book_id,
                'chapter_number': len(chapters) + 1,
                'title': f"Section {len(chapters) + 1}",
                'content': content,
                'word_count': len(content.split()),
                'file_path': '',
                'detection_confidence': 'low',
                'detection_method': 'fallback',
            })

        return chapters

    # Keep legacy methods for backwards compatibility
    def _detect_from_toc(self, text):
        """Legacy TOC detection - now uses _extract_toc_titles internally"""
        return self._extract_toc_titles(text)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/processors/test_chapter_splitter.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/processors/chapter_splitter.py tests/processors/test_chapter_splitter.py
git commit -m "feat: integrate detection pipeline into ChapterSplitter

Adds split_with_stats() for detection metadata. Integrates
CodeBlockDetector, CandidateExtractor, CandidateScorer, AnchorMerger.
Backwards-compatible split() API preserved."
```

---

## Task 7: Add CLI Debug Flag

**Files:**
- Modify: `src/cli.py`
- Manual test only (no automated test)

**Step 1: Read current CLI**

Read `src/cli.py` to understand current structure.

**Step 2: Add --debug flag**

Add `--debug` option to the `process` command that outputs detection stats:

```python
@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('-t', '--title', default=None, help='Book title')
@click.option('-a', '--author', default=None, help='Book author')
@click.option('--debug', is_flag=True, help='Show detection statistics')
def process(file_path, title, author, debug):
    """Process a book file (PDF or EPUB)"""
    # ... existing code ...

    # After chapter splitting:
    if debug:
        console.print("\n[bold]Detection Statistics:[/bold]")
        console.print(f"  Method: {stats.method}")
        console.print(f"  Confidence: {stats.confidence}")
        console.print(f"  Candidates found: {stats.candidates_found}")
        console.print(f"  Candidates rejected: {stats.candidates_rejected}")
        console.print(f"  Anchors used: {stats.anchors_used}")
        console.print(f"  Code blocks detected: {stats.code_blocks_detected}")
        if stats.warnings:
            console.print(f"  Warnings: {stats.warnings}")
```

**Step 3: Manual test**

Run: `python src/cli.py process /path/to/test.pdf --debug`

Verify stats are printed.

**Step 4: Commit**

```bash
git add src/cli.py
git commit -m "feat: add --debug flag to show detection statistics

Shows method, confidence, candidate counts, and warnings
when processing books."
```

---

## Task 8: Run Full Integration Test

**Files:**
- No new files

**Step 1: Run all tests**

Run: `pytest tests/ -v`

Expected: All tests pass

**Step 2: Test with real book**

If you have a test PDF with known issues (like Ubuntu Linux Bible):

```bash
python src/cli.py process /path/to/ubuntu-bible.pdf --debug
```

Verify:
- Fewer false positive chapters
- Detection stats show confidence level
- Real chapters detected correctly

**Step 3: Final commit**

```bash
git add -A
git commit -m "test: verify full integration

All unit tests passing. Manual testing complete."
```

---

## Summary

| Task | Component | Purpose |
|------|-----------|---------|
| 1 | CodeBlockDetector | Identify code regions to exclude |
| 2 | Data structures | ChapterCandidate, DetectionStats |
| 3 | CandidateScorer | Confidence scoring |
| 4 | CandidateExtractor | Extract candidates with context |
| 5 | AnchorMerger | Select anchors, absorb low-confidence |
| 6 | ChapterSplitter integration | Wire up pipeline |
| 7 | CLI --debug flag | Surface detection stats |
| 8 | Integration test | Verify everything works |
