"""Local BGE embedding wrapper for RAG features.

Uses FastEmbed/ONNX instead of PyTorch so local Windows development does not
depend on torch DLL loading.
"""

import asyncio
import importlib.util
from typing import Any

from app.config import settings

_model: Any | None = None


class EmbeddingServiceError(RuntimeError):
    pass


def _get_embedding_model() -> Any:
    global _model
    if _model is None:
        if importlib.util.find_spec("fastembed") is None:
            raise EmbeddingServiceError(
                "fastembed is required to generate local BGE resume embeddings. "
                "Install backend requirements and restart the server."
            )

        try:
            from fastembed import TextEmbedding
        except Exception as exc:
            raise EmbeddingServiceError(
                "FastEmbed/ONNX Runtime could not start. On Windows this usually means the current "
                "Python/native ML runtime is incompatible or a required Microsoft Visual C++ runtime "
                f"is missing. Original error: {exc}"
            ) from exc

        try:
            _model = TextEmbedding(
                model_name=settings.EMBEDDING_MODEL,
                cache_dir=settings.EMBEDDING_CACHE_DIR or None,
                threads=settings.EMBEDDING_THREADS,
            )
        except Exception as exc:
            raise EmbeddingServiceError(
                f"Failed to load embedding model {settings.EMBEDDING_MODEL}: {exc}"
            ) from exc
    return _model


async def generate_embeddings(texts: list[str]) -> list[list[float]]:
    clean_texts = [text.strip() for text in texts if text.strip()]
    if not clean_texts:
        return []

    return await asyncio.to_thread(_generate_embeddings_sync, clean_texts)


def _generate_embeddings_sync(texts: list[str]) -> list[list[float]]:
    try:
        vectors = list(_get_embedding_model().embed(texts, batch_size=settings.EMBEDDING_BATCH_SIZE))
    except Exception as exc:
        raise EmbeddingServiceError(f"Failed to generate resume embeddings: {exc}") from exc

    embeddings = [_to_float_list(vector) for vector in vectors]
    if len(embeddings) != len(texts):
        raise EmbeddingServiceError("Embedding response count did not match input count")

    for embedding in embeddings:
        if len(embedding) != settings.EMBEDDING_DIMENSIONS:
            raise EmbeddingServiceError(
                f"Embedding dimension mismatch: expected {settings.EMBEDDING_DIMENSIONS}, "
                f"got {len(embedding)}"
            )

    return embeddings


def _to_float_list(vector: Any) -> list[float]:
    if hasattr(vector, "tolist"):
        return [float(value) for value in vector.tolist()]
    return [float(value) for value in vector]
