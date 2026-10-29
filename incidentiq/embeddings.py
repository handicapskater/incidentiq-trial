"""384-dimensional, normalized all-MiniLM-L6-v2 embeddings."""

from functools import lru_cache
from typing import Sequence

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME, device="cpu")
    dimension = model.get_embedding_dimension()
    if dimension != EMBEDDING_DIMENSION:
        raise ValueError(f"{MODEL_NAME} returned {dimension} dimensions, expected {EMBEDDING_DIMENSION}")
    return model


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Embed documents or queries with the same normalized model."""
    if not texts:
        return []
    vectors = _model().encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
    result = vectors.tolist()
    if any(len(vector) != EMBEDDING_DIMENSION for vector in result):
        raise ValueError("Embedding dimension mismatch")
    return result


def embed_query(query: str) -> list[float]:
    if not query.strip():
        raise ValueError("Query must not be empty")
    return embed_texts([query])[0]
