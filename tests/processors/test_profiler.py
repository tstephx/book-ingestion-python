"""Tests for data profiling"""

import pytest
from src.processors.profiler import DataProfiler, BookProfile, QualityReport


@pytest.fixture
def profiler():
    return DataProfiler()


@pytest.fixture
def sample_metadata():
    return {
        'id': 'test-book-123',
        'title': 'Test Book',
        'author': 'Test Author',
        'word_count': 50000,
        'source_file': '/path/to/book.pdf'
    }


@pytest.fixture
def sample_chapters():
    return [
        {'id': '1', 'title': 'Chapter 1', 'word_count': 5000},
        {'id': '2', 'title': 'Chapter 2', 'word_count': 6000},
        {'id': '3', 'title': 'Chapter 3', 'word_count': 5500},
        {'id': '4', 'title': 'Chapter 4', 'word_count': 4800},
        {'id': '5', 'title': 'Chapter 5', 'word_count': 5200},
    ]


class TestBookProfile:
    def test_profile_creation(self, profiler, sample_metadata, sample_chapters):
        profile = profiler.profile_book(sample_metadata, sample_chapters)

        assert profile.book_id == 'test-book-123'
        assert profile.total_chapters == 5
        assert profile.total_words == 26500
        assert profile.min_chapter_words == 4800
        assert profile.max_chapter_words == 6000

    def test_avg_chapter_words(self, profiler, sample_metadata, sample_chapters):
        profile = profiler.profile_book(sample_metadata, sample_chapters)
        assert profile.avg_chapter_words == 5300.0  # (5000+6000+5500+4800+5200)/5

    def test_estimated_tokens(self, profiler, sample_metadata, sample_chapters):
        profile = profiler.profile_book(sample_metadata, sample_chapters)
        # ~1.33 tokens per word
        assert profile.estimated_tokens == int(26500 / 0.75)

    def test_chapters_under_threshold(self, profiler, sample_metadata):
        chapters = [
            {'id': '1', 'title': 'Short', 'word_count': 100},  # Under threshold
            {'id': '2', 'title': 'Normal', 'word_count': 5000},
            {'id': '3', 'title': 'Tiny', 'word_count': 50},  # Under threshold
        ]
        profile = profiler.profile_book(sample_metadata, chapters)
        assert profile.chapters_under_threshold == 2

    def test_chapters_over_threshold(self, profiler, sample_metadata):
        chapters = [
            {'id': '1', 'title': 'Huge', 'word_count': 25000},  # Over threshold
            {'id': '2', 'title': 'Normal', 'word_count': 5000},
            {'id': '3', 'title': 'Giant', 'word_count': 30000},  # Over threshold
        ]
        profile = profiler.profile_book(sample_metadata, chapters)
        assert profile.chapters_over_threshold == 2

    def test_empty_chapters(self, profiler, sample_metadata):
        profile = profiler.profile_book(sample_metadata, [])
        assert profile.total_chapters == 0
        assert profile.total_words == 0
        assert profile.avg_chapter_words == 0

    def test_single_chapter(self, profiler, sample_metadata):
        chapters = [{'id': '1', 'title': 'Only Chapter', 'word_count': 10000}]
        profile = profiler.profile_book(sample_metadata, chapters)
        assert profile.total_chapters == 1
        assert profile.chapter_word_variance == 0  # No variance with single chapter


class TestMetadataCompleteness:
    def test_complete_metadata(self, profiler):
        metadata = {
            'id': 'test-123',
            'title': 'Test Book',
            'author': 'Author',
            'word_count': 50000,
            'source_file': '/path/to/book.pdf'
        }
        completeness = profiler._calculate_completeness(metadata)
        assert completeness == 1.0

    def test_minimal_metadata(self, profiler):
        metadata = {'id': 'test-123', 'title': 'Test Book'}
        completeness = profiler._calculate_completeness(metadata)
        # Has required fields but not optional
        assert 0.5 <= completeness < 1.0

    def test_empty_metadata(self, profiler):
        completeness = profiler._calculate_completeness({})
        assert completeness == 0.0

    def test_partial_metadata(self, profiler):
        metadata = {'id': 'test-123'}  # Missing title
        completeness = profiler._calculate_completeness(metadata)
        assert completeness < 0.5


