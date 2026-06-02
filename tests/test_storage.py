"""Tests for the local JSON cache helpers."""

from pathlib import Path

from src import storage


def test_make_cache_key_is_stable() -> None:
    """Cache keys should not depend on parameter order."""
    first_key = storage.make_cache_key("endpoint", {"b": 2, "a": 1})
    second_key = storage.make_cache_key("endpoint", {"a": 1, "b": 2})

    assert first_key == second_key


def test_set_and_get_cached_response(tmp_path: Path, monkeypatch) -> None:
    """Cached data should round-trip through the local JSON cache."""
    monkeypatch.setattr(storage, "CACHE_DIR", tmp_path)
    cache_key = storage.make_cache_key("simple_price", {"ids": "bitcoin"})
    data = {"bitcoin": {"usd": 50000}}

    storage.set_cached_response(cache_key, data)

    assert storage.get_cached_response(cache_key) == data
