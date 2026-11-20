from __future__ import annotations

from datetime import date, datetime
from typing import Any

import dash
import pandas as pd
from dash import Input, Output, State, dcc

from cloudguard.dashboard.components.charts import (
    create_region_bar_figure,
    create_stacked_service_area_figure,
    create_sunburst_figure,
)
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


def register_cost_callbacks(app: dash.Dash) -> None:

    @app.callback(
        [
            Output("cost-sunburst-graph", "figure"),
            Output("cost-region-graph", "figure"),
            Output("cost-stacked-graph", "figure"),
            Output("cost-data-table", "data"),
        ],
        [
            Input("global-provider-select", "value"),
            Input("global-date-picker", "start_date"),
            Input("global-date-picker", "end_date"),
            Input("auto-refresh-interval", "n_intervals"),
        ],
    )
    def update_cost_explorer(
        provider: str | None,
        start_date: Any,
        end_date: Any,
        _n: int,
    ):
        p = provider or "mock"
        s = _parse_dt(start_date)
        e = _parse_dt(end_date)

        async def _fetch():
            records = await dashboard_service.get_cost_records(p, s, e)
            summary = await dashboard_service.get_cost_summary(p, s, e)
            return records, summary

        records, summary = run_async(_fetch())

        sunburst_fig = create_sunburst_figure(records)
        region_fig = create_region_bar_figure(summary.cost_by_region)
        stacked_fig = create_stacked_service_area_figure(records)

        table_data = [
            {
                "date": r.date.isoformat(),
                "service": r.service,
                "provider": r.provider.value if hasattr(r.provider, "value") else str(r.provider),
                "region": r.region,
                "usage_type": r.usage_type or r.service,
                "amount": f"{r.amount:,.2f}",
            }
            for r in records[:500]
        ]

        return sunburst_fig, region_fig, stacked_fig, table_data

    @app.callback(
        Output("download-cost-csv", "data"),
        Input("btn-export-cost-csv", "n_clicks"),
        [
            State("global-provider-select", "value"),
            State("global-date-picker", "start_date"),
            State("global-date-picker", "end_date"),
        ],
        prevent_initial_call=True,
    )
    def export_cost_csv(
        n_clicks: int | None,
        provider: str | None,
        start_date: Any,
        end_date: Any,
    ):
        if not n_clicks:
            return dash.no_update

        p = provider or "mock"
        s = _parse_dt(start_date)
        e = _parse_dt(end_date)

        async def _fetch():
            return await dashboard_service.get_cost_records(p, s, e)

        records = run_async(_fetch())
        rows = [
            {
                "date": r.date.isoformat(),
                "service": r.service,
                "provider": r.provider.value if hasattr(r.provider, "value") else str(r.provider),
                "region": r.region,
                "usage_type": r.usage_type or "",
                "amount": r.amount,
                "currency": r.currency,
            }
            for r in records
        ]
        df = pd.DataFrame(rows)
        return dcc.send_data_frame(df.to_csv, f"cloudguard_costs_{p}.csv", index=False)
