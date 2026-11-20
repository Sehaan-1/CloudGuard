from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from cloudguard.core.config import Settings
from cloudguard.core.models import (
    CostSummary,
    ScanResult,
)
from cloudguard.dashboard.services import DashboardService, run_async


def test_dashboard_service_resolve_dates():
    svc = DashboardService()
    s, e = svc.resolve_dates(date(2026, 8, 1), date(2026, 8, 10))
    assert s == date(2026, 8, 1)
    assert e == date(2026, 8, 10)

    s_rev, e_rev = svc.resolve_dates(date(2026, 8, 10), date(2026, 8, 1))
    assert s_rev == date(2026, 8, 1)
    assert e_rev == date(2026, 8, 10)

    s_def, e_def = svc.resolve_dates(None, None, days_back=15)
    assert (e_def - s_def).days == 15


@pytest.mark.asyncio
async def test_dashboard_service_cost_summary():
    svc = DashboardService()
    summary = await svc.get_cost_summary("mock", date(2026, 8, 1), date(2026, 8, 10))
    assert isinstance(summary, CostSummary)
    assert summary.total_cost > 0
    assert summary.record_count > 0

    summary_all = await svc.get_cost_summary("all", date(2026, 8, 1), date(2026, 8, 10))
    assert isinstance(summary_all, CostSummary)
    assert summary_all.total_cost > 0


@pytest.mark.asyncio
async def test_dashboard_service_cost_by_service_and_trend():
    svc = DashboardService()
    by_svc = await svc.get_cost_by_service("mock", date(2026, 8, 1), date(2026, 8, 10))
    assert isinstance(by_svc, dict)
    assert len(by_svc) > 0

    trend = await svc.get_cost_trend("mock", date(2026, 8, 1), date(2026, 8, 10), granularity="daily")
    assert isinstance(trend, dict)
    assert len(trend) > 0

    records = await svc.get_cost_records("mock", date(2026, 8, 1), date(2026, 8, 5))
    assert isinstance(records, list)
    assert len(records) > 0


@pytest.mark.asyncio
async def test_dashboard_service_anomalies_and_filtering():
    svc = DashboardService()
    anomalies = await svc.get_anomalies("mock", date(2026, 8, 1), date(2026, 8, 15), method="composite")
    assert isinstance(anomalies, list)

    anomalies_zscore = await svc.get_anomalies("mock", date(2026, 8, 1), date(2026, 8, 15), method="zscore", threshold=2.0)
    assert isinstance(anomalies_zscore, list)

    anomalies_iqr = await svc.get_anomalies("mock", date(2026, 8, 1), date(2026, 8, 15), method="iqr", threshold=1.5)
    assert isinstance(anomalies_iqr, list)

    anomalies_rolling = await svc.get_anomalies("mock", date(2026, 8, 1), date(2026, 8, 15), method="rolling", threshold=2.0)
    assert isinstance(anomalies_rolling, list)

    if anomalies:
        first_id = anomalies[0].id
        retrieved = await svc.get_anomaly_by_id(first_id, provider="mock")
        assert retrieved is not None
        assert retrieved.id == first_id

    missing = await svc.get_anomaly_by_id("non-existent-anomaly", provider="mock")
    assert missing is None


@pytest.mark.asyncio
async def test_dashboard_service_scan_and_recommendations():
    svc = DashboardService()
    scan = await svc.get_scan_result("mock")
    assert isinstance(scan, ScanResult)
    assert scan.total_resources_scanned > 0

    recs = await svc.get_recommendations("mock", scan_result=scan)
    assert isinstance(recs, list)
    assert len(recs) > 0

    first_rec_id = recs[0].id
    retrieved_rec = await svc.get_recommendation_by_id(first_rec_id, provider="mock")
    assert retrieved_rec is not None
    assert retrieved_rec.id == first_rec_id

    missing_rec = await svc.get_recommendation_by_id("non-existent-rec", provider="mock")
    assert missing_rec is None


@pytest.mark.asyncio
async def test_dashboard_service_report_generation(tmp_path: Path):
    svc = DashboardService()
    rep_id, rep_path = await svc.generate_report(
        provider="mock",
        title="Test Report",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 10),
        fmt="html",
        output_dir=tmp_path,
    )
    assert rep_id is not None
    assert rep_path.exists()

    rep_id_json, rep_path_json = await svc.generate_report(
        provider="mock",
        title="Test Report JSON",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 10),
        fmt="json",
        output_dir=tmp_path,
    )
    assert rep_id_json is not None
    assert rep_path_json.exists()


def test_run_async_utility():
    async def sample_coro():
        return 42

    result = run_async(sample_coro())
    assert result == 42


@pytest.mark.asyncio
async def test_dashboard_service_with_all_provider_credentials():
    custom_settings = Settings(
        app_env="testing",
        default_provider="mock",
    )
    svc = DashboardService(settings=custom_settings)
    summary = await svc.get_cost_summary("all", date(2026, 8, 1), date(2026, 8, 5))
    assert isinstance(summary, CostSummary)
    assert summary.total_cost > 0
