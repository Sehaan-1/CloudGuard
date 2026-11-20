"""Unit tests for CostAnalysisEngine in cloudguard.engine."""

from datetime import date

import pytest

from cloudguard.core.exceptions import AnalysisEngineError
from cloudguard.core.models import CloudProviderType, CostSummary, ScanResult
from cloudguard.engine import CostAnalysisEngine
from cloudguard.providers.base import CloudProvider
from cloudguard.providers.mock_provider import MockProvider


class BrokenProvider(CloudProvider):
    @property
    def provider_type(self) -> CloudProviderType:
        return CloudProviderType.MOCK

    def provider_name(self) -> str:
        return "Broken Cloud"

    async def test_connection(self) -> bool:
        return False

    async def get_cost_data(self, start_date, end_date, granularity):
        raise RuntimeError("Network drop")

    async def get_cost_summary(self, start_date, end_date):
        raise RuntimeError("Math crash")

    async def list_resources(self, resource_types=None):
        return []

    async def get_resource_utilization(self, resource_id, period_days=7):
        return 0.0

    async def get_idle_resources(self, threshold_pct=5.0, period_days=7):
        return []

    async def get_orphaned_storage(self, unused_days=30):
        return []

    async def scan(self, **kwargs):
        raise RuntimeError("Scan error")


class TestCostAnalysisEngine:
    @pytest.mark.asyncio
    async def test_engine_initialization_and_connection(self):
        engine = CostAnalysisEngine(provider="mock")
        assert engine.provider is not None
        assert await engine.test_connection() is True

    @pytest.mark.asyncio
    async def test_engine_initialization_with_instance(self):
        mock_p = MockProvider()
        engine = CostAnalysisEngine(provider=mock_p)
        assert engine.provider is mock_p

    @pytest.mark.asyncio
    async def test_engine_initialization_with_none_uses_default(self):
        engine = CostAnalysisEngine(provider=None)
        assert engine.provider is not None

    @pytest.mark.asyncio
    async def test_engine_get_cost_data(self):
        engine = CostAnalysisEngine(provider="mock")
        start = date(2026, 8, 1)
        end = date(2026, 8, 7)
        records = await engine.get_cost_data(start_date=start, end_date=end)

        assert len(records) > 0
        assert all(r.date >= start and r.date <= end for r in records)

    @pytest.mark.asyncio
    async def test_engine_get_cost_data_default_dates(self):
        engine = CostAnalysisEngine(provider="mock")
        records = await engine.get_cost_data()
        assert len(records) > 0

    @pytest.mark.asyncio
    async def test_engine_get_cost_summary(self):
        engine = CostAnalysisEngine(provider="mock")
        start = date(2026, 8, 1)
        end = date(2026, 8, 7)
        summary = await engine.get_cost_summary(start_date=start, end_date=end)

        assert isinstance(summary, CostSummary)
        assert summary.total_cost > 0
        assert summary.record_count > 0
        assert summary.period_start == start
        assert summary.period_end == end

    @pytest.mark.asyncio
    async def test_engine_scan_infrastructure(self):
        engine = CostAnalysisEngine(provider="mock")
        scan = await engine.scan_infrastructure()

        assert isinstance(scan, ScanResult)
        assert scan.total_resources_scanned > 0
        assert scan.total_waste_monthly > 0.0

    @pytest.mark.asyncio
    async def test_multi_cloud_scan_and_summary(self):
        results = await CostAnalysisEngine.multi_cloud_scan(["mock"])
        assert "mock" in results
        assert results["mock"].total_resources_scanned > 0

        start = date(2026, 8, 1)
        end = date(2026, 8, 7)
        multi_summary = await CostAnalysisEngine.multi_cloud_summary(
            ["mock"], start_date=start, end_date=end
        )
        assert isinstance(multi_summary, CostSummary)
        assert multi_summary.total_cost > 0

    @pytest.mark.asyncio
    async def test_engine_error_wrapping(self):
        broken = BrokenProvider()
        engine = CostAnalysisEngine(provider=broken)

        with pytest.raises(AnalysisEngineError):
            await engine.get_cost_data()

        with pytest.raises(AnalysisEngineError):
            await engine.get_cost_summary()

        with pytest.raises(AnalysisEngineError):
            await engine.scan_infrastructure()
