from __future__ import annotations

from datetime import date

from cloudguard.core.models import (
    AnomalyResult,
    CloudProviderType,
    CloudResource,
    CostRecord,
    ResourceStatus,
    ResourceType,
    Severity,
)
from cloudguard.dashboard.components.charts import (
    create_anomaly_scatter_figure,
    create_cost_vs_utilization_bubble_figure,
    create_empty_figure,
    create_region_bar_figure,
    create_service_donut_figure,
    create_spend_trend_figure,
    create_stacked_service_area_figure,
    create_sunburst_figure,
    create_utilization_heatmap_figure,
)
from cloudguard.dashboard.components.kpi_cards import render_kpi_card, render_kpi_grid
from cloudguard.dashboard.dash_app import create_dash_app
from cloudguard.dashboard.layouts import (
    layout_anomalies,
    layout_cost_explorer,
    layout_overview,
    layout_resources,
)


def test_kpi_card_rendering():
    card = render_kpi_card(
        title="Total Spend",
        value="$12,345.67",
        subtitle="Last 30 days",
        icon="💳",
        color="#38bdf8",
        badge_text="Active",
        badge_color="#10b981",
    )
    assert card is not None
    assert hasattr(card, "children")

    grid = render_kpi_grid(
        total_cost=50000.0,
        currency="USD",
        total_waste=2500.0,
        potential_savings=4000.0,
        anomalies_count=3,
        avg_daily=1666.67,
    )
    assert grid is not None
    assert len(grid.children) == 4


def test_chart_creation():
    empty_fig = create_empty_figure("No data")
    assert empty_fig is not None

    trend_fig = create_spend_trend_figure({"2026-08-01": 100.0, "2026-08-02": 150.0})
    assert trend_fig is not None
    assert len(trend_fig.data) > 0

    donut_fig = create_service_donut_figure({"Compute": 500.0, "Storage": 200.0})
    assert donut_fig is not None
    assert len(donut_fig.data) > 0

    region_fig = create_region_bar_figure({"eastus": 400.0, "westus": 300.0})
    assert region_fig is not None
    assert len(region_fig.data) > 0

    records = [
        CostRecord(
            service="Virtual Machines",
            date=date(2026, 8, 1),
            amount=120.0,
            provider=CloudProviderType.MOCK,
            region="eastus",
        ),
        CostRecord(
            service="Storage Accounts",
            date=date(2026, 8, 1),
            amount=30.0,
            provider=CloudProviderType.MOCK,
            region="westus",
        ),
    ]

    sunburst_fig = create_sunburst_figure(records)
    assert sunburst_fig is not None

    stacked_fig = create_stacked_service_area_figure(records)
    assert stacked_fig is not None

    anomalies = [
        AnomalyResult(
            service="Virtual Machines",
            date=date(2026, 8, 1),
            expected_cost=100.0,
            actual_cost=250.0,
            deviation_score=3.5,
            severity=Severity.HIGH,
        )
    ]
    anomaly_fig = create_anomaly_scatter_figure(records, anomalies)
    assert anomaly_fig is not None

    resources = [
        CloudResource(
            id="vm-1",
            name="test-vm-1",
            type=ResourceType.VM,
            provider=CloudProviderType.MOCK,
            utilization_pct=2.0,
            status=ResourceStatus.IDLE,
            monthly_cost=80.0,
        ),
        CloudResource(
            id="disk-1",
            name="test-disk-1",
            type=ResourceType.STORAGE,
            provider=CloudProviderType.MOCK,
            utilization_pct=0.0,
            status=ResourceStatus.ORPHANED,
            monthly_cost=40.0,
        ),
    ]

    heatmap_fig = create_utilization_heatmap_figure(resources)
    assert heatmap_fig is not None

    bubble_fig = create_cost_vs_utilization_bubble_figure(resources)
    assert bubble_fig is not None


def test_layouts_creation():
    ov = layout_overview()
    assert ov is not None

    ce = layout_cost_explorer()
    assert ce is not None

    an = layout_anomalies()
    assert an is not None

    res = layout_resources()
    assert res is not None


def test_dash_app_creation():
    app = create_dash_app()
    assert app is not None
    assert app.layout is not None
