from __future__ import annotations

from datetime import date, datetime
from typing import Any

import dash
from dash import Input, Output, html

from cloudguard.dashboard.components.charts import (
    create_service_donut_figure,
    create_spend_trend_figure,
)
from cloudguard.dashboard.components.kpi_cards import render_kpi_grid
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


def register_overview_callbacks(app: dash.Dash) -> None:

    @app.callback(
        Output("overview-kpi-container", "children"),
        [
            Input("global-provider-select", "value"),
            Input("global-date-picker", "start_date"),
            Input("global-date-picker", "end_date"),
            Input("auto-refresh-interval", "n_intervals"),
        ],
    )
    def update_overview_kpis(
        provider: str | None,
        start_date: Any,
        end_date: Any,
        _n: int,
    ) -> html.Div:
        p = provider or "mock"
        s = _parse_dt(start_date)
        e = _parse_dt(end_date)

        async def _fetch():
            summary = await dashboard_service.get_cost_summary(p, s, e)
            scan = await dashboard_service.get_scan_result(p)
            anomalies = await dashboard_service.get_anomalies(p, s, e)
            recs = await dashboard_service.get_recommendations(p, scan_result=scan)
            return summary, scan, anomalies, recs

        try:
            summary, scan, anomalies, recs = run_async(_fetch())
            potential_savings = sum(r.estimated_savings for r in recs)
            return render_kpi_grid(
                total_cost=summary.total_cost,
                currency=summary.currency,
                total_waste=scan.total_waste_monthly,
                potential_savings=round(potential_savings, 2),
                anomalies_count=len(anomalies),
                avg_daily=summary.average_daily_cost,
            )
        except Exception as exc:
            return html.Div(
                f"Failed to load metrics: {exc}",
                style={"color": "#f87171", "padding": "16px"},
            )

    @app.callback(
        Output("overview-trend-graph", "figure"),
        [
            Input("global-provider-select", "value"),
            Input("global-date-picker", "start_date"),
            Input("global-date-picker", "end_date"),
            Input("auto-refresh-interval", "n_intervals"),
        ],
    )
    def update_overview_trend(
        provider: str | None,
        start_date: Any,
        end_date: Any,
        _n: int,
    ):
        p = provider or "mock"
        s = _parse_dt(start_date)
        e = _parse_dt(end_date)

        async def _fetch():
            return await dashboard_service.get_cost_trend(p, s, e)

        daily_totals = run_async(_fetch())
        return create_spend_trend_figure(daily_totals)

    @app.callback(
        Output("overview-service-donut-graph", "figure"),
        [
            Input("global-provider-select", "value"),
            Input("global-date-picker", "start_date"),
            Input("global-date-picker", "end_date"),
            Input("auto-refresh-interval", "n_intervals"),
        ],
    )
    def update_overview_donut(
        provider: str | None,
        start_date: Any,
        end_date: Any,
        _n: int,
    ):
        p = provider or "mock"
        s = _parse_dt(start_date)
        e = _parse_dt(end_date)

        async def _fetch():
            return await dashboard_service.get_cost_by_service(p, s, e)

        cost_by_svc = run_async(_fetch())
        return create_service_donut_figure(cost_by_svc)

    @app.callback(
        Output("overview-anomalies-container", "children"),
        [
            Input("global-provider-select", "value"),
            Input("global-date-picker", "start_date"),
            Input("global-date-picker", "end_date"),
            Input("auto-refresh-interval", "n_intervals"),
        ],
    )
    def update_overview_anomalies(
        provider: str | None,
        start_date: Any,
        end_date: Any,
        _n: int,
    ) -> html.Div:
        p = provider or "mock"
        s = _parse_dt(start_date)
        e = _parse_dt(end_date)

        async def _fetch():
            return await dashboard_service.get_anomalies(p, s, e)

        anomalies = run_async(_fetch())
        if not anomalies:
            return html.Div(
                "✅ No active spending anomalies detected in the selected period.",
                style={
                    "color": "#34d399",
                    "padding": "16px 0",
                    "fontSize": "0.95rem",
                    "fontWeight": "500",
                },
            )

        items = []
        for a in anomalies[:5]:
            sev = a.severity.value if hasattr(a.severity, "value") else str(a.severity)
            badge_color = (
                "#ef4444"
                if sev == "critical"
                else "#fb923c"
                if sev == "high"
                else "#fbbf24"
                if sev == "medium"
                else "#38bdf8"
            )

            items.append(
                html.Div(
                    children=[
                        html.Div(
                            children=[
                                html.Span(
                                    a.service,
                                    style={
                                        "color": "#f8fafc",
                                        "fontWeight": "600",
                                        "fontSize": "0.9rem",
                                    },
                                ),
                                html.Span(
                                    sev.upper(),
                                    style={
                                        "backgroundColor": f"{badge_color}20",
                                        "color": badge_color,
                                        "border": f"1px solid {badge_color}50",
                                        "borderRadius": "4px",
                                        "padding": "2px 6px",
                                        "fontSize": "0.7rem",
                                        "fontWeight": "bold",
                                        "marginLeft": "8px",
                                    },
                                ),
                            ],
                            style={
                                "display": "flex",
                                "alignItems": "center",
                                "marginBottom": "4px",
                            },
                        ),
                        html.Div(
                            f"Observed ${a.actual_cost:,.2f} vs expected ${a.expected_cost:,.2f} on {a.date.isoformat()} ({a.deviation_score:.1f} sigma)",
                            style={"color": "#94a3b8", "fontSize": "0.8rem"},
                        ),
                    ],
                    style={
                        "backgroundColor": "#0f172a",
                        "border": "1px solid #334155",
                        "borderRadius": "8px",
                        "padding": "10px 14px",
                        "marginBottom": "10px",
                    },
                )
            )

        return html.Div(items)

    @app.callback(
        Output("overview-recommendations-container", "children"),
        [
            Input("global-provider-select", "value"),
            Input("auto-refresh-interval", "n_intervals"),
        ],
    )
    def update_overview_recommendations(
        provider: str | None,
        _n: int,
    ) -> html.Div:
        p = provider or "mock"

        async def _fetch():
            return await dashboard_service.get_recommendations(p)

        recs = run_async(_fetch())
        if not recs:
            return html.Div(
                "✅ Infrastructure is optimized. No high-priority recommendations.",
                style={
                    "color": "#34d399",
                    "padding": "16px 0",
                    "fontSize": "0.95rem",
                    "fontWeight": "500",
                },
            )

        items = []
        for r in recs[:5]:
            items.append(
                html.Div(
                    children=[
                        html.Div(
                            children=[
                                html.Span(
                                    r.title,
                                    style={
                                        "color": "#f8fafc",
                                        "fontWeight": "600",
                                        "fontSize": "0.9rem",
                                    },
                                ),
                                html.Span(
                                    f"+${r.estimated_savings:,.0f}/mo",
                                    style={
                                        "backgroundColor": "rgba(16, 185, 129, 0.15)",
                                        "color": "#34d399",
                                        "border": "1px solid rgba(16, 185, 129, 0.4)",
                                        "borderRadius": "4px",
                                        "padding": "2px 6px",
                                        "fontSize": "0.75rem",
                                        "fontWeight": "bold",
                                        "marginLeft": "8px",
                                    },
                                ),
                            ],
                            style={
                                "display": "flex",
                                "justifyContent": "space-between",
                                "alignItems": "center",
                                "marginBottom": "4px",
                            },
                        ),
                        html.Div(
                            f"{r.description[:90]}..."
                            if len(r.description) > 90
                            else r.description,
                            style={"color": "#94a3b8", "fontSize": "0.8rem"},
                        ),
                    ],
                    style={
                        "backgroundColor": "#0f172a",
                        "border": "1px solid #334155",
                        "borderRadius": "8px",
                        "padding": "10px 14px",
                        "marginBottom": "10px",
                    },
                )
            )

        return html.Div(items)
