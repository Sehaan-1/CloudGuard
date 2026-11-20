from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any

from cloudguard.core.config import get_settings
from cloudguard.core.models import (
    AnomalyResult,
    CloudResource,
    CostSummary,
    Recommendation,
)


class InMemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        async with self._lock:
            if key not in self._store:
                return None
            val, expiry = self._store[key]
            if expiry is not None and time.time() > expiry:
                del self._store[key]
                return None
            return val

    async def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        async with self._lock:
            expiry = time.time() + ttl if ttl is not None and ttl > 0 else None
            self._store[key] = (value, expiry)
            return True

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def exists(self, key: str) -> bool:
        val = await self.get(key)
        return val is not None

    async def clear(self, prefix: str | None = None) -> int:
        async with self._lock:
            if prefix is None:
                count = len(self._store)
                self._store.clear()
                return count
            keys_to_del = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_del:
                del self._store[k]
            return len(keys_to_del)


class CacheManager:
    def __init__(
        self,
        redis_url: str | None = None,
        default_ttl: int = 300,
        enable_redis: bool = True,
    ) -> None:
        self.redis_url = redis_url or get_settings().redis_url
        self.default_ttl = default_ttl
        self.enable_redis = enable_redis
        self._memory = InMemoryCache()
        self._redis: Any = None
        self._redis_available: bool | None = None

    async def _get_redis(self) -> Any:
        if not self.enable_redis:
            return None
        if self._redis_available is False:
            return None
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                client = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=0.5,
                    socket_timeout=0.5,
                )
                await client.ping()
                self._redis = client
                self._redis_available = True
            except Exception:
                self._redis_available = False
                self._redis = None
                return None
        return self._redis

    async def get(self, key: str) -> str | None:
        client = await self._get_redis()
        if client is not None:
            try:
                val = await client.get(key)
                if val is not None:
                    return str(val)
            except Exception:
                self._redis_available = False
        return await self._memory.get(key)

    async def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        effective_ttl = ttl if ttl is not None else self.default_ttl
        client = await self._get_redis()
        if client is not None:
            try:
                if effective_ttl > 0:
                    await client.setex(key, effective_ttl, value)
                else:
                    await client.set(key, value)
                await self._memory.set(key, value, effective_ttl)
                return True
            except Exception:
                self._redis_available = False
        return await self._memory.set(key, value, effective_ttl)

    async def get_json(self, key: str) -> Any | None:
        val = await self.get(key)
        if val is None:
            return None
        try:
            return json.loads(val)
        except Exception:
            return None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> bool:
        try:
            serialized = json.dumps(value, default=str)
            return await self.set(key, serialized, ttl)
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        client = await self._get_redis()
        if client is not None:
            try:
                await client.delete(key)
            except Exception:
                self._redis_available = False
        return await self._memory.delete(key)

    async def exists(self, key: str) -> bool:
        client = await self._get_redis()
        if client is not None:
            try:
                count = await client.exists(key)
                if count:
                    return True
            except Exception:
                self._redis_available = False
        return await self._memory.exists(key)

    async def clear(self, prefix: str | None = None) -> int:
        client = await self._get_redis()
        if client is not None:
            try:
                if prefix:
                    keys = await client.keys(f"{prefix}*")
                    if keys:
                        await client.delete(*keys)
                else:
                    await client.flushdb()
            except Exception:
                self._redis_available = False
        return await self._memory.clear(prefix)

    async def get_cost_summary(self, key: str) -> CostSummary | None:
        data = await self.get_json(key)
        if data:
            try:
                return CostSummary.model_validate(data)
            except Exception:
                return None
        return None

    async def set_cost_summary(self, key: str, summary: CostSummary, ttl: int = 300) -> bool:
        return await self.set_json(key, summary.model_dump(mode="json"), ttl=ttl)

    async def get_resources(self, key: str) -> list[CloudResource] | None:
        data = await self.get_json(key)
        if data and isinstance(data, list):
            try:
                return [CloudResource.model_validate(item) for item in data]
            except Exception:
                return None
        return None

    async def set_resources(self, key: str, resources: list[CloudResource], ttl: int = 900) -> bool:
        payload = [r.model_dump(mode="json") for r in resources]
        return await self.set_json(key, payload, ttl=ttl)

    async def get_anomalies(self, key: str) -> list[AnomalyResult] | None:
        data = await self.get_json(key)
        if data and isinstance(data, list):
            try:
                return [AnomalyResult.model_validate(item) for item in data]
            except Exception:
                return None
        return None

    async def set_anomalies(
        self, key: str, anomalies: list[AnomalyResult], ttl: int = 3600
    ) -> bool:
        payload = [a.model_dump(mode="json") for a in anomalies]
        return await self.set_json(key, payload, ttl=ttl)

    async def get_recommendations(self, key: str) -> list[Recommendation] | None:
        data = await self.get_json(key)
        if data and isinstance(data, list):
            try:
                return [Recommendation.model_validate(item) for item in data]
            except Exception:
                return None
        return None

    async def set_recommendations(
        self, key: str, recommendations: list[Recommendation], ttl: int = 1800
    ) -> bool:
        payload = [r.model_dump(mode="json") for r in recommendations]
        return await self.set_json(key, payload, ttl=ttl)

    async def close(self) -> None:
        if self._redis is not None:
            with contextlib.suppress(Exception):
                await self._redis.aclose()
            self._redis = None
            self._redis_available = None


def cached(
    ttl: int = 300,
    key_prefix: str = "",
    cache_manager: CacheManager | None = None,
) -> Callable[[Callable[..., Coroutine[Any, Any, Any]]], Callable[..., Coroutine[Any, Any, Any]]]:
    def decorator(
        func: Callable[..., Coroutine[Any, Any, Any]],
    ) -> Callable[..., Coroutine[Any, Any, Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cm = cache_manager or get_cache_manager()
            prefix = key_prefix or f"{func.__module__}.{func.__qualname__}"
            key_parts = [str(a) for a in args] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
            cache_key = f"{prefix}:{':'.join(key_parts)}"
            cached_val = await cm.get_json(cache_key)
            if cached_val is not None:
                return cached_val
            result = await func(*args, **kwargs)
            await cm.set_json(cache_key, result, ttl=ttl)
            return result

        return wrapper

    return decorator


_cache_manager: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager
