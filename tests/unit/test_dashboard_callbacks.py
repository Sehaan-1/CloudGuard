from __future__ import annotations

import inspect

import dash
import pytest

from cloudguard.dashboard.callbacks.anomaly_cb import register_anomaly_callbacks
from cloudguard.dashboard.callbacks.cost_cb import register_cost_callbacks
from cloudguard.dashboard.callbacks.overview_cb import register_overview_callbacks
from cloudguard.dashboard.callbacks.resource_cb import register_resource_callbacks


@pytest.fixture
def dash_test_app() -> dash.Dash:
    app = dash.Dash(__name__)
    register_overview_callbacks(app)
    register_cost_callbacks(app)
    register_anomaly_callbacks(app)
    register_resource_callbacks(app)
    return app


def _get_callback_fn(app: dash.Dash, output_id: str):
    for key, cb in app.callback_map.items():
        if output_id in key:
            fn = cb["callback"]
            return inspect.unwrap(fn)
    raise KeyError(f"No callback found for output {output_id}")


def test_overview_callbacks_invocation(dash_test_app: dash.Dash):
    kpi_cb = _get_callback_fn(dash_test_app, "overview-kpi-container.children")
    kpi_res = kpi_cb("mock", "2026-08-01", "2026-08-10", 0)
    assert kpi_res is not None

    trend_cb = _get_callback_fn(dash_test_app, "overview-trend-graph.figure")
    trend_fig = trend_cb("mock", "2026-08-01", "2026-08-10", 0)
    assert trend_fig is not None

    donut_cb = _get_callback_fn(dash_test_app, "overview-service-donut-graph.figure")
    donut_fig = donut_cb("mock", "2026-08-01", "2026-08-10", 0)
    assert donut_fig is not None

    anom_cb = _get_callback_fn(dash_test_app, "overview-anomalies-container.children")
    anom_res = anom_cb("mock", "2026-08-01", "2026-08-10", 0)
    assert anom_res is not None

    rec_cb = _get_callback_fn(dash_test_app, "overview-recommendations-container.children")
    rec_res = rec_cb("mock", 0)
    assert rec_res is not None


def test_cost_callbacks_invocation(dash_test_app: dash.Dash):
    cost_explorer_cb = _get_callback_fn(dash_test_app, "cost-sunburst-graph.figure")
    sunburst_fig, region_fig, stacked_fig, table_data = cost_explorer_cb("mock", "2026-08-01", "2026-08-10", 0)
    assert sunburst_fig is not None
    assert region_fig is not None
    assert stacked_fig is not None
    assert isinstance(table_data, list)

    export_csv_cb = _get_callback_fn(dash_test_app, "download-cost-csv.data")
    no_export = export_csv_cb(None, "mock", "2026-08-01", "2026-08-10")
    assert no_export == dash.no_update

    exported = export_csv_cb(1, "mock", "2026-08-01", "2026-08-10")
    assert exported is not None
    assert "content" in exported or "filename" in exported


def test_anomaly_callbacks_invocation(dash_test_app: dash.Dash):
    anomaly_cb = _get_callback_fn(dash_test_app, "anomaly-timeline-graph.figure")
    fig, table = anomaly_cb("mock", "2026-08-01", "2026-08-15", "composite", 3.0, "all", 0)
    assert fig is not None
    assert isinstance(table, list)

    for sev in ["critical", "high", "medium", "low"]:
        fig_s, table_s = anomaly_cb("mock", "2026-08-01", "2026-08-15", "composite", 3.0, sev, 0)
        assert fig_s is not None
        assert isinstance(table_s, list)


def test_resource_callbacks_invocation(dash_test_app: dash.Dash):
    res_cb = _get_callback_fn(dash_test_app, "resource-metrics-container.children")
    kpis, heatmap, bubble, inventory = res_cb("mock", "all", 0)
    assert kpis is not None
    assert heatmap is not None
    assert bubble is not None
    assert isinstance(inventory, list)

    for filter_val in ["idle", "orphaned", "underutilized", "untagged"]:
        _, _, _, filtered_inv = res_cb("mock", filter_val, 0)
        assert isinstance(filtered_inv, list)
