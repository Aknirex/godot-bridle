from __future__ import annotations

from threading import get_ident

import pytest

from bridle.knowledge.chroma_store import ChromaVectorStore
from bridle.knowledge.documents import KnowledgeChunk, KnowledgeSourceType
from bridle.knowledge.embeddings import DeterministicEmbeddingProvider
from bridle.knowledge.vector_store import InMemoryVectorStore


def chunk(chunk_id: str, source_id: str, text: str, res_path: str) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=chunk_id,
        source_id=source_id,
        source_type=KnowledgeSourceType.GODOT_PROJECT,
        text=text,
        content_hash=f"hash-{chunk_id}",
        start_line=1,
        end_line=2,
        metadata={"res_path": res_path, "kind": "script"},
    )


async def test_deterministic_embedding_is_stable_and_normalized() -> None:
    provider = DeterministicEmbeddingProvider(dimensions=16)
    first, second = await provider.embed(["player movement", "player movement"])

    assert first == second
    assert len(first) == 16
    assert abs(sum(value * value for value in first) - 1.0) < 1e-9


async def test_memory_vector_store_queries_filters_and_deletes() -> None:
    provider = DeterministicEmbeddingProvider()
    chunks = [
        chunk("one", "player", "player movement speed", "res://player.gd"),
        chunk("two", "enemy", "enemy health damage", "res://enemy.gd"),
    ]
    embeddings = await provider.embed([item.text for item in chunks])
    store = InMemoryVectorStore()
    await store.upsert(chunks, embeddings)

    query = (await provider.embed(["player speed"]))[0]
    hits = await store.query(query, top_k=2)
    filtered = await store.query(query, filters={"res_path": "res://enemy.gd"})
    await store.delete_sources({"player"})
    remaining = await store.query(query, top_k=2)

    assert hits[0].source_id == "player"
    assert hits[0].citation == "res://player.gd:1-2"
    assert [hit.source_id for hit in filtered] == ["enemy"]
    assert [hit.source_id for hit in remaining] == ["enemy"]


class FakeCollection:
    def __init__(self) -> None:
        self.upserted = None
        self.deleted = []
        self.worker_threads = []

    def upsert(self, **kwargs) -> None:
        self.worker_threads.append(get_ident())
        self.upserted = kwargs

    def delete(self, **kwargs) -> None:
        self.worker_threads.append(get_ident())
        self.deleted.append(kwargs)

    def query(self, **kwargs):
        self.worker_threads.append(get_ident())
        metadata = dict(self.upserted["metadatas"][0])
        return {
            "ids": [[self.upserted["ids"][0]]],
            "documents": [[self.upserted["documents"][0]]],
            "metadatas": [[metadata]],
            "distances": [[0.1]],
        }


class FakeClient:
    def __init__(self) -> None:
        self.collection = FakeCollection()
        self.name = None

    def get_or_create_collection(self, *, name, metadata):
        self.name = name
        assert metadata == {"hnsw:space": "cosine"}
        return self.collection


async def test_chroma_adapter_round_trips_chunks_without_installed_chromadb(tmp_path) -> None:
    event_loop_thread = get_ident()
    client = FakeClient()
    store = ChromaVectorStore(tmp_path / "vectors", tmp_path / "game", client=client)
    item = chunk("one", "player", "player movement", "res://player.gd")

    await store.upsert([item], [[1.0, 0.0]])
    hits = await store.query([1.0, 0.0])
    await store.delete_sources({"player"})

    assert client.name.startswith("bridle_")
    assert hits[0].score == 0.9
    assert hits[0].citation == "res://player.gd:1-2"
    assert client.collection.deleted == [
        {"where": {"source_id": {"$in": ["player"]}}}
    ]
    assert len(client.collection.worker_threads) == 3
    assert all(thread_id != event_loop_thread for thread_id in client.collection.worker_threads)


async def test_chroma_adapter_persists_vectors_locally(tmp_path) -> None:
    pytest.importorskip("chromadb")
    storage = tmp_path / "vectors"
    project = tmp_path / "game"
    item = chunk("one", "player", "player movement", "res://player.gd")
    first = ChromaVectorStore(storage, project)
    await first.upsert([item], [[1.0, 0.0]])

    reopened = ChromaVectorStore(storage, project)
    hits = await reopened.query([1.0, 0.0])
    await reopened.delete_sources({"player"})
    empty = await reopened.query([1.0, 0.0])

    assert [hit.chunk_id for hit in hits] == ["one"]
    assert empty == []
