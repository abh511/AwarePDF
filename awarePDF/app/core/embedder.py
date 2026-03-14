"""Sentence-transformer embedding generation for document chunks."""

from __future__ import annotations

import logging
from typing import Any

from sentence_transformers import SentenceTransformer
import config.settings as settings

logger = logging.getLogger(__name__)

_embedding_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Return singleton embedding model instance."""
    global _embedding_model
    
    if _embedding_model is None:
        model_name = settings.EMBEDDING_MODEL
        logger.info(f"Loading embedding model: {model_name}")
        _embedding_model = SentenceTransformer(model_name)
        logger.info(f"Embedding model loaded successfully")
    
    return _embedding_model


def embed_text(text: str) -> list[float]:
    """
    Generate embedding vector for a single text string.
    
    Args:
        text: Input text to embed
        
    Returns:
        List of floats representing the embedding vector
    """
    model = _get_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for multiple texts efficiently.
    
    Args:
        texts: List of text strings to embed
        
    Returns:
        List of embedding vectors
    """
    if not texts:
        return []
    
    model = _get_model()
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=len(texts) > 10)
    return embeddings.tolist()


def get_embedding_dimension() -> int:
    """Return the dimension of the embedding vectors."""
    model = _get_model()
    return model.get_sentence_embedding_dimension()
