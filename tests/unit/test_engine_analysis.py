import pytest

from cloudguard.analysis.zscore_detector import ZScoreDetector
from cloudguard.core.models import (
    AnomalyResult,
)
from cloudguard.engine import CostAnalysisEngine
from cloudguard.providers.mock_provider import MockProvider


@pytest.mark.asyncio
async def test_engine_detect_anomalies_default_mock():
    provider = MockProvider(resource_count=50, seed=42)
    engine = CostAnalysisEngine(provider=provider)

    anomalies = await engine.detect_anomalies()
    assert isinstance(anomalies, list)
    for a in anomalies:
        assert isinstance(a, AnomalyResult)
        assert a.actual_cost > 0.0


@pytest.mark.asyncio
async def test_engine_detect_anomalies_custom_strategy():
    provider = MockProvider(resource_count=30, seed=42)
    engine = CostAnalysisEngine(provider=provider)

    custom_strat = ZScoreDetector(threshold=2.0)
    anomalies = await engine.detect_anomalies(strategy=custom_strat)

    assert isinstance(anomalies, list)
    for a in anomalies:
        assert a.method == "zscore"


@pytest.mark.asyncio
async def test_engine_analyze_trends():
    provider = MockProvider(resource_count=50, seed=42)
    engine = CostAnalysisEngine(provider=provider)

    trends = await engine.analyze_trends()
    assert "mom_growth" in trends
    assert "burn_rate" in trends
    assert "top_cost_drivers" in trends
    assert "projections" in trends


@pytest.mark.asyncio
async def test_engine_project_costs():
    provider = MockProvider(resource_count=50, seed=42)
    engine = CostAnalysisEngine(provider=provider)

    projections = await engine.project_costs(days_ahead=20)
    assert "slope" in projections
    assert "projected_cost_next_period" in projections
    assert len(projections["projections"]) == 20
