---
status: active
tags: [project/book-ingestion-python, format/plan]
type: note
created: '2025-12-22'
modified: '2025-12-22'
---

# Improved Chapter Detection Design

## Problem

Current chapter detection has two failure modes:

1. **Over-splitting**: False positives from code blocks/terminal output matching patterns (e.g., "388 history 7" matching `^\d+\.\s+`)
2. **Under-splitting**: Falling back to generic "Section N" chunks when pattern detection fails

## Solution

Replace single-pass detection with a multi-stage pipeline:

```
Text → Code Block Detection → Candidate Extraction → Confidence Scoring → Anchor/Merge → Validation
```

Each stage filters or enriches, with final output being chapters tagged with `detection_confidence` and `detection_method`.

---

## Stage 1: Code Block Detection

Before pattern matching, identify and mark code/terminal output regions:

```python
class CodeBlockDetector:
    def detect(self, text: str) -> List[Tuple[int, int]]:
        """Returns list of (start_line, end_line) for code regions"""
        # Indicators:
        # - Multiple pipes, arrows, brackets
        # - Lines starting with $, #, >
        # - Consistent indentation blocks
        # - High density of special characters
        # - Numeric columns (like ps/top output)
```

Lines within code blocks are excluded from chapter pattern matching.

---

## Stage 2: Candidate Extraction with Context

Extract potential chapter markers with context for scoring:

```python
@dataclass
class ChapterCandidate:
    line_index: int
    title: str
    match_type: str  # 'toc', 'explicit', 'pattern', 'title_case'

    # Context for scoring
    preceded_by_blank: bool
    followed_by_prose: bool  # Next 50 lines have paragraph-like content
    nearby_similar_lines: int  # Count of similar patterns within ±5 lines
    in_code_block: bool
```

**Match type hierarchy** (highest to lowest confidence):

1. **toc** - Title found in TOC and matched in body
2. **explicit** - Contains "Chapter", "CHAPTER", "Part", "Lesson", etc.
3. **pattern** - Matches config patterns like `^\d+\.\s+`
4. **title_case** - Title-case heading preceded by blank line

---

## Stage 3: Confidence Scoring

Score each candidate based on multiple signals:

```python
def score_candidate(self, candidate: ChapterCandidate, text_stats: dict) -> float:
    score = 0.0

    # Match type base scores
    scores_by_type = {'toc': 0.9, 'explicit': 0.8, 'pattern': 0.4, 'title_case': 0.5}
    score = scores_by_type[candidate.match_type]

    # Modifiers
    if candidate.in_code_block: score -= 0.5
    if not candidate.preceded_by_blank: score -= 0.2
    if not candidate.followed_by_prose: score -= 0.3
    if candidate.nearby_similar_lines >= 2: score -= 0.4  # Likely a list

    return max(0.0, min(1.0, score))
```

**Confidence thresholds**:

- `>= 0.7` → **high** (anchor chapter)
- `0.4 - 0.7` → **medium** (keep if no better option)
- `< 0.4` → **low** (merge into previous anchor or discard)

---

## Stage 4: Anchor/Merge

High-confidence candidates become "anchors" that absorb low-confidence matches:

```python
def merge_with_anchors(self, candidates: List[ChapterCandidate]) -> List[Chapter]:
    anchors = [c for c in candidates if c.confidence >= 0.7]

    # If no anchors found, promote best medium-confidence candidates
    if not anchors:
        anchors = self._select_best_candidates(candidates, min_confidence=0.4)

    # Absorb low-confidence candidates into preceding anchor
    # Content between anchors becomes part of that chapter
```

Example: "CHAPTER 3 Using the Shell" is an anchor. "388 history 7" (low confidence) gets absorbed into Chapter 3's content.

---

## Stage 5: Validation & Diagnostics

Integrate with existing `ChapterValidator`, adding detection metadata:

```python
@dataclass
class ChapterResult:
    chapters: List[Chapter]
    detection_stats: DetectionStats

@dataclass
class DetectionStats:
    method: str  # 'toc', 'pattern', 'fallback'
    confidence: str  # 'high', 'medium', 'low'
    candidates_found: int
    candidates_rejected: int
    anchors_used: int
    merges_performed: int
    code_blocks_detected: int
    warnings: List[str]
```

This metadata:

1. Gets stored with the book for downstream filtering
2. Enables debugging ("why did this book get 63 chapters?")
3. Provides data to improve detection patterns over time

---

## File Structure

```
src/processors/
├── chapter_splitter.py      # Refactor: orchestrates pipeline
├── chapter_detector.py      # NEW: candidate extraction + scoring
├── code_block_detector.py   # NEW: identifies code regions
├── chapter_validator.py     # Existing: final validation
└── section_splitter.py      # Existing: splits large chapters
```

---

## Migration

- Existing API (`ChapterSplitter.split()`) remains unchanged
- New detection logic is internal refactoring
- Add optional `--debug` flag to CLI to output `DetectionStats`
- No database schema changes required (metadata stored in chapter files)

---

## Success Criteria

1. Ubuntu Linux Bible: Reduces from 63 chapters to ~24 real chapters
2. Books currently falling back to "Section N" get meaningful chapter titles
3. All chapters have `detection_confidence` metadata
4. `--debug` flag shows detection statistics
