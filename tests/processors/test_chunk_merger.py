"""
Tests for Chunk Merger

Tests the intelligent chapter merging functionality:
- MergeCandidate detection
- ChapterMerger merging logic
- Auto-merge functionality
"""

import pytest
from copy import deepcopy
from book_ingestion.processors.chunk_merger import (
    ChapterMerger,
    MergeCandidate,
    MergeResult,
    merge_undersized_chapters,
)


class TestChapterMerger:
    """Tests for ChapterMerger class"""
    
    @pytest.fixture
    def merger(self):
        """Create a ChapterMerger instance"""
        return ChapterMerger()
    
    @pytest.fixture
    def sample_chapters(self):
        """Create sample chapter data"""
        return [
            {
                'id': 'test-ch1',
                'book_id': 'test',
                'chapter_number': 1,
                'title': 'Chapter 1: Introduction',
                'content': 'This is the introduction content. ' * 100,
                'word_count': 3000,
            },
            {
                'id': 'test-ch2',
                'book_id': 'test',
                'chapter_number': 2,
                'title': 'Chapter 2: Getting Started',
                'content': 'This is chapter 2 content. ' * 150,
                'word_count': 4500,
            },
            {
                'id': 'test-ch3',
                'book_id': 'test',
                'chapter_number': 3,
                'title': 'Chapter 3: Advanced Topics',
                'content': 'This is advanced content. ' * 200,
                'word_count': 6000,
            },
        ]
    
    @pytest.fixture
    def undersized_chapters(self):
        """Create undersized chapters that need merging"""
        return [
            {
                'id': 'test-ch1',
                'book_id': 'test',
                'chapter_number': 1,
                'title': 'Chapter 1: Intro',
                'content': 'Short intro. ' * 50,
                'word_count': 500,
            },
            {
                'id': 'test-ch2',
                'book_id': 'test',
                'chapter_number': 2,
                'title': 'Section 2',
                'content': 'Section content. ' * 60,
                'word_count': 600,
            },
            {
                'id': 'test-ch3',
                'book_id': 'test',
                'chapter_number': 3,
                'title': 'Chapter 3: Main',
                'content': 'Main content. ' * 200,
                'word_count': 4000,
            },
            {
                'id': 'test-ch4',
                'book_id': 'test',
                'chapter_number': 4,
                'title': 'Summary',
                'content': 'Summary content. ' * 40,
                'word_count': 400,
            },
        ]
    
    def test_should_merge_well_sized(self, merger, sample_chapters):
        """Should not recommend merging well-sized chapters"""
        assert merger.should_merge_chapters(sample_chapters) is False
    
    def test_should_merge_undersized(self, merger, undersized_chapters):
        """Should recommend merging undersized chapters"""
        assert merger.should_merge_chapters(undersized_chapters) is True
    
    def test_should_merge_empty(self, merger):
        """Should not recommend merging empty list"""
        assert merger.should_merge_chapters([]) is False
    
    def test_should_merge_too_few(self, merger):
        """Should not recommend merging with too few chapters"""
        chapters = [{'word_count': 100}]
        assert merger.should_merge_chapters(chapters) is False
    
    def test_find_candidates_undersized(self, merger, undersized_chapters):
        """Should find merge candidates for undersized chapters"""
        candidates = merger.find_merge_candidates(undersized_chapters)
        
        assert len(candidates) > 0
        
        # Should identify the small chapters
        indices = {c.first_index for c in candidates} | {c.second_index for c in candidates}
        assert 0 in indices  # Chapter 1 (500 words)
        assert 1 in indices  # Section 2 (600 words)
    
    def test_find_candidates_sorted_by_score(self, merger, undersized_chapters):
        """Candidates should be sorted by merge score"""
        candidates = merger.find_merge_candidates(undersized_chapters)
        
        if len(candidates) >= 2:
            for i in range(len(candidates) - 1):
                assert candidates[i].merge_score >= candidates[i + 1].merge_score
    
    def test_find_candidates_has_reasons(self, merger, undersized_chapters):
        """Each candidate should have merge reasons"""
        candidates = merger.find_merge_candidates(undersized_chapters)
        
        for candidate in candidates:
            assert len(candidate.merge_reasons) > 0
    
    def test_find_candidates_no_oversized_combined(self, merger):
        """Should not suggest merges that would exceed max size"""
        # Two large chapters
        chapters = [
            {'word_count': 15000, 'title': 'Chapter 1', 'book_id': 'test'},
            {'word_count': 15000, 'title': 'Chapter 2', 'book_id': 'test'},
        ]
        
        candidates = merger.find_merge_candidates(chapters)
        
        # Should not suggest merging these (combined would be 30000)
        for candidate in candidates:
            assert candidate.combined_word_count <= merger.MAX_COMBINED_WORDS
    
    def test_merge_chapters_basic(self, merger, undersized_chapters):
        """Should merge undersized chapters"""
        result = merger.merge_chapters(undersized_chapters, max_merges=1)
        
        assert isinstance(result, MergeResult)
        assert result.original_count == 4
        assert result.merged_count <= 4
        assert result.merges_performed <= 1
    
    def test_merge_chapters_reduces_count(self, merger, undersized_chapters):
        """Merging should reduce chapter count"""
        result = merger.merge_chapters(undersized_chapters, max_merges=2)
        
        assert result.merged_count < result.original_count
        assert len(result.chapters) == result.merged_count
    
    def test_merge_chapters_preserves_content(self, merger, undersized_chapters):
        """Merged chapters should preserve all content"""
        original_words = sum(c['word_count'] for c in undersized_chapters)
        
        result = merger.merge_chapters(undersized_chapters, max_merges=2)
        merged_words = sum(c['word_count'] for c in result.chapters)
        
        # Word count should be preserved
        assert merged_words == original_words
    
    def test_merge_chapters_renumbers(self, merger, undersized_chapters):
        """Merged chapters should be renumbered"""
        result = merger.merge_chapters(undersized_chapters, max_merges=2)
        
        for i, chapter in enumerate(result.chapters):
            assert chapter['chapter_number'] == i + 1
    
    def test_merge_chapters_no_action_needed(self, merger, sample_chapters):
        """Should not merge well-sized chapters"""
        result = merger.merge_chapters(sample_chapters)
        
        assert result.merges_performed == 0
        assert result.merged_count == result.original_count
    
    def test_merge_chapters_empty(self, merger):
        """Should handle empty chapter list"""
        result = merger.merge_chapters([])
        
        assert result.original_count == 0
        assert result.merged_count == 0
        assert result.merges_performed == 0
    
    def test_merge_chapters_with_min_score(self, merger, undersized_chapters):
        """Should respect minimum score threshold"""
        # High threshold should reduce merges
        result_high = merger.merge_chapters(undersized_chapters, min_score=0.9)
        result_low = merger.merge_chapters(undersized_chapters, min_score=0.1)
        
        # Lower threshold should allow more merges (or equal)
        assert result_low.merges_performed >= result_high.merges_performed
    
    def test_auto_merge_reaches_target(self, merger):
        """Auto-merge should attempt to reach target avg size"""
        # Many small chapters
        chapters = [
            {
                'id': f'test-ch{i}',
                'book_id': 'test',
                'chapter_number': i,
                'title': f'Section {i}',
                'content': f'Content {i}. ' * 100,
                'word_count': 1000,
            }
            for i in range(10)
        ]
        
        result = merger.auto_merge(chapters, target_avg_words=4000)
        
        if result.chapters:
            avg_words = sum(c['word_count'] for c in result.chapters) / len(result.chapters)
            # Should get closer to target
            assert avg_words > 1000
    
    def test_auto_merge_stops_when_no_candidates(self, merger, sample_chapters):
        """Auto-merge should stop when no candidates remain"""
        result = merger.auto_merge(sample_chapters)
        
        # Well-sized chapters shouldn't be merged much
        assert result.merged_count >= len(sample_chapters) - 1
    
    def test_quality_improvement_positive(self, merger, undersized_chapters):
        """Merging should improve quality (increase avg size)"""
        result = merger.auto_merge(undersized_chapters)
        
        # Quality improvement should be positive (avg increased)
        assert result.quality_improvement >= 0


