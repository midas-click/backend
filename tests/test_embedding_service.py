import pytest

from app.services import embedding_service
from app.services.embedding_service import EmbeddingServiceError, generate_embeddings


class FakeVector:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class FakeEmbeddingModel:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def embed(self, texts, **kwargs):
        self.calls.append((texts, kwargs))
        return [FakeVector(value) for value in self.values]


@pytest.mark.asyncio
async def test_generate_embeddings_returns_bge_vectors(monkeypatch):
    model = FakeEmbeddingModel([
        [0.0, 0.0, 0.0],
        [1.0, 1.0, 1.0],
    ])
    monkeypatch.setattr(embedding_service.settings, "EMBEDDING_DIMENSIONS", 3)
    monkeypatch.setattr(embedding_service.settings, "EMBEDDING_BATCH_SIZE", 8)
    monkeypatch.setattr(embedding_service, "_get_embedding_model", lambda: model)

    embeddings = await generate_embeddings(["first", "second"])

    assert embeddings == [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]]
    assert model.calls == [(["first", "second"], {"batch_size": 8})]


@pytest.mark.asyncio
async def test_generate_embeddings_rejects_dimension_mismatch(monkeypatch):
    monkeypatch.setattr(embedding_service.settings, "EMBEDDING_DIMENSIONS", 3)
    monkeypatch.setattr(embedding_service, "_get_embedding_model", lambda: FakeEmbeddingModel([[0.0, 1.0]]))

    with pytest.raises(EmbeddingServiceError, match="dimension mismatch"):
        await generate_embeddings(["first"])


@pytest.mark.asyncio
async def test_generate_embeddings_allows_empty_inputs():
    assert await generate_embeddings([]) == []
    assert await generate_embeddings(["  "]) == []
