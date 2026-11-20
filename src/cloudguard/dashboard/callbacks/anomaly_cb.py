from __future__ import annotations

from datetime import date, datetime
from typing import Any

import dash
from dash import Input, Output

from cloudguard.dashboard.components.charts import create_anomaly_scatter_figure
from cloudguard.dashboard.services import dashboard_service, run_async


def _parse_dt(d_val: Any) -> date | None:
    if not d_val:
        return None
    if isinstance(d_val, date):
        return d_val
    try:
        return datetime.strptime(str(d_val)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def register_anomaly_callbacks(app: dash.Dash) -> None:

    @app.callback(
        [
            Output("anomaly-timeline-graph", "figure"),
            Output("anomaly-detail-table", "data"),
        ],
        [
            Input("global-provider-select", "value"),
            Input("global-date-picker", "start_date"),
            Input("global-date-picker", "end_date"),
            Input("anomaly-method-dropdown", "value"),
            Input("anomaly-sensitivity-slider", "value"),
            Input("anomaly-severity-filter", "value"),
            Input("auto-refresh-interval", "n_intervals"),
        ],
    )
    def update_anomalies_view(
        provider: str | None,
        start_date: Any,
        end_date: Any,
        method: str | None,
        sensitivity: float | None,
        severity_filter: str | None,
        _n: int,
    ):
        p = provider or "mock"
        s = _parse_dt(start_date)
        e = _parse_dt(end_date)
        m = method or "composite"
        sens = sensitivity or 3.0

        async def _fetch():
            records = await dashboard_service.get_cost_records(p, s, e)
            anomalies = await dashboard_service.get_anomalies(
                provider=p,
                start_date=s,
                end_date=e,
                method=m,
                threshold=sens,
            )
            return records, anomalies

        records, anomalies = run_async(_fetch())

        if severity_filter and severity_filter != "all":
            if severity_filter == "critical":
                anomalies = [
                    a
                    for a in anomalies
                    if (a.severity.value if hasattr(a.severity, "value") else str(a.severity))
                    == "critical"
                ]
            elif severity_filter == "high":
                anomalies = [
                    a
                    for a in anomalies
                    if (a.severity.value if hasattr(a.severity, "value") else str(a.severity))
                    in ("high", "critical")
                ]
            elif severity_filter == "medium":
                anomalies = [
                    a
                    for a in anomalies
                    if (a.severity.value if hasattr(a.severity, "value") else str(a.severity))
                    in ("medium", "high", "critical")
                ]
            elif severity_filter == "low":
                anomalies = [
                    a
                    for a in anomalies
                    if (a.severity.value if hasattr(a.severity, "value") else str(a.severity))
                    == "low"
                ]

        fig = create_anomaly_scatter_figure(records, anomalies)

        table_data = [
            {
                "date": a.date.isoformat(),
                "service": a.service,
                "expected_cost": f"${a.expected_cost:,.2f}",
                "actual_cost": f"${a.actual_cost:,.2f}",
                "deviation_score": f"{a.deviation_score:.2f} sigma",
                "severity": (
                    a.severity.value.upper()
                    if hasattr(a.severity, "value")
                    else str(a.severity).upper()
                ),
                "method": a.method,
                "description": a.description,
            }
            for a in anomalies
        ]

        return fig, table_data
