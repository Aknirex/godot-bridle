from __future__ import annotations

import time

import pytest

from bridle.harness.cache import ExactCache, SemanticCache
from bridle.knowledge.embeddings import DeterministicEmbeddingProvider


def test_exact_cache_uses_canonical_content_hash(tmp_path) -> None:
    cache = ExactCache(tmp_path / "cache.sqlite3")
    try:
        first = cache.set({"model": "demo", "options": {"b": 2, "a": 1}}, {"answer": 3})
        second, _ = cache.hash_key({"options": {"a": 1, "b": 2}, "model": "demo"})

        hit = cache.get({"options": {"a": 1, "b": 2}, "model": "demo"})
        assert first == second
        assert hit is not None
        assert hit.value == {"answer": 3}
    finally:
        cache.close()


def test_exact_cache_expires_entries(tmp_path) -> None:
    cache = ExactCache(tmp_path / "cache.sqlite3")
    try:
        cache.set("short", "value", ttl_seconds=0.01)
        time.sleep(0.02)
        assert cache.get("short") is None
        with pytest.raises(ValueError):
            cache.set("bad", "value", ttl_seconds=0)
    finally:
        cache.close()


def test_exact_cache_evicts_least_recently_used_entry(tmp_path) -> None:
    cache = ExactCache(tmp_path / "cache.sqlite3", max_entries=2)
    try:
        cache.set("first", 1)
        cache.set("second", 2)
        assert cache.get("first") is not None
        cache.set("third", 3)

        assert cache.get("first") is not None
        assert cache.get("second") is None
        assert cache.get("third") is not None
    finally:
        cache.close()


async def test_semantic_cache_matches_similar_prompt_and_isolates_model(tmp_path) -> None:
    first_provider = DeterministicEmbeddingProvider(dimensions=64)
    cache = SemanticCache(tmp_path / "semantic.sqlite3", first_provider, threshold=0.5)
    try:
        await cache.set("chat:model-a", "player movement speed", {"answer": 10})
        hit = await cache.get("chat:model-a", "movement speed player")
        miss = await cache.get("chat:model-b", "movement speed player")

        assert hit is not None
        assert hit.value == {"answer": 10}
        assert miss is None
    finally:
        cache.close()
