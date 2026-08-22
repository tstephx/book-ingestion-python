"""
Semantic Chunking for Chapter Detection Validation

Uses embeddings to detect topic changes and validate chapter boundaries.
Based on LangChain best practices for RAG text splitting.

Key Features:
- Detects semantic topic shifts using embedding similarity
- Validates regex-detected chapters against semantic boundaries
- Provides confidence scores for chapter boundaries
- Suggests merges for over-fragmented content
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import statistics

# Lazy import for sentence-transformers (optional dependency)
_EMBEDDING_MODEL = None
_HAS_EMBEDDINGS = None


def _check_embeddings_available() -> bool:
    """Check if sentence-transformers is available"""
    global _HAS_EMBEDDINGS
    if _HAS_EMBEDDINGS is None:
        try:
            from sentence_transformers import SentenceTransformer
            _HAS_EMBEDDINGS = True
        except ImportError:
            _HAS_EMBEDDINGS = False
    return _HAS_EMBEDDINGS


def _get_embedding_model():
    """Lazy load the embedding model (singleton pattern)"""
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        if not _check_embeddings_available():
            raise ImportError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
        from sentence_transformers import SentenceTransformer
        # Use lightweight model for speed
        _EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
    return _EMBEDDING_MODEL


@dataclass
class SemanticBoundary:
    """A detected semantic boundary between topics"""
    position: int           # Character position in text
    line_index: int         # Line number
    similarity_score: float # Similarity between adjacent chunks (lower = bigger change)
    is_significant: bool    # True if below threshold (topic shift)
    context_before: str     # Text snippet before boundary
    context_after: str      # Text snippet after boundary


@dataclass
class ChapterValidation:
    """Result of semantic validation for a chapter boundary"""
    chapter_index: int
    title: str
    line_index: int
    word_count: int
    
    # Semantic analysis
    has_semantic_boundary: bool     # Is there a topic shift near this chapter start?
    semantic_confidence: float      # 0-1, how confident are we this is a real chapter
    nearest_boundary_distance: int  # Lines to nearest semantic boundary
    
    # Recommendations
    is_valid: bool
    should_merge_with_previous: bool
    should_merge_with_next: bool
    merge_reason: str = ""


@dataclass 
class SemanticChunkingResult:
    """Complete result of semantic chunking analysis"""
    boundaries: List[SemanticBoundary]
    chapter_validations: List[ChapterValidation]
    overall_confidence: float
    recommendations: List[str]
    statistics: Dict


class RecursiveTextSplitter:
    """
    LangChain-style recursive text splitter with natural separators.
    
    Splits text hierarchically using separators in priority order:
    1. Paragraph breaks (\\n\\n)
    2. Single newlines (\\n)
    3. Sentences (. )
    4. Words ( )
    5. Characters ("")
    """
    
    DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]
    
    def __init__(
        self,
        chunk_size: int = 1500,
        chunk_overlap: int = 200,
        separators: List[str] = None,
        length_function = len
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or self.DEFAULT_SEPARATORS
        self.length_function = length_function
    
    def split_text(self, text: str) -> List[str]:
        """Split text into chunks using recursive character splitting"""
        return self._split_text(text, self.separators)
    
    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        """Recursively split text using separator hierarchy"""
        final_chunks = []
        separator = separators[-1]
        new_separators = []
        
        # Find appropriate separator
        for i, sep in enumerate(separators):
            if sep == "":
                separator = sep
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1:]
                break
        
        # Split using found separator
        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)
        
        # Merge small splits back together
        good_splits = []
        current = ""
        
        for split in splits:
            if self.length_function(current + separator + split) <= self.chunk_size:
                current = current + separator + split if current else split
            else:
                if current:
                    good_splits.append(current)
                
                if self.length_function(split) <= self.chunk_size:
                    current = split
                elif new_separators:
                    # Recursively split with finer separator
                    good_splits.extend(self._split_text(split, new_separators))
                    current = ""
                else:
                    # Can't split further, keep as is
                    good_splits.append(split)
                    current = ""
        
        if current:
            good_splits.append(current)
        
        return good_splits
    
    def split_with_overlap(self, text: str) -> List[Dict]:
        """Split text and include overlap information"""
        chunks = self.split_text(text)
        result = []
        
        current_pos = 0
        for i, chunk in enumerate(chunks):
            # Find actual position in original text
            pos = text.find(chunk, current_pos)
            if pos == -1:
                pos = current_pos
            
            result.append({
                'index': i,
                'content': chunk,
                'start_pos': pos,
                'end_pos': pos + len(chunk),
                'word_count': len(chunk.split())
            })
            
            current_pos = pos + len(chunk)
        
        return result


class SemanticChunker:
    """
    Semantic chunking using embeddings to detect topic changes.
    
    Based on LangChain experimental SemanticChunker pattern.
    Detects where topics actually change vs arbitrary regex matches.
    """
    
    def __init__(
        self,
        buffer_size: int = 200,           # Words to include in each chunk for comparison
        breakpoint_threshold: float = 0.7, # Similarity below this = topic change
        percentile_threshold: float = 0.9, # Use 90th percentile for dynamic threshold
        use_percentile: bool = True        # Use percentile vs fixed threshold
    ):
        self.buffer_size = buffer_size
        self.breakpoint_threshold = breakpoint_threshold
        self.percentile_threshold = percentile_threshold
        self.use_percentile = use_percentile
    
    def detect_boundaries(self, text: str) -> List[SemanticBoundary]:
        """
        Detect semantic boundaries in text using embedding similarity.
        
        Returns list of boundaries sorted by position.
        """
        if not _check_embeddings_available():
            raise ImportError("sentence-transformers required for semantic chunking")
        
        model = _get_embedding_model()
        
        # Split into sentences/chunks for comparison
        sentences = self._split_into_sentences(text)
        if len(sentences) < 2:
            return []
        
        # Generate embeddings
        texts = [s['text'] for s in sentences]
        embeddings = model.encode(texts, show_progress_bar=False)
        
        # Calculate similarity between adjacent chunks
        similarities = []
        for i in range(len(embeddings) - 1):
            sim = self._cosine_similarity(embeddings[i], embeddings[i + 1])
            similarities.append({
                'position': sentences[i]['end_pos'],
                'line_index': sentences[i]['line_index'],
                'similarity': sim,
                'context_before': sentences[i]['text'][:100],
                'context_after': sentences[i + 1]['text'][:100]
            })
        
        # Determine threshold
        if self.use_percentile and similarities:
            sim_values = [s['similarity'] for s in similarities]
            # Low similarity = topic change, so use the low-tail percentile.
            # A linear-interpolated percentile (rather than a truncated list
            # index) avoids collapsing to the bare minimum -- which nothing
            # can ever be "below" -- whenever there are few similarity values
            # (fewer than 10, given the default percentile_threshold=0.9).
            import numpy as np
            threshold = np.percentile(sim_values, (1 - self.percentile_threshold) * 100)
        else:
            threshold = self.breakpoint_threshold
        
        # Create boundary objects
        boundaries = []
        for sim in similarities:
            is_significant = sim['similarity'] < threshold
            boundaries.append(SemanticBoundary(
                position=sim['position'],
                line_index=sim['line_index'],
                similarity_score=sim['similarity'],
                is_significant=is_significant,
                context_before=sim['context_before'],
                context_after=sim['context_after']
            ))
        
        return boundaries
    
    def _split_into_sentences(self, text: str) -> List[Dict]:
        """Split text into sentences with position tracking"""
        # Split by paragraph first, then by sentence
        lines = text.split('\n')
        sentences = []
        current_pos = 0
        
        for line_idx, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                current_pos += len(line) + 1  # +1 for newline
                continue
            
            # Split line into sentences
            parts = re.split(r'(?<=[.!?])\s+', line_stripped)
            
            for part in parts:
                if len(part.split()) >= 5:  # Minimum 5 words
                    sentences.append({
                        'text': part,
                        'start_pos': current_pos,
                        'end_pos': current_pos + len(part),
                        'line_index': line_idx
                    })
            
            current_pos += len(line) + 1
        
        # Merge very short sentences into larger chunks
        merged = []
        current = None
        
        for sent in sentences:
            if current is None:
                current = sent.copy()
                current['text'] = sent['text']
            elif len(current['text'].split()) < self.buffer_size:
                current['text'] += ' ' + sent['text']
                current['end_pos'] = sent['end_pos']
                current['line_index'] = sent['line_index']
            else:
                merged.append(current)
                current = sent.copy()
        
        if current:
            merged.append(current)
        
        return merged
    
    def _cosine_similarity(self, vec1, vec2) -> float:
        """Calculate cosine similarity between two vectors"""
        import numpy as np
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))


class ChapterBoundaryValidator:
    """
    Validates detected chapter boundaries against semantic analysis.
    
    Cross-references regex-detected chapters with semantic topic shifts
    to identify over-fragmentation or missed chapters.
    """
    
    # Thresholds for validation
    MIN_WORDS_FOR_VALID_CHAPTER = 2000
    MAX_WORDS_FOR_VALID_CHAPTER = 20000
    MAX_CHAPTERS_PER_100K_WORDS = 15
    MIN_CHAPTERS_PER_100K_WORDS = 3
    
    # Semantic validation thresholds  
    MAX_DISTANCE_TO_BOUNDARY = 50  # Lines
    MIN_SEMANTIC_CONFIDENCE = 0.5
    
    def __init__(self, use_semantic: bool = True):
        self.use_semantic = use_semantic and _check_embeddings_available()
        self.semantic_chunker = SemanticChunker() if self.use_semantic else None
    
    def validate_chapters(
        self,
        text: str,
        chapters: List[Dict]
    ) -> SemanticChunkingResult:
        """
        Validate chapter detection against semantic boundaries.
        
        Args:
            text: Full book text
            chapters: List of chapter dicts from splitter
            
        Returns:
            SemanticChunkingResult with validations and recommendations
        """
        # Get semantic boundaries if available
        boundaries = []
        if self.use_semantic:
            try:
                boundaries = self.semantic_chunker.detect_boundaries(text)
            except Exception as e:
                # Fall back to non-semantic validation
                print(f"Semantic analysis failed: {e}")
                boundaries = []
        
        # Validate each chapter
        validations = []
        lines = text.split('\n')
        
        for i, chapter in enumerate(chapters):
            validation = self._validate_single_chapter(
                chapter, i, chapters, boundaries, lines
            )
            validations.append(validation)
        
        # Calculate overall statistics
        stats = self._calculate_statistics(validations, chapters)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(validations, stats)
        
        # Calculate overall confidence
        if validations:
            overall_confidence = statistics.mean(
                v.semantic_confidence for v in validations
            )
        else:
            overall_confidence = 0.0
        
        return SemanticChunkingResult(
            boundaries=boundaries,
            chapter_validations=validations,
            overall_confidence=overall_confidence,
            recommendations=recommendations,
            statistics=stats
        )
    
    def _validate_single_chapter(
        self,
        chapter: Dict,
        index: int,
        all_chapters: List[Dict],
        boundaries: List[SemanticBoundary],
        lines: List[str]
    ) -> ChapterValidation:
        """Validate a single chapter boundary"""
        
        word_count = chapter.get('word_count', 0)
        line_index = self._find_chapter_line(chapter, lines)
        
        # Find nearest semantic boundary
        nearest_boundary = None
        nearest_distance = float('inf')
        
        for boundary in boundaries:
            if boundary.is_significant:
                distance = abs(boundary.line_index - line_index)
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest_boundary = boundary
        
        has_semantic_boundary = (
            nearest_boundary is not None and 
            nearest_distance <= self.MAX_DISTANCE_TO_BOUNDARY
        )
        
        # Calculate semantic confidence
        if not boundaries:
            # No semantic analysis available, use heuristics only
            semantic_confidence = self._heuristic_confidence(chapter, word_count)
        elif has_semantic_boundary:
            # Strong semantic boundary nearby
            proximity_factor = 1.0 - (nearest_distance / self.MAX_DISTANCE_TO_BOUNDARY)
            similarity_factor = 1.0 - nearest_boundary.similarity_score
            semantic_confidence = 0.5 + (0.5 * proximity_factor * similarity_factor)
        else:
            # No semantic boundary, lower confidence
            semantic_confidence = 0.3
        
        # Determine merge recommendations
        should_merge_prev = False
        should_merge_next = False
        merge_reason = ""
        
        if word_count < self.MIN_WORDS_FOR_VALID_CHAPTER:
            if index > 0:
                should_merge_prev = True
                merge_reason = f"Chapter too short ({word_count} words)"
            elif index < len(all_chapters) - 1:
                should_merge_next = True
                merge_reason = f"Chapter too short ({word_count} words)"
        
        if not has_semantic_boundary and semantic_confidence < 0.4:
            if index > 0 and word_count < 5000:
                should_merge_prev = True
                merge_reason = f"No semantic boundary + small size"
        
        is_valid = (
            word_count >= self.MIN_WORDS_FOR_VALID_CHAPTER and
            (has_semantic_boundary or semantic_confidence >= self.MIN_SEMANTIC_CONFIDENCE)
        )
        
        return ChapterValidation(
            chapter_index=index,
            title=chapter.get('title', ''),
            line_index=line_index,
            word_count=word_count,
            has_semantic_boundary=has_semantic_boundary,
            semantic_confidence=semantic_confidence,
            nearest_boundary_distance=int(nearest_distance) if nearest_distance != float('inf') else -1,
            is_valid=is_valid,
            should_merge_with_previous=should_merge_prev,
            should_merge_with_next=should_merge_next,
            merge_reason=merge_reason
        )
    
    def _find_chapter_line(self, chapter: Dict, lines: List[str]) -> int:
        """Find the line index where chapter starts"""
        title = chapter.get('title', '')
        if not title:
            return 0
        
        # Search for title in text
        title_lower = title.lower().strip()
        for i, line in enumerate(lines):
            if title_lower in line.lower():
                return i
        
        return 0
    
    def _heuristic_confidence(self, chapter: Dict, word_count: int) -> float:
        """Calculate confidence using heuristics only (no semantic)"""
        confidence = 0.5
        
        # Word count factor
        if self.MIN_WORDS_FOR_VALID_CHAPTER <= word_count <= self.MAX_WORDS_FOR_VALID_CHAPTER:
            confidence += 0.2
        elif word_count < 1000:
            confidence -= 0.2
        elif word_count > 25000:
            confidence -= 0.1
        
        # Title quality factor
        title = chapter.get('title', '')
        if re.match(r'^(Chapter|Part|Lesson|Module|Unit)\s+\d+', title, re.IGNORECASE):
            confidence += 0.2
        elif re.match(r'^Section\s+\d+$', title):
            confidence -= 0.3  # Generic fallback title
        
        return max(0.0, min(1.0, confidence))
    
    def _calculate_statistics(
        self,
        validations: List[ChapterValidation],
        chapters: List[Dict]
    ) -> Dict:
        """Calculate validation statistics"""
        if not validations:
            return {
                'total_chapters': 0,
                'valid_chapters': 0,
                'invalid_chapters': 0,
                'merge_candidates': 0,
                'avg_confidence': 0.0,
                'avg_word_count': 0.0,
                'chapters_with_semantic_boundary': 0
            }
        
        word_counts = [v.word_count for v in validations]
        
        return {
            'total_chapters': len(validations),
            'valid_chapters': sum(1 for v in validations if v.is_valid),
            'invalid_chapters': sum(1 for v in validations if not v.is_valid),
            'merge_candidates': sum(
                1 for v in validations 
                if v.should_merge_with_previous or v.should_merge_with_next
            ),
            'avg_confidence': statistics.mean(v.semantic_confidence for v in validations),
            'avg_word_count': statistics.mean(word_counts),
            'min_word_count': min(word_counts),
            'max_word_count': max(word_counts),
            'chapters_with_semantic_boundary': sum(
                1 for v in validations if v.has_semantic_boundary
            )
        }
    
    def _generate_recommendations(
        self,
        validations: List[ChapterValidation],
        stats: Dict
    ) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # Check for over-fragmentation
        if stats['total_chapters'] > 40:
            recommendations.append(
                f"⚠️ High chapter count ({stats['total_chapters']}) suggests over-fragmentation. "
                f"Consider merging chapters with low confidence scores."
            )
        
        if stats['avg_word_count'] < 2000:
            recommendations.append(
                f"⚠️ Low average chapter size ({stats['avg_word_count']:.0f} words). "
                f"Expected 3,000-15,000 words per chapter."
            )
        
        # Check for under-fragmentation
        if stats['avg_word_count'] > 20000:
            recommendations.append(
                f"⚠️ High average chapter size ({stats['avg_word_count']:.0f} words). "
                f"Some chapters may contain missed splits."
            )
        
        # Specific merge recommendations
        merge_candidates = [v for v in validations if v.should_merge_with_previous]
        if merge_candidates:
            chapters_to_merge = [str(v.chapter_index + 1) for v in merge_candidates[:5]]
            recommendations.append(
                f"💡 Consider merging chapters: {', '.join(chapters_to_merge)} "
                f"with their predecessors."
            )
        
        # Semantic validation summary
        if stats['chapters_with_semantic_boundary'] == 0 and validations:
            recommendations.append(
                "ℹ️ No semantic boundaries detected at chapter starts. "
                "Consider reviewing chapter detection patterns."
            )
        elif stats['chapters_with_semantic_boundary'] < len(validations) * 0.5:
            recommendations.append(
                f"ℹ️ Only {stats['chapters_with_semantic_boundary']}/{len(validations)} "
                f"chapters aligned with semantic topic shifts."
            )
        
        return recommendations


def validate_chunking(chapters: List[Dict]) -> Dict:
    """
    Simple validation function for chapter detection quality.
    
    Quick check for over-fragmentation based on word counts.
    Use ChapterBoundaryValidator for deeper semantic analysis.
    
    Args:
        chapters: List of chapter dictionaries with 'word_count' key
        
    Returns:
        Dictionary with 'valid', 'issue', and 'metrics' keys
    """
    if not chapters:
        return {
            "valid": False,
            "issue": "no_chapters",
            "metrics": {"chapter_count": 0, "avg_words": 0}
        }
    
    word_counts = [c.get('word_count', 0) for c in chapters]
    avg_words = sum(word_counts) / len(word_counts)
    total_words = sum(word_counts)
    
    metrics = {
        "chapter_count": len(chapters),
        "avg_words": avg_words,
        "total_words": total_words,
        "min_words": min(word_counts),
        "max_words": max(word_counts)
    }
    
    # Check for over-fragmentation
    if avg_words < 2000:
        return {
            "valid": False,
            "issue": "over-fragmentation",
            "message": f"Average chapter size ({avg_words:.0f} words) is too small",
            "metrics": metrics
        }
    
    # Check for suspicious chapter count
    if len(chapters) > 40 and avg_words < 5000:
        return {
            "valid": False,
            "issue": "suspicious_chapter_count",
            "message": f"High chapter count ({len(chapters)}) with small avg size ({avg_words:.0f} words)",
            "metrics": metrics
        }
    
    # Check for under-fragmentation (chapters too large)
    if avg_words > 25000:
        return {
            "valid": False,
            "issue": "under-fragmentation",
            "message": f"Average chapter size ({avg_words:.0f} words) is too large",
            "metrics": metrics
        }
    
    # Expected chapters for word count
    expected_chapters = max(3, total_words // 10000)
    if len(chapters) < expected_chapters // 2:
        return {
            "valid": False,
            "issue": "too_few_chapters",
            "message": f"Only {len(chapters)} chapters for {total_words:,} words (expected ~{expected_chapters})",
            "metrics": metrics
        }
    
    return {
        "valid": True,
        "issue": None,
        "metrics": metrics
    }
