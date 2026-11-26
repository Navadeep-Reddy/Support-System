from math import isfinite

from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
from langsmith import traceable

from support_agent.core.config import Settings, get_settings


class EmbeddingService:
    """NVIDIA hosted embeddings with explicit retrieval modes and vector validation."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = NVIDIAEmbeddings(
            model=self._settings.embedding_model,
            base_url=self._settings.nvidia_base_url,
            api_key=self._settings.nvidia_api_key.get_secret_value() or None,
            dimensions=self._settings.embedding_dimensions,
            # Reject oversized content rather than silently indexing truncated text.
            truncate="NONE",
        )

    @traceable(name="nvidia_embed_passages", run_type="embedding")
    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        vectors = self._client.embed_documents(texts)
        return [self._validate_vector(vector) for vector in vectors]

    @traceable(name="nvidia_embed_query", run_type="embedding")
    def embed_query(self, text: str) -> list[float]:
        return self._validate_vector(self._client.embed_query(text))

    def _validate_vector(self, vector: list[float]) -> list[float]:
        if len(vector) != self._settings.embedding_dimensions:
            raise ValueError(
                "NVIDIA embedding returned an unexpected vector size: "
                f"expected {self._settings.embedding_dimensions}, got {len(vector)}"
            )
        if not all(isfinite(value) for value in vector):
            raise ValueError("NVIDIA embedding returned a non-finite vector value")
        return vector
