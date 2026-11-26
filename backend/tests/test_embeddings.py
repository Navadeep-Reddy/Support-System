from collections.abc import Callable

import pytest

from support_agent.core.config import Settings
from support_agent.services.embeddings import EmbeddingService


class FakeNvidiaEmbeddings:
    def __init__(self, **kwargs: object) -> None:
        self.options = kwargs
        self.embed_documents: Callable[[list[str]], list[list[float]]] = lambda _texts: [
            [0.25] * 2048
        ]
        self.embed_query: Callable[[str], list[float]] = lambda _text: [0.5] * 2048


def test_uses_configured_model_and_native_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("support_agent.services.embeddings.NVIDIAEmbeddings", FakeNvidiaEmbeddings)
    settings = Settings(
        embedding_model="nvidia/nemotron-3.5-embed-1b",
        embedding_dimensions=2048,
        nvidia_api_key="test-key",
        _env_file=None,
    )

    service = EmbeddingService(settings)

    assert service._client.options["model"] == "nvidia/nemotron-3.5-embed-1b"
    assert service._client.options["dimensions"] == 2048
    assert service._client.options["truncate"] == "NONE"
    assert service._client.options["api_key"] == "test-key"
    assert len(service.embed_passages(["article text"])[0]) == 2048
    assert len(service.embed_query("search query")) == 2048


def test_rejects_wrong_vector_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("support_agent.services.embeddings.NVIDIAEmbeddings", FakeNvidiaEmbeddings)
    service = EmbeddingService(Settings(_env_file=None))

    with pytest.raises(ValueError, match="unexpected vector size"):
        service._validate_vector([0.1])


def test_rejects_non_finite_vector_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("support_agent.services.embeddings.NVIDIAEmbeddings", FakeNvidiaEmbeddings)
    service = EmbeddingService(Settings(_env_file=None))

    with pytest.raises(ValueError, match="non-finite"):
        service._validate_vector([float("nan")] * 2048)
