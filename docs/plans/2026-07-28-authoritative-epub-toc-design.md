# Authoritative EPUB TOC Design

## Problem

The enhanced EPUB parser resolves publisher-provided TOC entries to exact text
positions. For a structured travel guide, those anchors correctly identify the
major guide chapters. Candidate extraction currently mixes those structural
anchors with heuristic title-case and pattern candidates, however. The anchor
merger then promotes heuristics to satisfy a word-count-derived target. In the
audited guide this creates a false chapter named after another regional imprint.

The same audit found `books.word_count = 0` even though the saved chapters have
valid word counts. An existing regression reproduces this. A later cleanup
commit removed the chapter-sum rollup while claiming a migration handled it,
but the storage path still inserts the unmodified metadata value.

## Approaches Considered

### 1. Special-case travel guides

Pass `book_type=travel_guide` into the ingestion library and use a dedicated
detector. This would couple generic EPUB extraction to the caller's classifier
and leave other richly structured EPUBs exposed to the same false positives.

### 2. Raise heuristic thresholds

Require stronger scores or wider spacing before supplementing EPUB anchors.
This reduces some false positives but still treats heuristic density as more
authoritative than publisher structure. Results would remain sensitive to book
length and typography.

### 3. Treat a complete resolved EPUB TOC as authoritative

When at least three chapter-level EPUB anchors resolve, return only those
structural candidates. If fewer than three resolve, retain the existing mixed
heuristic path so sparse or damaged EPUB metadata can recover.

This is the selected approach. It is format-driven rather than title- or
book-type-specific, preserves the existing fallback for weak metadata, and
changes only the candidate-selection boundary where the structural information
is otherwise diluted.

## Data Flow

1. The enhanced EPUB parser builds split points and resolves chapter anchors.
2. `CandidateExtractor` creates `EPUB_ANCHOR` candidates.
3. If three or more resolve, they become the full candidate set.
4. Otherwise, the extractor continues combining resolved anchors with
   non-overlapping heuristics.
5. Existing scoring, chapter construction, size validation, and oversized
   chapter splitting continue unchanged.
6. Before storage, `BookIngestionApp` rolls up chapter word counts into book
   metadata, which becomes the authoritative book-level count.

## Error Handling and Safety

The reliability threshold prevents one or two accidentally resolved anchors
from suppressing recovery heuristics. No source-specific strings, file names,
or classifier types are introduced. Forced fallback behavior remains unchanged.
The live book will be reingested without `force_fallback`, left pending under
supervised autonomy, and audited before any approval.

## Testing

- Add a synthetic guide test with three resolved publisher anchors and a
  title-case back-matter heading. It must initially show that the heuristic
  heading leaks into the candidate set, then pass with only EPUB anchors.
- Keep the existing one-anchor fingerprint tests to cover the sparse-anchor
  fallback path.
- Re-run the existing word-count regression before and after restoring the
  rollup.
- Run the focused chapter/EPUB/storage suites and the full suite, explicitly
  reporting the pre-existing semantic-model test if its environment-dependent
  behavior remains.
- Dry-run the real EPUB with storage disabled, then audit the live reingestion.
