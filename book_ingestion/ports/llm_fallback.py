"""LLM Fallback Protocol for chapter detection improvement."""

from typing import Protocol, List, Dict, Optional
from dataclasses import dataclass


@dataclass
class LLMFallbackRequest:
    """Request for LLM to improve chapter detection."""
    text_sample: str  # First N characters of the book
    detected_chapters: List[Dict]  # Current chapter detection results
    detection_confidence: float  # 0-1 confidence score
    detection_method: str  # Method used: 'toc', 'heuristic', 'semantic', etc.
    book_metadata: Dict  # Title, author, etc.


@dataclass
class LLMFallbackResponse:
    """Response from LLM with improved chapter detection."""
    improved_chapters: List[Dict]  # Corrected chapter list
    confidence_delta: float  # How much confidence improved
    corrections_made: List[str]  # Description of corrections
    should_merge: List[tuple]  # Pairs of chapters to merge: (idx1, idx2)
    should_split: List[int]  # Chapter indices that should be split


class LLMFallbackPort(Protocol):
    """
    Protocol for LLM-based fallback when chapter detection confidence is low.

    Implementations should call an LLM (Claude, GPT, etc.) to analyze the
    book text and improve chapter detection when automated methods fail.

    Example implementation:
        class ClaudeFallback:
            def __init__(self, client: Anthropic):
                self.client = client

            def improve_detection(self, request: LLMFallbackRequest) -> Optional[LLMFallbackResponse]:
                response = self.client.messages.create(
                    model="claude-sonnet-4-20250514",
                    messages=[{"role": "user", "content": self._build_prompt(request)}]
                )
                return self._parse_response(response)
    """

    def improve_detection(
        self, request: LLMFallbackRequest
    ) -> Optional[LLMFallbackResponse]:
        """
        Attempt to improve chapter detection using LLM analysis.

        Args:
            request: Context about the book and current detection results

        Returns:
            Improved detection results, or None if LLM cannot improve
        """
        ...

    def should_trigger(self, confidence: float, method: str) -> bool:
        """
        Determine if LLM fallback should be triggered.

        Args:
            confidence: Current detection confidence (0-1)
            method: Detection method used

        Returns:
            True if LLM fallback should be attempted
        """
        ...