class TestMergeCandidate:
    """Tests for MergeCandidate dataclass"""
    
    def test_merge_candidate_creation(self):
        """Should create valid MergeCandidate"""
        candidate = MergeCandidate(
            first_index=0,
            second_index=1,
            combined_word_count=5000,
            merge_score=0.7,
            merge_reasons=['Too small', 'Sequential']
        )
        
        assert candidate.first_index == 0
        assert candidate.second_index == 1
        assert candidate.combined_word_count == 5000
        assert candidate.merge_score == 0.7
        assert len(candidate.merge_reasons) == 2


class TestMergeResult:
    """Tests for MergeResult dataclass"""
    
    def test_merge_result_creation(self):
        """Should create valid MergeResult"""
        chapters = [{'word_count': 5000}]
        result = MergeResult(
            original_count=3,
            merged_count=2,
            merges_performed=1,
            merge_details=[(0, 1)],
            chapters=chapters,
            quality_improvement=1500.0
        )
        
        assert result.original_count == 3
        assert result.merged_count == 2
        assert result.merges_performed == 1
        assert len(result.merge_details) == 1
        assert result.quality_improvement == 1500.0


class TestMergeUndersizedChapters:
    """Tests for convenience function"""
    
    def test_merge_undersized_basic(self):
        """Convenience function should work"""
        chapters = [
            {'id': f'ch{i}', 'book_id': 'test', 'chapter_number': i,
             'title': f'Section {i}', 'content': f'Content {i}', 'word_count': 500}
            for i in range(5)
        ]
        
        result = merge_undersized_chapters(chapters)
        
        assert len(result) < len(chapters)
    
    def test_merge_undersized_custom_threshold(self):
        """Should respect custom min_words threshold"""
        chapters = [
            {'id': f'ch{i}', 'book_id': 'test', 'chapter_number': i,
             'title': f'Chapter {i}', 'content': f'Content {i}', 'word_count': 3000}
            for i in range(4)
        ]
        
        # With default threshold (2000), these shouldn't merge
        result_default = merge_undersized_chapters(chapters, min_words=2000)
        
        # With higher threshold, they might
        result_high = merge_undersized_chapters(chapters, min_words=4000)
        
        # Higher threshold should cause more merges
        assert len(result_high) <= len(result_default)


