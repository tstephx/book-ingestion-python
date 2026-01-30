"""
Port interfaces (Protocol classes) for dependency injection.

These protocols define the contracts for external dependencies that can be
injected into the book ingestion pipeline.
"""

from book_ingestion.ports.llm_fallback import LLMFallbackPort
from book_ingestion.ports.repository import BookRepository
from book_ingestion.ports.logger import PipelineLogger

__all__ = [
    "LLMFallbackPort",
    "BookRepository",
    "PipelineLogger",
]
