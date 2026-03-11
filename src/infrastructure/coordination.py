"""Optional distributed coordination backed by Redis."""

from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from typing import Any


def distributed_coordination_enabled() -> bool:
    return bool(os.environ.get("ONTRO_REDIS_URL", "").strip())


class RedisCoordinationProvider:
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._client: Any | None = None

    def _redis(self):
        if self._client is None:
            import redis

            self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def rate_limit(self, key: str, limit: int, window_seconds: int) -> bool:
        client = self._redis()
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_seconds)
        return int(count) <= limit

    @contextmanager
    def lock(self, key: str, ttl_seconds: int = 30):
        client = self._redis()
        token = uuid.uuid4().hex
        deadline = time.time() + ttl_seconds
        acquired = False
        while time.time() < deadline:
            acquired = bool(client.set(key, token, nx=True, ex=ttl_seconds))
            if acquired:
                break
            time.sleep(0.05)
        if not acquired:
            raise TimeoutError(f"Timed out acquiring distributed lock for {key}")
        try:
            yield
        finally:
            if client.get(key) == token:
                client.delete(key)


_provider: RedisCoordinationProvider | None = None


def get_coordination_provider() -> RedisCoordinationProvider | None:
    global _provider
    redis_url = os.environ.get("ONTRO_REDIS_URL", "").strip()
    if not redis_url:
        return None
    if _provider is None or _provider.redis_url != redis_url:
        _provider = RedisCoordinationProvider(redis_url)
    return _provider
