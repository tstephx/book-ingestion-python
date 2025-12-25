"""
Tests for Semantic Chunker and Chunk Merger

Tests the LangChain-inspired chunking improvements:
- RecursiveTextSplitter
- SemanticChunker (optional, requires sentence-transformers)
- ChapterBoundaryValidator
- validate_chunking()
"""

import pytest
from src.processors.semantic_chunker import (
    RecursiveTextSplitter,
    validate_chunking,
    ChapterBoundaryValidator,
)


class TestRecursiveTextSplitter:
    """Tests for LangChain-style recursive text splitter"""
    
    def test_split_simple_text(self):
        """Should split text on paragraph boundaries"""
        splitter = RecursiveTextSplitter(chunk_size=100, chunk_overlap=0)
        
        text = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph."
        chunks = splitter.split_text(text)
        
        assert len(chunks) >= 1
        assert "First paragraph" in chunks[0]
    
    def test_split_preserves_paragraphs(self):
        """Should prefer paragraph breaks over word breaks"""
        splitter = RecursiveTextSplitter(chunk_size=200, chunk_overlap=0)
        
        text = """This is the first paragraph with enough words to be meaningful.

This is the second paragraph with different content.

This is the third paragraph to test splitting."""
        
        chunks = splitter.split_text(text)
        
        # Should split on paragraphs, not mid-sentence
        for chunk in chunks:
            # No chunk should end mid-sentence (with partial word)
            assert chunk.strip().endswith('.') or len(chunk.strip()) > 10
    
    def test_split_long_paragraph(self):
        """Should fall back to sentence splitting for long paragraphs"""
        splitter = RecursiveTextSplitter(chunk_size=50, chunk_overlap=0)
        
        text = "This is a very long sentence that exceeds the chunk size limit. " * 10
        chunks = splitter.split_text(text)
        
        # Should create multiple chunks
        assert len(chunks) > 1
        # Each chunk should be under the limit (approximately)
        for chunk in chunks:
            assert len(chunk) <= 100  # Allow some flexibility
    
    def test_split_with_overlap(self):
        """Should track position information"""
        splitter = RecursiveTextSplitter(chunk_size=100, chunk_overlap=20)
        
        text = "First part. Second part. Third part. Fourth part. Fifth part."
        result = splitter.split_with_overlap(text)
        
        assert len(result) >= 1
        assert 'content' in result[0]
        assert 'start_pos' in result[0]
        assert 'end_pos' in result[0]
        assert 'word_count' in result[0]


class TestValidateChunking:
    """Tests for simple chunking validation function"""
    
    def test_valid_chapters(self):
        """Should return valid for well-sized chapters"""
        chapters = [
            {'word_count': 5000, 'title': 'Chapter 1'},
            {'word_count': 6000, 'title': 'Chapter 2'},
            {'word_count': 7000, 'title': 'Chapter 3'},
        ]
        
        result = validate_chunking(chapters)
        
        assert result['valid'] is True
        assert result['issue'] is None
        assert result['metrics']['avg_words'] == 6000
    
    def test_over_fragmentation(self):
        """Should detect over-fragmented chapters"""
        # Many small chapters
        chapters = [
            {'word_count': 500, 'title': f'Section {i}'}
            for i in range(20)
        ]
        
        result = validate_chunking(chapters)
        
        assert result['valid'] is False
        assert result['issue'] == 'over-fragmentation'
        assert 'too small' in result.get('message', '').lower()
    
    def test_under_fragmentation(self):
        """Should detect under-fragmented chapters (too large)"""
        chapters = [
            {'word_count': 50000, 'title': 'Chapter 1'},
            {'word_count': 45000, 'title': 'Chapter 2'},
        ]
        
        result = validate_chunking(chapters)
        
        assert result['valid'] is False
        assert result['issue'] == 'under-fragmentation'
    
    def test_suspicious_count(self):
        """Should detect suspicious chapter count"""
        # Many small chapters
        chapters = [
            {'word_count': 1000, 'title': f'Section {i}'}
            for i in range(50)
        ]
        
        result = validate_chunking(chapters)
        
        assert result['valid'] is False
        assert 'chapter_count' in result['issue'] or 'fragmentation' in result['issue']
    
    def test_no_chapters(self):
        """Should handle empty chapter list"""
        result = validate_chunking([])
        
        assert result['valid'] is False
        assert result['issue'] == 'no_chapters'
    
    def test_metrics_present(self):
        """Should include metrics in result"""
        chapters = [
            {'word_count': 5000, 'title': 'Chapter 1'},
            {'word_count': 5000, 'title': 'Chapter 2'},
        ]
        
        result = validate_chunking(chapters)
        
        assert 'metrics' in result
        assert 'chapter_count' in result['metrics']
        assert 'avg_words' in result['metrics']
        assert 'total_words' in result['metrics']
        assert 'min_words' in result['metrics']
        assert 'max_words' in result['metrics']


