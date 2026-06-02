"""Simple JSON file cache for API responses."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from src.config import settings


CACHE_DIR = Path(".cache")


def make_cache_key(name: str, params: dict[str, Any]) -> str:
    """Create a stable cache key from an endpoint name and request params."""
    normalized = json.dumps(
        {"name": name, "params": params},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_cached_response(key: str) -> Any | None:
    """Return cached data when present and not expired."""
    cache_path = _cache_path(key)
    if not cache_path.exists():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        created_at = float(payload.get("created_at", 0))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None

    if time.time() - created_at > settings.cache_ttl_seconds:
        return None

    return payload.get("data")


def set_cached_response(key: str, data: Any) -> None:
    """Write response data to the local JSON cache."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": time.time(),
            "data": data,
        }
        _cache_path(key).write_text(json.dumps(payload), encoding="utf-8")
    except (OSError, TypeError):
        return


def _cache_path(key: str) -> Path:
    """Return the cache file path for a key."""
    return CACHE_DIR / f"{key}.json"
