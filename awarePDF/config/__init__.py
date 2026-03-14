"""Configuration package for environment-aware application settings."""

from .settings import APP_TITLE, CHROMA_PERSIST_DIR, EMBEDDING_MODEL, validate_keys

__all__ = ["APP_TITLE", "CHROMA_PERSIST_DIR", "EMBEDDING_MODEL", "validate_keys"]
