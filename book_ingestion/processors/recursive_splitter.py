"""
Recursive Text Splitter with Natural Separators

Based on LangChain's RecursiveCharacterTextSplitter approach:
1. Try to split on largest semantic separators first (chapters, paragraphs)
2. Fall back to smaller separators if chunks are still too large
3. Preserve context with configurable overlap

This provides LangChain-style chunking while being tailored for
book content processing.

Reference: LLM Design Patterns, Chapter on Chunking Strategies
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class SeparatorType(Enum):
    """Types of text separators in order of preference"""
    CHAPTER = "chapter"           # Explicit chapter markers
    SECTION = "section"           # Section/part markers
    DOUBLE_NEWLINE = "paragraph"  # Paragraph breaks
    NEWLINE = "line"              # Line breaks
    SENTENCE = "sentence"         # Sentence boundaries
    WORD = "word"                 # Word boundaries


@dataclass
class TextChunk:
    """A chunk of text with metadata"""
    text: str
    start_index: int      # Character index in original text
    end_index: int
    word_count: int
    separator_used: SeparatorType
    chunk_index: int = 0


@dataclass
class SplitResult:
    """Result of recursive splitting"""
    chunks: List[TextChunk]
    total_chunks: int
    avg_chunk_size: float
    min_chunk_size: int
    max_chunk_size: int
    separators_used: dict  # Count by separator type


class RecursiveTextSplitter:
    """
    Splits text recursively using natural separators.
    
    Unlike simple fixed-size splitting, this tries to preserve
    semantic boundaries by using a hierarchy of separators.
    """
    
    # Default separator patterns in order of preference
    DEFAULT_SEPARATORS = [
        # Chapter-level patterns (most preferred)
        (r'\n\s*(?=Chapter\s+\d+)', SeparatorType.CHAPTER),
        (r'\n\s*(?=CHAPTER\s+\d+)', SeparatorType.CHAPTER),
        (r'\n\s*(?=Part\s+\d+)', SeparatorType.SECTION),
        (r'\n\s*(?=Section\s+\d+)', SeparatorType.SECTION),
        
        # Paragraph breaks (double newline)
        (r'\n\n+', SeparatorType.DOUBLE_NEWLINE),
        
        # Single newlines
        (r'\n', SeparatorType.NEWLINE),
        
        # Sentence boundaries
        (r'(?<=[.!?])\s+', SeparatorType.SENTENCE),
        
        # Word boundaries (last resort)
        (r'\s+', SeparatorType.WORD),
    ]
    
    def __init__(
        self,
        chunk_size: int = 10000,       # Target words per chunk
        chunk_overlap: int = 200,       # Words of overlap
        min_chunk_size: int = 500,      # Minimum words per chunk
        max_chunk_size: int = 20000,    # Maximum words per chunk
        separators: List[Tuple[str, SeparatorType]] = None,
        length_function: Callable[[str], int] = None,
    ):
        """
        Initialize the recursive splitter.
        
        Args:
            chunk_size: Target number of words per chunk
            chunk_overlap: Words to overlap between chunks for context
            min_chunk_size: Don't create chunks smaller than this
            max_chunk_size: Force split chunks larger than this
            separators: Custom separator patterns (regex, type) tuples
            length_function: Custom length function (default: word count)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        
        # Compile separator patterns
        self.separators = []
        for pattern, sep_type in (separators or self.DEFAULT_SEPARATORS):
            try:
                self.separators.append((re.compile(pattern), sep_type))
            except re.error as e:
                logger.warning(f"Invalid separator pattern '{pattern}': {e}")
                
        self.length_function = length_function or self._word_count
        
    def _word_count(self, text: str) -> int:
        """Count words in text"""
        return len(text.split())
    
    def split(self, text: str) -> SplitResult:
        """
        Split text into chunks using recursive separator approach.
        
        Returns:
            SplitResult with chunks and statistics
        """
        if not text or not text.strip():
            return SplitResult(
                chunks=[],
                total_chunks=0,
                avg_chunk_size=0,
                min_chunk_size=0,
                max_chunk_size=0,
                separators_used={}
            )
        
        # Track separator usage
        separator_counts = {sep_type: 0 for sep_type in SeparatorType}
        
        # Recursively split
        chunks = self._recursive_split(text, 0, separator_counts)
        
        # Add overlap between chunks
        if self.chunk_overlap > 0 and len(chunks) > 1:
            chunks = self._add_overlap(chunks, text)
        
        # Merge chunks that are too small
        chunks = self._merge_small_chunks(chunks)
        
        # Update chunk indices
        for i, chunk in enumerate(chunks):
            chunk.chunk_index = i
            
        # Calculate statistics
        word_counts = [chunk.word_count for chunk in chunks]
        
        return SplitResult(
            chunks=chunks,
            total_chunks=len(chunks),
            avg_chunk_size=sum(word_counts) / len(word_counts) if word_counts else 0,
            min_chunk_size=min(word_counts) if word_counts else 0,
            max_chunk_size=max(word_counts) if word_counts else 0,
            separators_used={k.value: v for k, v in separator_counts.items() if v > 0}
        )
    
    def _recursive_split(
        self,
        text: str,
        separator_index: int,
        separator_counts: dict
    ) -> List[TextChunk]:
        """
        Recursively split text using separator hierarchy.
        
        Tries each separator in order until chunks are small enough.
        """
        word_count = self._word_count(text)
        
        # Base case: text is small enough
        if word_count <= self.chunk_size:
            return [TextChunk(
                text=text,
                start_index=0,  # Will be updated by caller
                end_index=len(text),
                word_count=word_count,
                separator_used=SeparatorType.WORD  # Default
            )]
        
        # Try each separator level
        for sep_idx in range(separator_index, len(self.separators)):
            pattern, sep_type = self.separators[sep_idx]
            
            # Split using this separator
            splits = self._split_by_pattern(text, pattern)
            
            if len(splits) > 1:
                # Successfully split - recursively process each part
                chunks = []
                current_pos = 0
                
                for split_text in splits:
                    if not split_text.strip():
                        current_pos += len(split_text)
                        continue
                        
                    # Recursively split if still too large
                    sub_chunks = self._recursive_split(
                        split_text, 
                        sep_idx + 1, 
                        separator_counts
                    )
                    
                    # Update positions and separator info
                    for chunk in sub_chunks:
                        chunk.start_index += current_pos
                        chunk.end_index += current_pos
                        if chunk.separator_used == SeparatorType.WORD:
                            chunk.separator_used = sep_type
                            
                    chunks.extend(sub_chunks)
                    separator_counts[sep_type] += 1
                    current_pos += len(split_text)
                    
                return chunks
        
        # No separator worked - force split at word boundaries
        return self._force_split(text)
    
    def _split_by_pattern(self, text: str, pattern: re.Pattern) -> List[str]:
        """Split text by regex pattern, keeping the delimiters"""
        # Find all matches
        splits = []
        last_end = 0
        
        for match in pattern.finditer(text):
            if match.start() > last_end:
                splits.append(text[last_end:match.start()])
            # Keep the delimiter with the following text
            last_end = match.start()
            
        # Add remaining text
        if last_end < len(text):
            splits.append(text[last_end:])
            
        return splits
    
    def _force_split(self, text: str) -> List[TextChunk]:
        """Force split text at word boundaries when no separator works"""
        words = text.split()
        chunks = []
        current_words = []
        current_start = 0
        word_pos = 0
        
        for word in words:
            current_words.append(word)
            
            if len(current_words) >= self.chunk_size:
                chunk_text = ' '.join(current_words)
                chunks.append(TextChunk(
                    text=chunk_text,
                    start_index=current_start,
                    end_index=current_start + len(chunk_text),
                    word_count=len(current_words),
                    separator_used=SeparatorType.WORD
                ))
                
                current_start += len(chunk_text) + 1
                current_words = []
                
        # Don't forget the last chunk
        if current_words:
            chunk_text = ' '.join(current_words)
            chunks.append(TextChunk(
                text=chunk_text,
                start_index=current_start,
                end_index=current_start + len(chunk_text),
                word_count=len(current_words),
                separator_used=SeparatorType.WORD
            ))
            
        return chunks
    
    def _add_overlap(self, chunks: List[TextChunk], original_text: str) -> List[TextChunk]:
        """Add overlap between chunks for context preservation"""
        if len(chunks) < 2:
            return chunks
            
        overlapped_chunks = []
        
        for i, chunk in enumerate(chunks):
            new_text = chunk.text
            new_start = chunk.start_index
            
            # Add overlap from previous chunk
            if i > 0 and self.chunk_overlap > 0:
                prev_chunk = chunks[i - 1]
                prev_words = prev_chunk.text.split()
                overlap_words = prev_words[-self.chunk_overlap:] if len(prev_words) > self.chunk_overlap else prev_words
                overlap_text = ' '.join(overlap_words)
                
                new_text = overlap_text + ' ' + new_text
                # Adjust start index (approximate)
                new_start = max(0, chunk.start_index - len(overlap_text) - 1)
                
            overlapped_chunks.append(TextChunk(
                text=new_text,
                start_index=new_start,
                end_index=chunk.end_index,
                word_count=len(new_text.split()),
                separator_used=chunk.separator_used,
                chunk_index=i
            ))
            
        return overlapped_chunks
    
    def _merge_small_chunks(self, chunks: List[TextChunk]) -> List[TextChunk]:
        """Merge chunks that are too small"""
        if not chunks:
            return chunks
            
        merged = []
        current = None
        
        for chunk in chunks:
            if current is None:
                current = chunk
                continue
                
            # Merge if current chunk is too small
            if current.word_count < self.min_chunk_size:
                # Merge with next chunk
                current = TextChunk(
                    text=current.text + '\n' + chunk.text,
                    start_index=current.start_index,
                    end_index=chunk.end_index,
                    word_count=current.word_count + chunk.word_count,
                    separator_used=current.separator_used
                )
            else:
                merged.append(current)
                current = chunk
                
        # Don't forget the last chunk
        if current is not None:
            merged.append(current)
            
        return merged