class TestQualityAssessment:
    def test_high_quality_book(self, profiler, sample_metadata, sample_chapters):
        profile = profiler.profile_book(sample_metadata, sample_chapters)
        quality = profiler.assess_quality(profile)

        assert quality.quality_score >= 75
        assert len(quality.warnings) == 0

    def test_low_quality_single_chapter(self, profiler):
        metadata = {'id': 'test-123', 'title': 'Test'}
        chapters = [{'id': '1', 'title': 'Chapter', 'word_count': 50000}]

        profile = profiler.profile_book(metadata, chapters)
        quality = profiler.assess_quality(profile)

        assert quality.quality_score < 75
        assert any('1 chapter' in w.lower() for w in quality.warnings)

    def test_uneven_chapters_warning(self, profiler, sample_metadata):
        # Very uneven chapters
        chapters = [
            {'id': '1', 'word_count': 100},
            {'id': '2', 'word_count': 50000},
            {'id': '3', 'word_count': 200},
        ]
        profile = profiler.profile_book(sample_metadata, chapters)
        quality = profiler.assess_quality(profile)

        assert any('variance' in w.lower() for w in quality.warnings)

    def test_encoding_issues_affect_score(self, profiler, sample_metadata, sample_chapters):
        profile_clean = profiler.profile_book(sample_metadata, sample_chapters, encoding_issues=0)
        profile_issues = profiler.profile_book(sample_metadata, sample_chapters, encoding_issues=20)

        quality_clean = profiler.assess_quality(profile_clean)
        quality_issues = profiler.assess_quality(profile_issues)

        assert quality_clean.quality_score > quality_issues.quality_score

    def test_small_chapters_warning(self, profiler, sample_metadata):
        chapters = [
            {'id': '1', 'word_count': 100},  # Too small
            {'id': '2', 'word_count': 5000},
        ]
        profile = profiler.profile_book(sample_metadata, chapters)
        quality = profiler.assess_quality(profile)

        assert any('under' in w.lower() for w in quality.warnings)

    def test_large_chapters_warning(self, profiler, sample_metadata):
        chapters = [
            {'id': '1', 'word_count': 25000},  # Too large
            {'id': '2', 'word_count': 5000},
        ]
        profile = profiler.profile_book(sample_metadata, chapters)
        quality = profiler.assess_quality(profile)

        assert any('over' in w.lower() for w in quality.warnings)


class TestReportGeneration:
    def test_generate_report(self, profiler, sample_metadata, sample_chapters):
        profile = profiler.profile_book(sample_metadata, sample_chapters)
        report = profiler.generate_report(profile)

        assert '## Processing Quality Report' in report
        assert 'test-book-123' in report
        assert '/100' in report
        assert 'Total Words:' in report
        assert 'Chapters Detected:' in report

    def test_report_shows_warnings(self, profiler):
        metadata = {'id': 'test-123', 'title': 'Test'}
        chapters = [{'id': '1', 'word_count': 50}]  # Tiny chapter

        profile = profiler.profile_book(metadata, chapters)
        report = profiler.generate_report(profile)

        assert '⚠️' in report  # Warning emoji

    def test_compare_profiles(self, profiler, sample_metadata, sample_chapters):
        # Create two profiles
        profile1 = profiler.profile_book(sample_metadata, sample_chapters)

        metadata2 = {**sample_metadata, 'id': 'test-book-456'}
        chapters2 = [
            {'id': '1', 'word_count': 3000},
            {'id': '2', 'word_count': 4000},
        ]
        profile2 = profiler.profile_book(metadata2, chapters2)

        comparison = profiler.compare_profiles([profile1, profile2])

        assert '## Book Comparison Report' in comparison
        assert 'Comparing 2 books' in comparison
        # IDs are truncated in the table
        assert 'test-boo' in comparison
        assert 'Summary' in comparison

    def test_compare_empty_profiles(self, profiler):
        comparison = profiler.compare_profiles([])
        assert 'No profiles to compare' in comparison
