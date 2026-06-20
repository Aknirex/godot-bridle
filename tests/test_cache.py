from __future__ import annotations

import time

import pytest

from bridle.harness.cache import ExactCache


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