class ChapterAwareSplitter(RecursiveTextSplitter):
    """
    Extension of RecursiveTextSplitter specifically for book chapters.
    
    Adds:
    - Target chapter size of 3,000-15,000 words
    - Better handling of chapter-like patterns
    - Quality metrics for splits
    """
    
    # Target chapter sizes based on book research
    TARGET_MIN_WORDS = 3000
    TARGET_MAX_WORDS = 15000
    IDEAL_CHAPTER_WORDS = 8000  # Average chapter size
    
    # Chapter-specific separators
    CHAPTER_SEPARATORS = [
        # Primary chapter patterns
        (r'\n\s*(?=CHAPTER\s+\d+)', SeparatorType.CHAPTER),
        (r'\n\s*(?=Chapter\s+\d+)', SeparatorType.CHAPTER),
        (r'\n\s*(?=PART\s+[IVX\d]+)', SeparatorType.SECTION),
        (r'\n\s*(?=Part\s+[IVX\d]+)', SeparatorType.SECTION),
        
        # Section patterns
        (r'\n\s*(?=Section\s+\d+)', SeparatorType.SECTION),
        (r'\n\s*(?=MODULE\s+\d+)', SeparatorType.SECTION),
        (r'\n\s*(?=Lesson\s+\d+)', SeparatorType.SECTION),
        
        # Numbered headings
        (r'\n\s*(?=\d+\.\s+[A-Z])', SeparatorType.SECTION),
        
        # Multiple blank lines (section break)
        (r'\n{3,}', SeparatorType.DOUBLE_NEWLINE),
        
        # Standard paragraph breaks
        (r'\n\n+', SeparatorType.DOUBLE_NEWLINE),
        
        # Line breaks
        (r'\n', SeparatorType.NEWLINE),
        
        # Sentences
        (r'(?<=[.!?])\s+', SeparatorType.SENTENCE),
        
        # Words
        (r'\s+', SeparatorType.WORD),
    ]
    
    def __init__(
        self,
        target_words: int = None,
        min_words: int = None,
        max_words: int = None,
        overlap: int = 200,
    ):
        """
        Initialize chapter-aware splitter.
        
        Args:
            target_words: Target words per chapter (default: 8000)
            min_words: Minimum chapter size (default: 3000)
            max_words: Maximum chapter size (default: 15000)
            overlap: Word overlap for context
        """
        super().__init__(
            chunk_size=target_words or self.IDEAL_CHAPTER_WORDS,
            chunk_overlap=overlap,
            min_chunk_size=min_words or self.TARGET_MIN_WORDS,
            max_chunk_size=max_words or self.TARGET_MAX_WORDS,
            separators=self.CHAPTER_SEPARATORS
        )
        
    def validate_splits(self, result: SplitResult) -> dict:
        """
        Validate split quality against chapter targets.
        
        Returns:
            Dict with validation results and recommendations
        """
        issues = []
        recommendations = []
        
        # Check average size
        if result.avg_chunk_size < self.TARGET_MIN_WORDS:
            issues.append(f"Average chunk size ({result.avg_chunk_size:.0f}) below target ({self.TARGET_MIN_WORDS})")
            recommendations.append("Consider merging small chapters")
            
        if result.avg_chunk_size > self.TARGET_MAX_WORDS:
            issues.append(f"Average chunk size ({result.avg_chunk_size:.0f}) above target ({self.TARGET_MAX_WORDS})")
            recommendations.append("Consider splitting large chapters")
            
        # Check individual chunks
        undersized = sum(1 for c in result.chunks if c.word_count < self.TARGET_MIN_WORDS)
        oversized = sum(1 for c in result.chunks if c.word_count > self.TARGET_MAX_WORDS)
        
        if undersized > 0:
            issues.append(f"{undersized} chunks below minimum size")
            
        if oversized > 0:
            issues.append(f"{oversized} chunks above maximum size")
            
        # Check chunk count
        total_words = sum(c.word_count for c in result.chunks)
        expected_chapters = max(1, total_words // self.IDEAL_CHAPTER_WORDS)
        
        if result.total_chunks > expected_chapters * 2:
            issues.append(f"Too many chunks ({result.total_chunks}) for word count ({total_words})")
            recommendations.append("Possible over-fragmentation")
            
        if result.total_chunks < expected_chapters // 2 and expected_chapters > 2:
            issues.append(f"Too few chunks ({result.total_chunks}) for word count ({total_words})")
            recommendations.append("Possible under-detection")
            
        # Calculate quality score
        quality_score = 100
        quality_score -= len(issues) * 10
        quality_score -= undersized * 5
        quality_score -= oversized * 5
        quality_score = max(0, min(100, quality_score))
        
        return {
            "valid": len(issues) == 0,
            "quality_score": quality_score,
            "issues": issues,
            "recommendations": recommendations,
            "stats": {
                "total_chunks": result.total_chunks,
                "expected_chapters": expected_chapters,
                "undersized_count": undersized,
                "oversized_count": oversized,
                "avg_chunk_size": result.avg_chunk_size,
                "target_range": f"{self.TARGET_MIN_WORDS}-{self.TARGET_MAX_WORDS}"
            }
        }