class TestChapterBoundaryValidator:
    """Tests for chapter boundary validation"""
    
    def test_validate_with_heuristics(self):
        """Should validate using heuristics when semantic not available"""
        # Create validator without semantic
        validator = ChapterBoundaryValidator(use_semantic=False)
        
        text = "Chapter content here. " * 1000
        chapters = [
            {'title': 'Chapter 1', 'word_count': 5000, 'content': 'Content 1'},
            {'title': 'Chapter 2', 'word_count': 6000, 'content': 'Content 2'},
        ]
        
        result = validator.validate_chapters(text, chapters)
        
        assert result is not None
        assert len(result.chapter_validations) == 2
        assert result.overall_confidence > 0
    
    def test_recommendations_generated(self):
        """Should generate recommendations for issues"""
        validator = ChapterBoundaryValidator(use_semantic=False)
        
        # Create many small chapters to trigger recommendations
        text = "Content. " * 5000
        chapters = [
            {'title': f'Section {i}', 'word_count': 500, 'content': f'Content {i}'}
            for i in range(30)
        ]
        
        result = validator.validate_chapters(text, chapters)
        
        # Should have recommendations for small chapters
        assert len(result.recommendations) > 0
    
    def test_statistics_calculated(self):
        """Should calculate statistics"""
        validator = ChapterBoundaryValidator(use_semantic=False)
        
        text = "Content. " * 1000
        chapters = [
            {'title': 'Chapter 1', 'word_count': 5000, 'content': 'Content'},
            {'title': 'Chapter 2', 'word_count': 6000, 'content': 'Content'},
        ]
        
        result = validator.validate_chapters(text, chapters)
        
        assert 'total_chapters' in result.statistics
        assert 'valid_chapters' in result.statistics
        assert 'avg_confidence' in result.statistics


class TestSemanticChunker:
    """Tests for semantic chunker (requires sentence-transformers)"""
    
    @pytest.fixture
    def check_semantic_available(self):
        """Check if sentence-transformers is available"""
        try:
            from sentence_transformers import SentenceTransformer
            return True
        except ImportError:
            pytest.skip("sentence-transformers not installed")
            return False
    
    def test_detect_boundaries_basic(self, check_semantic_available):
        """Should detect semantic boundaries"""
        from src.processors.semantic_chunker import SemanticChunker
        
        chunker = SemanticChunker()
        
        # Create text with clear topic shifts
        text = """
        Machine learning is a subset of artificial intelligence.
        It involves training models on data to make predictions.
        Neural networks are commonly used in machine learning.
        
        Cooking is a creative art form that combines flavors.
        Fresh ingredients are essential for good cuisine.
        Different cultures have unique cooking traditions.
        
        Space exploration has advanced significantly.
        Rockets carry astronauts to the International Space Station.
        Mars is a primary target for future missions.
        """
        
        boundaries = chunker.detect_boundaries(text)
        
        assert len(boundaries) > 0
        # Should detect topic shifts between the three different topics
        assert any(b.is_significant for b in boundaries)


# Integration tests
class TestChunkingIntegration:
    """Integration tests for the full chunking pipeline"""
    
    def test_full_validation_pipeline(self):
        """Test complete validation pipeline"""
        from src.processors.semantic_chunker import (
            validate_chunking,
            ChapterBoundaryValidator,
        )
        from src.processors.chunk_merger import ChapterMerger
        
        # Create test chapters
        chapters = [
            {'title': 'Chapter 1', 'word_count': 5000, 'content': 'Content 1', 'book_id': 'test'},
            {'title': 'Chapter 2', 'word_count': 6000, 'content': 'Content 2', 'book_id': 'test'},
            {'title': 'Chapter 3', 'word_count': 4500, 'content': 'Content 3', 'book_id': 'test'},
        ]
        
        # Step 1: Quick validation
        result = validate_chunking(chapters)
        assert result['valid'] is True
        
        # Step 2: Check if merger would recommend changes
        merger = ChapterMerger()
        assert not merger.should_merge_chapters(chapters)
    
    def test_problematic_book_detection(self):
        """Test detection of problematic books"""
        from src.processors.semantic_chunker import validate_chunking
        from src.processors.chunk_merger import ChapterMerger
        
        # Create problematic chapters (over-fragmented)
        chapters = [
            {'title': f'Section {i}', 'word_count': 800, 'content': f'Short content {i}', 'book_id': 'test'}
            for i in range(25)
        ]
        
        # Step 1: Detect problem
        result = validate_chunking(chapters)
        assert result['valid'] is False
        
        # Step 2: Merger should recommend fixes
        merger = ChapterMerger()
        assert merger.should_merge_chapters(chapters)
        
        # Step 3: Find merge candidates
        candidates = merger.find_merge_candidates(chapters)
        assert len(candidates) > 0
