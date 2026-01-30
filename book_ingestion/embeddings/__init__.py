"""
Embeddings module for generating vector embeddings from book chapters.

Lazy loads torch and sentence-transformers to avoid import overhead
when embeddings are not needed.
"""

from book_ingestion.embeddings.generator import EmbeddingGenerator

__all__ = ["EmbeddingGenerator"]
