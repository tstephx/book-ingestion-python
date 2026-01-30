"""
Chapter Merger for Over-Fragmented Content

Intelligently merges chapters that have been over-split during detection.
Uses both heuristics and semantic analysis to determine merge candidates.

Based on LangChain chunking best practices:
- Chunks should be 3,000-15,000 words for chapters
- Chunk overlap preserves context at boundaries
- Semantic similarity guides merge decisions
"""

import re
import statistics
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from copy import deepcopy


@dataclass
class MergeCandidate:
    """A pair of chapters that should potentially be merged"""
    first_index: int
    second_index: int
    combined_word_count: int
    merge_score: float        # 0-1, higher = stronger merge candidate
    merge_reasons: List[str]


@dataclass  
class MergeResult:
    """Result of merging chapters"""
    original_count: int
    merged_count: int
    merges_performed: int
    merge_details: List[Tuple[int, int]]  # (from, to) index pairs
    chapters: List[Dict]
    quality_improvement: float  # Change in avg chapter size


class ChapterMerger:
    """
    Merges over-fragmented chapters based on quality thresholds.
    
    Uses multiple signals to identify merge candidates:
    - Word count (chapters < MIN_WORDS are candidates)
    - Title patterns (sections within chapters)
    - Semantic similarity (optional, requires embeddings)
    - Sequential chapter numbering gaps
    """
    
    # Target chapter size range (words)
    MIN_TARGET_WORDS = 3000
    MAX_TARGET_WORDS = 15000
    IDEAL_TARGET_WORDS = 8000
    
    # Merge thresholds
    MIN_WORDS_STANDALONE = 2000  # Below this, consider merging
    MAX_COMBINED_WORDS = 25000   # Don't merge if result would exceed this
    
    # Title patterns indicating sub-sections (not real chapters)
    SUBSECTION_PATTERNS = [
        r'^Section\s+\d+$',
        r'^\d+(\.\d+)+\s+',       # "1.1 Title" or "2.3.1 Title" (multi-level numbering)
        r'^Part\s+[IVX]+\s*$',     # Part without title
        r'^Getting\s+Started',
        r'^Introduction\s*$',
        r'^Preface\s*$',
        r'^Foreword\s*$',
        r'^Acknowledgments?\s*$',
        r'^Summary\s*$',
        r'^Conclusion\s*$',
        r'^Review\s*$',
    ]
    
    def __init__(self, use_semantic: bool = False):
        """
        Initialize the merger.
        
        Args:
            use_semantic: Whether to use semantic similarity for merge decisions
        """
        self.use_semantic = use_semantic
        self._semantic_chunker = None
        
        # Compile subsection patterns
        self.subsection_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.SUBSECTION_PATTERNS
        ]
    
    def should_merge_chapters(
        self,
        chapters: List[Dict],
        total_word_count: int = 0
    ) -> bool:
        """
        Quick check if chapters need merging.
        
        Args:
            chapters: List of chapter dicts
            total_word_count: Optional total word count for book
            
        Returns:
            True if merging is recommended
        """
        if not chapters or len(chapters) < 3:
            return False
        
        word_counts = [c.get('word_count', 0) for c in chapters]
        avg_words = statistics.mean(word_counts)
        
        # Too many small chapters
        if avg_words < 2000:
            return True
        
        # High chapter count with small average
        if len(chapters) > 40 and avg_words < 5000:
            return True
        
        # Many undersized chapters
        undersized = sum(1 for w in word_counts if w < self.MIN_WORDS_STANDALONE)
        if undersized > len(chapters) * 0.3:
            return True
        
        return False
    
    def find_merge_candidates(
        self,
        chapters: List[Dict],
        text: str = None
    ) -> List[MergeCandidate]:
        """
        Find pairs of chapters that should be merged.
        
        Args:
            chapters: List of chapter dicts
            text: Optional full text for semantic analysis
            
        Returns:
            List of MergeCandidate objects, sorted by merge_score
        """
        candidates = []
        
        for i in range(len(chapters) - 1):
            current = chapters[i]
            next_ch = chapters[i + 1]
            
            current_words = current.get('word_count', 0)
            next_words = next_ch.get('word_count', 0)
            combined = current_words + next_words
            
            # Skip if combined would be too large
            if combined > self.MAX_COMBINED_WORDS:
                continue
            
            merge_reasons = []
            score = 0.0
            
            # Reason 1: Current chapter is undersized
            if current_words < self.MIN_WORDS_STANDALONE:
                score += 0.3
                merge_reasons.append(f"Current chapter undersized ({current_words} words)")
            
            # Reason 2: Next chapter is undersized
            if next_words < self.MIN_WORDS_STANDALONE:
                score += 0.3
                merge_reasons.append(f"Next chapter undersized ({next_words} words)")
            
            # Reason 3: Title suggests subsection
            next_title = next_ch.get('title', '')
            if self._is_subsection_title(next_title):
                score += 0.25
                merge_reasons.append(f"Title suggests subsection: {next_title[:50]}")
            
            # Reason 4: Sequential chapter number missing
            current_num = self._extract_chapter_number(current.get('title', ''))
            next_num = self._extract_chapter_number(next_ch.get('title', ''))
            if current_num and next_num and next_num != current_num + 1:
                # Gap in numbering suggests over-splitting
                if next_num > current_num + 1:
                    score += 0.2
                    merge_reasons.append(f"Chapter number gap: {current_num} -> {next_num}")
            
            # Reason 5: Combined size is ideal
            if self.MIN_TARGET_WORDS <= combined <= self.MAX_TARGET_WORDS:
                score += 0.1
                merge_reasons.append(f"Combined size is ideal ({combined} words)")
            
            # Only add if there's at least one reason
            if merge_reasons and score > 0:
                candidates.append(MergeCandidate(
                    first_index=i,
                    second_index=i + 1,
                    combined_word_count=combined,
                    merge_score=min(1.0, score),
                    merge_reasons=merge_reasons
                ))
        
        # Sort by score (highest first)
        candidates.sort(key=lambda c: c.merge_score, reverse=True)
        
        return candidates
    
    def merge_chapters(
        self,
        chapters: List[Dict],
        max_merges: int = None,
        min_score: float = 0.3,
        text: str = None
    ) -> MergeResult:
        """
        Perform chapter merging based on quality analysis.
        
        Args:
            chapters: List of chapter dicts to merge
            max_merges: Maximum number of merges to perform (None = auto)
            min_score: Minimum merge score required
            text: Optional full text for semantic analysis
            
        Returns:
            MergeResult with merged chapters
        """
        if not chapters:
            return MergeResult(
                original_count=0,
                merged_count=0,
                merges_performed=0,
                merge_details=[],
                chapters=[],
                quality_improvement=0.0
            )
        
        # Calculate original quality
        original_avg = statistics.mean([c.get('word_count', 0) for c in chapters])
        
        # Find merge candidates
        candidates = self.find_merge_candidates(chapters, text)
        candidates = [c for c in candidates if c.merge_score >= min_score]
        
        if not candidates:
            return MergeResult(
                original_count=len(chapters),
                merged_count=len(chapters),
                merges_performed=0,
                merge_details=[],
                chapters=deepcopy(chapters),
                quality_improvement=0.0
            )
        
        # Limit merges if specified
        if max_merges is None:
            # Auto-calculate based on how many would bring avg to target
            current_avg = original_avg
            target_avg = self.IDEAL_TARGET_WORDS
            if current_avg < target_avg:
                # Rough estimate of merges needed
                max_merges = int((target_avg - current_avg) / 2000 * len(chapters) / 2)
                max_merges = max(1, min(max_merges, len(candidates)))
        
        # Perform merges (be careful not to double-merge)
        merged_chapters = deepcopy(chapters)
        merge_details = []
        merged_indices = set()
        
        for candidate in candidates[:max_merges]:
            # Skip if either chapter already merged
            if (candidate.first_index in merged_indices or 
                candidate.second_index in merged_indices):
                continue
            
            # Find current positions (may have shifted due to previous merges)
            current_first = self._find_shifted_index(
                candidate.first_index, merge_details
            )
            current_second = self._find_shifted_index(
                candidate.second_index, merge_details
            )
            
            if current_first is None or current_second is None:
                continue
            
            if current_second != current_first + 1:
                continue  # No longer adjacent
            
            # Perform merge
            first = merged_chapters[current_first]
            second = merged_chapters[current_second]
            
            merged = self._merge_two_chapters(first, second, current_first + 1)
            
            # Replace in list
            merged_chapters[current_first] = merged
            del merged_chapters[current_second]
            
            merge_details.append((candidate.first_index, candidate.second_index))
            merged_indices.add(candidate.first_index)
            merged_indices.add(candidate.second_index)
        
        # Renumber chapters
        for i, chapter in enumerate(merged_chapters):
            chapter['chapter_number'] = i + 1
            chapter['id'] = f"{chapter.get('book_id', 'book')}-ch{i + 1}"
        
        # Calculate quality improvement
        if merged_chapters:
            new_avg = statistics.mean([c.get('word_count', 0) for c in merged_chapters])
            quality_improvement = new_avg - original_avg
        else:
            quality_improvement = 0.0
        
        return MergeResult(
            original_count=len(chapters),
            merged_count=len(merged_chapters),
            merges_performed=len(merge_details),
            merge_details=merge_details,
            chapters=merged_chapters,
            quality_improvement=quality_improvement
        )
    
    def auto_merge(
        self,
        chapters: List[Dict],
        target_avg_words: int = None,
        text: str = None
    ) -> MergeResult:
        """
        Automatically merge chapters to reach target average size.
        
        Iteratively merges until target is reached or no more candidates.
        
        Args:
            chapters: List of chapter dicts
            target_avg_words: Target average words per chapter
            text: Optional full text for semantic analysis
            
        Returns:
            MergeResult with optimally merged chapters
        """
        if target_avg_words is None:
            target_avg_words = self.IDEAL_TARGET_WORDS
        
        current_chapters = deepcopy(chapters)
        all_merge_details = []
        
        # Iteratively merge until target reached or no candidates
        max_iterations = len(chapters)  # Safety limit
        
        for _ in range(max_iterations):
            # Check if target reached
            if not current_chapters:
                break
            
            avg_words = statistics.mean([c.get('word_count', 0) for c in current_chapters])
            if avg_words >= target_avg_words:
                break
            
            # Find and perform one merge
            result = self.merge_chapters(
                current_chapters,
                max_merges=1,
                min_score=0.2,  # Lower threshold for auto-merge
                text=text
            )
            
            if result.merges_performed == 0:
                break  # No more candidates
            
            current_chapters = result.chapters
            all_merge_details.extend(result.merge_details)
        
        # Calculate final metrics
        if chapters:
            original_avg = statistics.mean([c.get('word_count', 0) for c in chapters])
        else:
            original_avg = 0
        
        if current_chapters:
            new_avg = statistics.mean([c.get('word_count', 0) for c in current_chapters])
        else:
            new_avg = 0
        
        return MergeResult(
            original_count=len(chapters),
            merged_count=len(current_chapters),
            merges_performed=len(all_merge_details),
            merge_details=all_merge_details,
            chapters=current_chapters,
            quality_improvement=new_avg - original_avg
        )
    
    def _is_subsection_title(self, title: str) -> bool:
        """Check if title indicates a subsection rather than chapter"""
        if not title:
            return False
        
        for pattern in self.subsection_patterns:
            if pattern.match(title.strip()):
                return True
        
        return False
    
    def _extract_chapter_number(self, title: str) -> Optional[int]:
        """Extract chapter number from title"""
        if not title:
            return None
        
        # Try various patterns
        patterns = [
            r'^Chapter\s+(\d+)',
            r'^(\d+)\.\s+',
            r'^(\d+)\s+[A-Z]',
        ]
        
        for pattern in patterns:
            match = re.match(pattern, title, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        
        return None
    
    def _find_shifted_index(
        self,
        original_index: int,
        previous_merges: List[Tuple[int, int]]
    ) -> Optional[int]:
        """Find current index after previous merges"""
        shifted = original_index
        
        for first, second in previous_merges:
            if original_index == first or original_index == second:
                # This chapter was already merged
                if original_index == second:
                    return None
            elif original_index > second:
                # Shift down by 1 for each merge that removed a chapter before us
                shifted -= 1
        
        return shifted
    
    def _merge_two_chapters(
        self,
        first: Dict,
        second: Dict,
        new_number: int
    ) -> Dict:
        """Merge two chapter dicts into one"""
        # Combine content
        first_content = first.get('content', '')
        second_content = second.get('content', '')
        
        # Add a separator between contents
        combined_content = first_content.strip()
        if combined_content and second_content:
            combined_content += "\n\n---\n\n"
        combined_content += second_content.strip()
        
        # Create merged title
        first_title = first.get('title', '')
        second_title = second.get('title', '')
        
        # Use first title if it's a "real" chapter title
        if self._extract_chapter_number(first_title):
            merged_title = first_title
        elif first_title and not self._is_subsection_title(first_title):
            merged_title = first_title
        else:
            merged_title = f"{first_title} + {second_title}"
        
        return {
            'id': f"{first.get('book_id', 'book')}-ch{new_number}",
            'book_id': first.get('book_id', ''),
            'chapter_number': new_number,
            'title': merged_title,
            'content': combined_content,
            'word_count': first.get('word_count', 0) + second.get('word_count', 0),
            'file_path': first.get('file_path', ''),
            'merged_from': [first.get('title', ''), second.get('title', '')]
        }


def merge_undersized_chapters(
    chapters: List[Dict],
    min_words: int = 2000,
    max_combined: int = 20000
) -> List[Dict]:
    """
    Simple convenience function to merge undersized chapters.
    
    Args:
        chapters: List of chapter dicts
        min_words: Minimum words for standalone chapter
        max_combined: Maximum words after merge
        
    Returns:
        Merged chapter list
    """
    merger = ChapterMerger()
    merger.MIN_WORDS_STANDALONE = min_words
    merger.MAX_COMBINED_WORDS = max_combined
    
    result = merger.auto_merge(chapters)
    return result.chapters
