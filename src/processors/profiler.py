"""Data profiling for processed books"""

import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BookProfile:
    """Statistical profile of a processed book"""
    book_id: str
    total_words: int
    total_chapters: int
    avg_chapter_words: float
    chapter_word_variance: float
    min_chapter_words: int
    max_chapter_words: int
    estimated_tokens: int
    metadata_completeness: float  # 0-1 score
    encoding_issues: int
    chapters_under_threshold: int   # Chapters < 500 words
    chapters_over_threshold: int    # Chapters > 20000 words

    # Optional detailed stats
    chapter_word_counts: List[int] = field(default_factory=list)


@dataclass
class QualityReport:
    """Quality assessment report for a processed book"""
    profile: BookProfile
    quality_score: int  # 0-100
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)


class DataProfiler:
    """Profile and assess quality of processed books"""

    # Thresholds for chapter size warnings
    MIN_CHAPTER_WORDS = 500
    MAX_CHAPTER_WORDS = 20000

    # Weights for quality score calculation
    SCORE_WEIGHTS = {
        'metadata_completeness': 20,
        'chapter_balance': 30,
        'chapter_count': 20,
        'encoding_quality': 15,
        'chapter_size_distribution': 15,
    }

    # Required and optional metadata fields
    REQUIRED_METADATA = ['id', 'title']
    OPTIONAL_METADATA = ['author', 'word_count', 'source_file']

    def profile_book(self, metadata: Dict, chapters: List[Dict],
                     encoding_issues: int = 0) -> BookProfile:
        """
        Generate a statistical profile for a processed book.

        Args:
            metadata: Book metadata dictionary
            chapters: List of chapter dictionaries
            encoding_issues: Number of encoding issues found during cleaning

        Returns:
            BookProfile with comprehensive statistics
        """
        word_counts = [c.get('word_count', 0) for c in chapters]

        # Handle edge cases
        if not word_counts:
            return BookProfile(
                book_id=metadata.get('id', 'unknown'),
                total_words=0,
                total_chapters=0,
                avg_chapter_words=0,
                chapter_word_variance=0,
                min_chapter_words=0,
                max_chapter_words=0,
                estimated_tokens=0,
                metadata_completeness=self._calculate_completeness(metadata),
                encoding_issues=encoding_issues,
                chapters_under_threshold=0,
                chapters_over_threshold=0,
                chapter_word_counts=[]
            )

        total_words = sum(word_counts)
        avg_words = statistics.mean(word_counts)
        variance = statistics.variance(word_counts) if len(word_counts) > 1 else 0

        return BookProfile(
            book_id=metadata.get('id', 'unknown'),
            total_words=total_words,
            total_chapters=len(chapters),
            avg_chapter_words=avg_words,
            chapter_word_variance=variance,
            min_chapter_words=min(word_counts),
            max_chapter_words=max(word_counts),
            estimated_tokens=int(total_words / 0.75),  # ~1.33 tokens/word
            metadata_completeness=self._calculate_completeness(metadata),
            encoding_issues=encoding_issues,
            chapters_under_threshold=sum(1 for w in word_counts if w < self.MIN_CHAPTER_WORDS),
            chapters_over_threshold=sum(1 for w in word_counts if w > self.MAX_CHAPTER_WORDS),
            chapter_word_counts=word_counts
        )

    def _calculate_completeness(self, metadata: Dict) -> float:
        """Calculate metadata completeness score (0-1)"""
        if not metadata:
            return 0.0

        total_fields = len(self.REQUIRED_METADATA) + len(self.OPTIONAL_METADATA)
        present_fields = 0

        # Required fields count more
        for field in self.REQUIRED_METADATA:
            if metadata.get(field):
                present_fields += 1.5  # Weight required fields higher

        for field in self.OPTIONAL_METADATA:
            if metadata.get(field):
                present_fields += 1

        # Normalize to 0-1
        max_score = len(self.REQUIRED_METADATA) * 1.5 + len(self.OPTIONAL_METADATA)
        return min(1.0, present_fields / max_score)

    def assess_quality(self, profile: BookProfile) -> QualityReport:
        """
        Assess the quality of a processed book.

        Args:
            profile: BookProfile to assess

        Returns:
            QualityReport with score and warnings
        """
        warnings = []
        info = []
        scores = {}

        # 1. Metadata completeness (20 points)
        scores['metadata_completeness'] = profile.metadata_completeness * self.SCORE_WEIGHTS['metadata_completeness']
        if profile.metadata_completeness < 0.5:
            warnings.append("Incomplete metadata - missing required fields")
        elif profile.metadata_completeness < 0.8:
            info.append("Some optional metadata fields are missing")

        # 2. Chapter balance (30 points) - based on variance
        if profile.total_chapters > 0:
            # Lower variance = more balanced = higher score
            cv = (profile.chapter_word_variance ** 0.5) / max(profile.avg_chapter_words, 1)  # Coefficient of variation
            balance_score = max(0, 1 - cv) * self.SCORE_WEIGHTS['chapter_balance']
            scores['chapter_balance'] = balance_score

            if cv > 1.0:
                warnings.append(f"High chapter size variance (CV={cv:.2f}) - chapters are very uneven")
            elif cv > 0.5:
                info.append(f"Moderate chapter size variance (CV={cv:.2f})")
        else:
            scores['chapter_balance'] = 0
            warnings.append("No chapters detected")

        # 3. Chapter count (20 points)
        if profile.total_chapters == 0:
            scores['chapter_count'] = 0
        elif profile.total_chapters == 1:
            scores['chapter_count'] = 5
            warnings.append("Only 1 chapter detected - may indicate detection issues")
        elif 3 <= profile.total_chapters <= 50:
            scores['chapter_count'] = self.SCORE_WEIGHTS['chapter_count']
        elif profile.total_chapters > 50:
            scores['chapter_count'] = 15
            info.append(f"Large number of chapters ({profile.total_chapters})")
        else:
            scores['chapter_count'] = 10
            info.append(f"Small number of chapters ({profile.total_chapters})")

        # 4. Encoding quality (15 points)
        if profile.encoding_issues == 0:
            scores['encoding_quality'] = self.SCORE_WEIGHTS['encoding_quality']
        elif profile.encoding_issues < 10:
            scores['encoding_quality'] = 10
            info.append(f"Minor encoding issues detected ({profile.encoding_issues})")
        else:
            scores['encoding_quality'] = max(0, 15 - profile.encoding_issues)
            warnings.append(f"Significant encoding issues ({profile.encoding_issues})")

        # 5. Chapter size distribution (15 points)
        if profile.total_chapters > 0:
            problematic_chapters = profile.chapters_under_threshold + profile.chapters_over_threshold
            problem_ratio = problematic_chapters / profile.total_chapters
            scores['chapter_size_distribution'] = (1 - problem_ratio) * self.SCORE_WEIGHTS['chapter_size_distribution']

            if profile.chapters_under_threshold > 0:
                warnings.append(f"{profile.chapters_under_threshold} chapter(s) under {self.MIN_CHAPTER_WORDS} words")
            if profile.chapters_over_threshold > 0:
                warnings.append(f"{profile.chapters_over_threshold} chapter(s) over {self.MAX_CHAPTER_WORDS} words")
        else:
            scores['chapter_size_distribution'] = 0

        # Calculate total score
        quality_score = int(sum(scores.values()))

        return QualityReport(
            profile=profile,
            quality_score=quality_score,
            warnings=warnings,
            info=info
        )

    def generate_report(self, profile: BookProfile) -> str:
        """
        Generate a human-readable quality report.

        Args:
            profile: BookProfile to report on

        Returns:
            Formatted markdown report string
        """
        quality = self.assess_quality(profile)

        # Determine quality level label
        if quality.quality_score >= 90:
            quality_label = "Excellent"
        elif quality.quality_score >= 75:
            quality_label = "Good"
        elif quality.quality_score >= 50:
            quality_label = "Fair"
        else:
            quality_label = "Poor"

        report = f"""## Processing Quality Report

**Book ID:** {profile.book_id}
**Quality Score:** {quality.quality_score}/100 ({quality_label})

### Statistics
- Total Words: {profile.total_words:,}
- Chapters Detected: {profile.total_chapters}
- Avg Chapter Size: {profile.avg_chapter_words:,.0f} words
- Min Chapter Size: {profile.min_chapter_words:,} words
- Max Chapter Size: {profile.max_chapter_words:,} words
- Estimated Tokens: {profile.estimated_tokens:,}
- Metadata Completeness: {profile.metadata_completeness:.0%}

### Warnings
{self._format_issues(quality.warnings, 'warning') or 'None'}

### Info
{self._format_issues(quality.info, 'info') or 'None'}
"""
        return report.strip()

    def _format_issues(self, issues: List[str], issue_type: str) -> str:
        """Format a list of issues for the report"""
        if not issues:
            return ""
        emoji = "⚠️" if issue_type == "warning" else "ℹ️"
        return "\n".join(f"{emoji} {issue}" for issue in issues)

    def compare_profiles(self, profiles: List[BookProfile]) -> str:
        """
        Generate a comparison report for multiple books.

        Args:
            profiles: List of BookProfiles to compare

        Returns:
            Formatted comparison report
        """
        if not profiles:
            return "No profiles to compare."

        report = ["## Book Comparison Report\n"]
        report.append(f"Comparing {len(profiles)} books\n")
        report.append("| Book ID | Chapters | Words | Avg Chapter | Score |")
        report.append("|---------|----------|-------|-------------|-------|")

        for profile in profiles:
            quality = self.assess_quality(profile)
            short_id = profile.book_id[:8] + "..."
            report.append(
                f"| {short_id} | {profile.total_chapters} | "
                f"{profile.total_words:,} | {profile.avg_chapter_words:,.0f} | "
                f"{quality.quality_score}/100 |"
            )

        # Summary statistics
        avg_score = sum(self.assess_quality(p).quality_score for p in profiles) / len(profiles)
        total_words = sum(p.total_words for p in profiles)
        total_chapters = sum(p.total_chapters for p in profiles)

        report.append(f"\n### Summary")
        report.append(f"- Total Books: {len(profiles)}")
        report.append(f"- Total Words: {total_words:,}")
        report.append(f"- Total Chapters: {total_chapters}")
        report.append(f"- Average Quality Score: {avg_score:.1f}/100")

        return "\n".join(report)