class TestSubsectionDetection:
    """Tests for subsection title detection"""
    
    @pytest.fixture
    def merger(self):
        return ChapterMerger()
    
    def test_detects_section_pattern(self, merger):
        """Should detect 'Section N' as subsection"""
        assert merger._is_subsection_title('Section 1') is True
        assert merger._is_subsection_title('Section 42') is True
    
    def test_detects_numbered_subsection(self, merger):
        """Should detect '1.1 Title' as subsection"""
        assert merger._is_subsection_title('1.1 Getting Started') is True
        assert merger._is_subsection_title('2.3.1 Deep Nesting') is True
    
    def test_detects_intro_conclusion(self, merger):
        """Should detect intro/summary as subsection"""
        assert merger._is_subsection_title('Introduction') is True
        assert merger._is_subsection_title('Summary') is True
        assert merger._is_subsection_title('Conclusion') is True
        assert merger._is_subsection_title('Preface') is True
    
    def test_real_chapter_not_subsection(self, merger):
        """Real chapter titles should not be subsections"""
        assert merger._is_subsection_title('Chapter 1: Getting Started') is False
        assert merger._is_subsection_title('Building Your First App') is False
        assert merger._is_subsection_title('Advanced Docker Techniques') is False


class TestChapterNumberExtraction:
    """Tests for chapter number extraction"""
    
    @pytest.fixture
    def merger(self):
        return ChapterMerger()
    
    def test_extract_chapter_number(self, merger):
        """Should extract chapter number from title"""
        assert merger._extract_chapter_number('Chapter 5: Title') == 5
        assert merger._extract_chapter_number('Chapter 12') == 12
    
    def test_extract_numbered_title(self, merger):
        """Should extract from numbered format"""
        assert merger._extract_chapter_number('1. Introduction') == 1
        assert merger._extract_chapter_number('10. Conclusion') == 10
    
    def test_extract_no_number(self, merger):
        """Should return None for titles without numbers"""
        assert merger._extract_chapter_number('Introduction') is None
        assert merger._extract_chapter_number('Getting Started') is None
