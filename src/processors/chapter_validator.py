"""Chapter validation and quality checks"""

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ValidationResult:
    """Result of chapter validation"""
    is_valid: bool
    warnings: List[str]
    errors: List[str]
    expected_chapters: Optional[int] = None
    actual_chapters: Optional[int] = None

    def has_issues(self) -> bool:
        return len(self.warnings) > 0 or len(self.errors) > 0


class ChapterValidator:
    """Validates chapter detection quality"""

    # Thresholds for validation
    MIN_WORDS_PER_CHAPTER = 500
    MAX_WORDS_PER_CHAPTER = 30000
    MIN_CHAPTERS_PER_100K_WORDS = 3
    MAX_CHAPTER_SIZE_RATIO = 5  # Largest chapter shouldn't be 5x the median

    def __init__(self):
        # Patterns for detecting TOC entries
        self.toc_patterns = [
            re.compile(r'^Chapter\s+(\d+)[,:]\s+', re.IGNORECASE),
            re.compile(r'^Project\s+(\d+[A-Z]):', re.IGNORECASE),
            re.compile(r'^Lesson\s+(\d+)', re.IGNORECASE),
            re.compile(r'^Module\s+(\d+)', re.IGNORECASE),
            re.compile(r'^Part\s+(\d+)', re.IGNORECASE),
            re.compile(r'^Unit\s+(\d+)', re.IGNORECASE),
        ]

    def validate(self, text: str, chapters: List[dict], book_word_count: int) -> ValidationResult:
        """
        Validate chapter detection results.

        Args:
            text: Original book text
            chapters: List of detected chapters
            book_word_count: Total word count of book

        Returns:
            ValidationResult with any warnings/errors
        """
        warnings = []
        errors = []

        # Count expected chapters from TOC
        expected_count = self._count_toc_chapters(text)
        actual_count = len(chapters)

        # Check 1: Compare against TOC
        if expected_count and expected_count > 0:
            if actual_count < expected_count:
                diff = expected_count - actual_count
                if diff == 1:
                    warnings.append(f"Missing 1 chapter (expected {expected_count}, found {actual_count})")
                elif diff <= 3:
                    warnings.append(f"Missing {diff} chapters (expected {expected_count}, found {actual_count})")
                else:
                    errors.append(f"Missing {diff} chapters (expected {expected_count}, found {actual_count})")

        # Check 2: Minimum chapters for book size
        if book_word_count > 50000:
            expected_min = max(3, book_word_count // 20000)  # ~1 chapter per 20k words
            if actual_count < expected_min:
                warnings.append(
                    f"Only {actual_count} chapters for {book_word_count:,} words "
                    f"(expected at least {expected_min})"
                )

        # Check 3: Individual chapter sizes
        if chapters:
            word_counts = [ch.get('word_count', 0) for ch in chapters]

            # Check for oversized chapters
            for i, wc in enumerate(word_counts):
                if wc > self.MAX_WORDS_PER_CHAPTER:
                    warnings.append(
                        f"Chapter {i+1} is very large ({wc:,} words) - may contain missed splits"
                    )

            # Check for undersized chapters
            tiny_chapters = [i+1 for i, wc in enumerate(word_counts) if wc < 100]
            if tiny_chapters:
                warnings.append(f"Very small chapters detected: {tiny_chapters}")

            # Check for size imbalance
            if len(word_counts) >= 3:
                sorted_counts = sorted(word_counts)
                median = sorted_counts[len(sorted_counts) // 2]
                largest = max(word_counts)

                if median > 0 and largest / median > self.MAX_CHAPTER_SIZE_RATIO:
                    largest_idx = word_counts.index(largest) + 1
                    warnings.append(
                        f"Chapter {largest_idx} is {largest/median:.1f}x larger than median - "
                        f"may contain missed splits"
                    )

        # Check 4: Fixed-size splitting detection
        if chapters:
            titles = [ch.get('title', '') for ch in chapters]
            section_pattern = sum(1 for t in titles if re.match(r'^Section\s+\d+$', t))
            if section_pattern > 0 and section_pattern == len(titles):
                errors.append(
                    "All chapters are generic 'Section N' - pattern-based detection failed, "
                    "fell back to fixed-size splitting"
                )

        is_valid = len(errors) == 0

        return ValidationResult(
            is_valid=is_valid,
            warnings=warnings,
            errors=errors,
            expected_chapters=expected_count,
            actual_chapters=actual_count
        )

    def _count_toc_chapters(self, text: str) -> Optional[int]:
        """Count chapters mentioned in TOC"""
        lines = text.split('\n')[:500]  # Only check first 500 lines

        chapter_numbers = set()

        for line in lines:
            line_stripped = line.strip()
            for pattern in self.toc_patterns:
                match = pattern.match(line_stripped)
                if match:
                    chapter_numbers.add(match.group(1))
                    break

        return len(chapter_numbers) if chapter_numbers else None

    def get_recommendations(self, result: ValidationResult) -> List[str]:
        """Get recommendations for fixing issues"""
        recommendations = []

        if result.expected_chapters and result.actual_chapters:
            if result.actual_chapters < result.expected_chapters:
                recommendations.append(
                    "Try reprocessing with --debug to see which chapters are being missed"
                )
                recommendations.append(
                    "Check if chapter titles in body differ from TOC titles"
                )

        for warning in result.warnings:
            if "very large" in warning.lower():
                recommendations.append(
                    "Large chapters may indicate missed chapter headers - "
                    "check chapter patterns in config.json"
                )
            if "fixed-size splitting" in warning.lower():
                recommendations.append(
                    "Add appropriate chapter patterns for this book's format to config.json"
                )

        return recommendations


def validate_book_chapters(text: str, chapters: List[dict]) -> ValidationResult:
    """Convenience function to validate chapters"""
    word_count = len(text.split())
    validator = ChapterValidator()
    return validator.validate(text, chapters, word_count)
