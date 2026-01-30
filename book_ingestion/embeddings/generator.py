"""
Embedding Generator for book chapters.

Lazy loads torch and sentence-transformers to avoid import overhead.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result from generating embeddings."""

    chapter_id: str
    embedding: List[float]
    model_name: str
    dimension: int


class EmbeddingGenerator:
    """
    Generate embeddings for book chapters using sentence-transformers.

    Lazy loads torch and sentence-transformers on first use to avoid
    heavy import overhead when embeddings are not needed.

    Usage:
        generator = EmbeddingGenerator()
        embeddings = generator.generate_for_chapters(chapters)
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: Optional[str] = None,
        cache_dir: Optional[Path] = None,
    ):
        """
        Initialize the embedding generator.

        Args:
            model_name: Name of the sentence-transformers model to use
            device: Device to run on ('cpu', 'cuda', 'mps', or None for auto)
            cache_dir: Directory to cache downloaded models
        """
        self.model_name = model_name
        self.device = device
        self.cache_dir = cache_dir
        self._model = None
        self._dimension = None

    def _get_model(self):
        """Lazy-load the sentence transformer model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise ImportError(
                    "sentence-transformers is required for embeddings. "
                    "Install it with: pip install book-ingestion[embeddings]"
                ) from e

            logger.info(f"Loading embedding model: {self.model_name}")

            kwargs: Dict[str, Any] = {}
            if self.device:
                kwargs["device"] = self.device
            if self.cache_dir:
                kwargs["cache_folder"] = str(self.cache_dir)

            self._model = SentenceTransformer(self.model_name, **kwargs)
            self._dimension = self._model.get_sentence_embedding_dimension()

            logger.info(
                f"Loaded model with dimension {self._dimension} on {self._model.device}"
            )

        return self._model

    @property
    def dimension(self) -> int:
        """Get the embedding dimension (loads model if not loaded)."""
        if self._dimension is None:
            self._get_model()
        return self._dimension

    def generate(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to generate embedding for

        Returns:
            List of floats representing the embedding
        """
        model = self._get_model()
        embedding = model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def generate_batch(
        self, texts: List[str], batch_size: int = 32, show_progress: bool = True
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to generate embeddings for
            batch_size: Number of texts to process at once
            show_progress: Whether to show a progress bar

        Returns:
            List of embeddings (each embedding is a list of floats)
        """
        model = self._get_model()
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
        )
        return [e.tolist() for e in embeddings]

    def generate_for_chapters(
        self,
        chapters: List[Dict],
        text_key: str = "content",
        id_key: str = "id",
        batch_size: int = 32,
        show_progress: bool = True,
    ) -> List[EmbeddingResult]:
        """
        Generate embeddings for a list of chapters.

        Args:
            chapters: List of chapter dictionaries
            text_key: Key in chapter dict containing the text
            id_key: Key in chapter dict containing the ID
            batch_size: Number of chapters to process at once
            show_progress: Whether to show a progress bar

        Returns:
            List of EmbeddingResult objects
        """
        texts = [ch.get(text_key, "") for ch in chapters]
        ids = [ch.get(id_key, str(i)) for i, ch in enumerate(chapters)]

        embeddings = self.generate_batch(texts, batch_size, show_progress)

        return [
            EmbeddingResult(
                chapter_id=chapter_id,
                embedding=embedding,
                model_name=self.model_name,
                dimension=len(embedding),
            )
            for chapter_id, embedding in zip(ids, embeddings)
        ]

    def similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Cosine similarity score (0-1)
        """
        try:
            import numpy as np
        except ImportError as e:
            raise ImportError(
                "numpy is required for similarity calculation. "
                "Install it with: pip install book-ingestion[embeddings]"
            ) from e

        a = np.array(embedding1)
        b = np.array(embedding2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
