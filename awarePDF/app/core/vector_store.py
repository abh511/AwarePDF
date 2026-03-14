"""ChromaDB operations for persistent vector indexing and lookup."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import chromadb
from chromadb.utils import embedding_functions
import config.settings as settings

if TYPE_CHECKING:
	from chromadb.api.models.Collection import Collection


logger = logging.getLogger(__name__)

_client: chromadb.PersistentClient | None = None
_embedding_fn: Any | None = None


def _get_chroma_dir() -> Path:
	"""Resolve Chroma persistence directory from runtime settings."""
	return Path(settings.CHROMA_PERSIST_DIR)


def _get_embedding_model_name() -> str:
	"""Resolve embedding model name from runtime settings."""
	return settings.EMBEDDING_MODEL


def _ensure_storage_path() -> None:
	"""Create the persistent ChromaDB storage directory if it does not exist."""
	_get_chroma_dir().mkdir(parents=True, exist_ok=True)


def _get_client() -> chromadb.PersistentClient:
	"""Return a singleton ChromaDB persistent client."""
	global _client

	if _client is None:
		_ensure_storage_path()
		try:
			chroma_dir = _get_chroma_dir()
			_client = chromadb.PersistentClient(path=str(chroma_dir))
			logger.info("Initialized ChromaDB client at %s", chroma_dir)
		except Exception:
			logger.exception("Failed to initialize ChromaDB client.")
			raise

	return _client


def _get_embedding_function() -> Any:
	"""Return a singleton sentence-transformers embedding function for ChromaDB."""
	global _embedding_fn

	if _embedding_fn is None:
		try:
			model_name = _get_embedding_model_name()
			_embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
				model_name=model_name
			)
			logger.info("Loaded embedding model: %s", model_name)
		except Exception:
			logger.exception("Failed to load embedding model: %s", _get_embedding_model_name())
			raise

	return _embedding_fn


def _build_collection_name(pdf_hash: str) -> str:
	"""Build a deterministic collection name from a PDF hash."""
	cleaned_hash = pdf_hash.strip()
	if not cleaned_hash:
		raise ValueError("pdf_hash must be a non-empty string")
	return cleaned_hash


def _prepare_metadata(chunk: dict) -> dict:
	"""Normalize and filter metadata fields before writing to ChromaDB."""
	source_meta = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}

	metadata = {
		"page_number": source_meta.get("page_number", chunk.get("page_number")),
		"chunk_index": source_meta.get("chunk_index", chunk.get("chunk_index")),
		"content_type": source_meta.get("content_type", chunk.get("content_type", "text")),
		"section_heading": source_meta.get("section_heading", chunk.get("section_heading")),
		"pdf_filename": source_meta.get("pdf_filename", chunk.get("pdf_filename")),
	}

	# Chroma metadata values must be primitive scalars; drop missing values.
	cleaned: dict[str, Any] = {}
	for key, value in metadata.items():
		if value is None:
			continue
		if isinstance(value, (str, int, float, bool)):
			cleaned[key] = value
		else:
			cleaned[key] = str(value)

	return cleaned


def create_or_get_collection(pdf_hash: str) -> Collection:
	"""Create or fetch the ChromaDB collection for a PDF hash.

	Args:
		pdf_hash: Stable hash for a PDF document.

	Returns:
		The ChromaDB collection associated with the hash.
	"""
	try:
		client = _get_client()
		name = _build_collection_name(pdf_hash)
		collection = client.get_or_create_collection(
			name=name,
			embedding_function=_get_embedding_function(),
			metadata={"pdf_hash": pdf_hash},
		)
		logger.info("Collection ready: %s", name)
		return collection
	except Exception:
		logger.exception("Unable to create/get collection for hash: %s", pdf_hash)
		raise


def initialize_vector_store(warmup_embeddings: bool = False) -> dict[str, Any]:
	"""Initialize ChromaDB persistence and optionally warm up embeddings.

	Args:
		warmup_embeddings: When True, loads the embedding model during initialization.

	Returns:
		Diagnostic payload describing readiness and active configuration.
	"""
	try:
		client = _get_client()
		if warmup_embeddings:
			_get_embedding_function()

		return {
			"ready": True,
			"persist_directory": str(_get_chroma_dir()),
			"embedding_model": _get_embedding_model_name(),
			"collection_count": len(client.list_collections()),
			"embedding_warmed": warmup_embeddings,
		}
	except Exception as exc:
		logger.exception("Vector store initialization failed.")
		return {
			"ready": False,
			"persist_directory": str(_get_chroma_dir()),
			"embedding_model": _get_embedding_model_name(),
			"error": str(exc),
			"embedding_warmed": warmup_embeddings,
		}


def add_documents(collection: Collection, chunks: list[dict]) -> None:
	"""Add chunked PDF content into an existing collection.

	Args:
		collection: Target ChromaDB collection.
		chunks: List of chunk dictionaries with keys `text` and `metadata`.

	Raises:
		ValueError: If collection is missing.
	"""
	if collection is None:
		raise ValueError("collection must not be None")

	if not chunks:
		logger.warning("No chunks provided for collection '%s'.", collection.name)
		return

	try:
		documents: list[str] = []
		metadatas: list[dict] = []
		ids: list[str] = []

		for idx, chunk in enumerate(chunks):
			text = chunk.get("text")
			if not isinstance(text, str) or not text.strip():
				logger.debug("Skipping empty chunk at index %s", idx)
				continue

			metadata = _prepare_metadata(chunk)
			chunk_index = metadata.get("chunk_index", idx)
			page_number = metadata.get("page_number", 0)
			chunk_id = f"{collection.name}_{page_number}_{chunk_index}_{uuid4().hex[:8]}"

			documents.append(text)
			metadatas.append(metadata)
			ids.append(chunk_id)

		if not documents:
			logger.warning("No valid chunks to add for collection '%s'.", collection.name)
			return

		collection.add(documents=documents, metadatas=metadatas, ids=ids)
		logger.info("Added %s chunks to collection '%s'.", len(documents), collection.name)
	except Exception:
		logger.exception("Failed to add documents to collection '%s'.", collection.name)
		raise


def similarity_search(collection: Collection, query: str, k: int = 5) -> list[dict]:
	"""Run semantic similarity search for a query against a collection.

	Args:
		collection: ChromaDB collection to query.
		query: Natural language search query.
		k: Maximum number of results to return.

	Returns:
		List of dictionaries containing `id`, `text`, `metadata`, and `distance`.
	"""
	if collection is None:
		raise ValueError("collection must not be None")
	if not isinstance(query, str) or not query.strip():
		logger.warning("Empty query passed to similarity_search for '%s'.", collection.name)
		return []

	result_count = max(1, int(k))

	try:
		results = collection.query(
			query_texts=[query],
			n_results=result_count,
			include=["documents", "metadatas", "distances"],
		)

		ids = results.get("ids", [[]])[0]
		documents = results.get("documents", [[]])[0]
		metadatas = results.get("metadatas", [[]])[0]
		distances = results.get("distances", [[]])[0]

		payload: list[dict] = []
		for idx, text in enumerate(documents):
			payload.append(
				{
					"id": ids[idx] if idx < len(ids) else None,
					"text": text,
					"metadata": metadatas[idx] if idx < len(metadatas) else {},
					"distance": distances[idx] if idx < len(distances) else None,
				}
			)

		logger.info(
			"Similarity search on '%s' returned %s results.",
			collection.name,
			len(payload),
		)
		return payload
	except Exception:
		logger.exception("Similarity search failed for collection '%s'.", collection.name)
		raise


def collection_exists(pdf_hash: str) -> bool:
	"""Check whether a collection exists for the given PDF hash.

	Args:
		pdf_hash: Stable hash for a PDF document.

	Returns:
		True if the collection exists, otherwise False.
	"""
	name = _build_collection_name(pdf_hash)
	try:
		client = _get_client()
		client.get_collection(name=name, embedding_function=_get_embedding_function())
		return True
	except Exception as exc:
		message = str(exc).lower()
		if "not found" in message or "does not exist" in message:
			return False
		logger.exception("Error while checking collection existence for '%s'.", name)
		raise


def delete_collection(pdf_hash: str) -> None:
	"""Delete a PDF hash collection from ChromaDB.

	Args:
		pdf_hash: Stable hash for a PDF document.
	"""
	name = _build_collection_name(pdf_hash)

	try:
		client = _get_client()
		if not collection_exists(pdf_hash):
			logger.info("Collection '%s' does not exist. Nothing to delete.", name)
			return

		client.delete_collection(name=name)
		logger.info("Deleted collection '%s'.", name)
	except Exception:
		logger.exception("Failed to delete collection '%s'.", name)
		raise


def get_collection_stats(pdf_hash: str) -> dict:
	"""Return basic statistics about a PDF hash collection.

	Args:
		pdf_hash: Stable hash for a PDF document.

	Returns:
		Dictionary with existence flag, collection name, vector count, and storage path.
	"""
	name = _build_collection_name(pdf_hash)

	try:
		if not collection_exists(pdf_hash):
			return {
				"exists": False,
				"collection_name": name,
				"count": 0,
				"chunk_count": 0,
				"persist_directory": str(_get_chroma_dir()),
			}

		collection = create_or_get_collection(pdf_hash)
		count = collection.count()
		return {
			"exists": True,
			"collection_name": name,
			"count": count,
			"chunk_count": count,
			"persist_directory": str(_get_chroma_dir()),
			"metadata": collection.metadata or {},
		}
	except Exception:
		logger.exception("Failed to fetch stats for collection '%s'.", name)
		raise


def reset_runtime_state() -> None:
	"""Reset cached singleton resources (useful for tests)."""
	global _client
	global _embedding_fn
	_client = None
	_embedding_fn = None
