from __future__ import annotations

import asyncio
import datetime as dt

import pytest

from cloudguard.core.models import (
    AnomalyResult,
    CloudProviderType,
    CloudResource,
    CostSummary,
    Recommendation,
    RecommendationPriority,
    RecommendationStatus,
    ResourceStatus,
    ResourceType,
    Severity,
)
from cloudguard.data.cache import (
    CacheManager,
    InMemoryCache,
    cached,
    get_cache_manager,
)


@pytest.mark.asyncio
async def test_in_memory_cache_basic_ops():
    cache = InMemoryCache()
    assert await cache.get("key1") is None
    assert await cache.exists("key1") is False

    await cache.set("key1", "val1", ttl=60)
    assert await cache.get("key1") == "val1"
    assert await cache.exists("key1") is True

    deleted = await cache.delete("key1")
    assert deleted is True
    assert await cache.get("key1") is None
    assert await cache.exists("key1") is False


@pytest.mark.asyncio
async def test_in_memory_cache_ttl_expiration():
    cache = InMemoryCache()
    await cache.set("temp_key", "temp_val", ttl=1)
    assert await cache.get("temp_key") == "temp_val"

    await asyncio.sleep(1.1)
    assert await cache.get("temp_key") is None
    assert await cache.exists("temp_key") is False


@pytest.mark.asyncio
async def test_in_memory_cache_clear_and_prefix():
    cache = InMemoryCache()
    await cache.set("user:1", "alice")
    await cache.set("user:2", "bob")
    await cache.set("item:1", "sword")

    cleared_users = await cache.clear("user:")
    assert cleared_users == 2
    assert await cache.get("user:1") is None
    assert await cache.get("item:1") == "sword"

    cleared_all = await cache.clear()
    assert cleared_all == 1
    assert await cache.get("item:1") is None


@pytest.mark.asyncio
async def test_cache_manager_json_and_fallback():
    cm = CacheManager(redis_url="redis://localhost:9999/0", enable_redis=False)
    data = {"name": "cloudguard", "version": 1}
    assert await cm.set_json("app:info", data, ttl=100) is True
    retrieved = await cm.get_json("app:info")
    assert retrieved == data

    assert await cm.exists("app:info") is True
    assert await cm.delete("app:info") is True
    assert await cm.get_json("app:info") is None


@pytest.mark.asyncio
async def test_cache_manager_domain_entities():
    cm = CacheManager(enable_redis=False)

    summary = CostSummary(
        total_cost=250.0,
        period_start=dt.date(2026, 8, 1),
        period_end=dt.date(2026, 8, 10),
    )
    await cm.set_cost_summary("costs:summary:latest", summary, ttl=300)
    cached_summary = await cm.get_cost_summary("costs:summary:latest")
    assert cached_summary is not None
    assert cached_summary.total_cost == 250.0

    resources = [
        CloudResource(
            id="vm-01",
            name="web-01",
            type=ResourceType.VM,
            provider=CloudProviderType.MOCK,
            monthly_cost=80.0,
            status=ResourceStatus.RUNNING,
        )
    ]
    await cm.set_resources("resources:all", resources, ttl=900)
    cached_res = await cm.get_resources("resources:all")
    assert cached_res is not None
    assert len(cached_res) == 1
    assert cached_res[0].id == "vm-01"

    anomalies = [
        AnomalyResult(
            id="anom-test",
            service="VM",
            date=dt.date(2026, 8, 5),
            expected_cost=10.0,
            actual_cost=50.0,
            severity=Severity.HIGH,
        )
    ]
    await cm.set_anomalies("anomalies:latest", anomalies, ttl=3600)
    cached_anoms = await cm.get_anomalies("anomalies:latest")
    assert cached_anoms is not None
    assert len(cached_anoms) == 1
    assert cached_anoms[0].id == "anom-test"

    recs = [
        Recommendation(
            id="rec-test",
            resource_id="vm-01",
            action="resize",
            title="Rightsize VM",
            description="Reduce VM size",
            estimated_savings=30.0,
            priority=RecommendationPriority.MEDIUM,
            status=RecommendationStatus.OPEN,
        )
    ]
    await cm.set_recommendations("recs:latest", recs, ttl=1800)
    cached_recs = await cm.get_recommendations("recs:latest")
    assert cached_recs is not None
    assert len(cached_recs) == 1
    assert cached_recs[0].id == "rec-test"

    await cm.close()


@pytest.mark.asyncio
async def test_cached_decorator():
    cm = CacheManager(enable_redis=False)
    call_count = 0

    @cached(ttl=60, key_prefix="test_fn", cache_manager=cm)
    async def compute_heavy_task(val: int) -> dict[str, int]:
        nonlocal call_count
        call_count += 1
        return {"result": val * 2}

    res1 = await compute_heavy_task(5)
    assert res1 == {"result": 10}
    assert call_count == 1

    res2 = await compute_heavy_task(5)
    assert res2 == {"result": 10}
    assert call_count == 1

    res3 = await compute_heavy_task(10)
    assert res3 == {"result": 20}
    assert call_count == 2


@pytest.mark.asyncio
async def test_singleton_cache_manager():
    cm1 = get_cache_manager()
    cm2 = get_cache_manager()
    assert cm1 is cm2


@pytest.mark.asyncio
async def test_cache_manager_with_mocked_redis():
    from unittest.mock import AsyncMock

    mock_client = AsyncMock()
    mock_client.ping.return_value = True
    mock_client.get.return_value = "redis_val"
    mock_client.set.return_value = True
    mock_client.setex.return_value = True
    mock_client.delete.return_value = True
    mock_client.exists.return_value = 1
    mock_client.keys.return_value = ["pre:1", "pre:2"]
    mock_client.flushdb.return_value = True
    mock_client.aclose.return_value = None

    cm = CacheManager(redis_url="redis://fake:6379/0", enable_redis=True)
    cm._redis = mock_client
    cm._redis_available = True

    assert await cm.get("key1") == "redis_val"
    assert await cm.set("key1", "val1", ttl=60) is True
    assert await cm.set("key2", "val2", ttl=0) is True
    assert await cm.exists("key1") is True
    assert await cm.delete("key1") is True
    assert await cm.clear(prefix="pre:") >= 0
    assert await cm.clear() >= 0
    await cm.close()


@pytest.mark.asyncio
async def test_cache_manager_redis_error_fallback():
    from unittest.mock import AsyncMock

    failing_client = AsyncMock()
    failing_client.get.side_effect = ConnectionError("Redis is down")
    failing_client.setex.side_effect = ConnectionError("Redis is down")
    failing_client.delete.side_effect = ConnectionError("Redis is down")
    failing_client.exists.side_effect = ConnectionError("Redis is down")
    failing_client.keys.side_effect = ConnectionError("Redis is down")

    cm = CacheManager(redis_url="redis://fake:6379/0", enable_redis=True)
    cm._redis = failing_client
    cm._redis_available = True

    await cm.set("fallback_key", "memory_value", ttl=60)
    val = await cm.get("fallback_key")
    assert val == "memory_value"
    assert cm._redis_available is False


@pytest.mark.asyncio
async def test_cache_manager_invalid_json_handling():
    cm = CacheManager(enable_redis=False)
    await cm.set("invalid_json", "not a json string", ttl=60)
    assert await cm.get_json("invalid_json") is None
    assert await cm.get_cost_summary("invalid_json") is None
    assert await cm.get_resources("invalid_json") is None
    assert await cm.get_anomalies("invalid_json") is None
    assert await cm.get_recommendations("invalid_json") is None
