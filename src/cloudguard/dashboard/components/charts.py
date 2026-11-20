from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from cloudguard.core.models import (
    AnomalyResult,
    CloudResource,
    CostRecord,
    Severity,
)

DARK_BG = "#1e293b"
DARK_PAPER = "#1e293b"
TEXT_COLOR = "#f8fafc"
GRID_COLOR = "#334155"

PALETTE = [
    "#38bdf8",
    "#34d399",
    "#fbbf24",
    "#a78bfa",
    "#f472b6",
    "#22d3ee",
    "#818cf8",
    "#fb923c",
    "#2dd4bf",
    "#94a3b8",
]


def _apply_dark_layout(
    fig: go.Figure,
    title: str | None = None,
    height: int = 340,
    show_legend: bool = True,
) -> go.Figure:
    layout_update: dict[str, Any] = {
        "paper_bgcolor": DARK_PAPER,
        "plot_bgcolor": DARK_BG,
        "font": {"color": TEXT_COLOR, "family": "Segoe UI, -apple-system, sans-serif", "size": 12},
        "height": height,
        "showlegend": show_legend,
        "margin": {"l": 48, "r": 24, "t": 48 if title else 24, "b": 40},
        "hovermode": "closest",
    }
    if title:
        layout_update["title"] = {
            "text": title,
            "font": {"size": 15, "color": "#f8fafc", "weight": "bold"},
            "x": 0.02,
            "y": 0.95,
        }
    fig.update_layout(**layout_update)
    fig.update_xaxes(showgrid=True, gridcolor=GRID_COLOR, zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor=GRID_COLOR, zeroline=False)
    return fig


def create_empty_figure(message: str = "No data available for selected criteria") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font={"size": 14, "color": "#94a3b8"},
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _apply_dark_layout(fig, height=300, show_legend=False)


def create_spend_trend_figure(
    daily_totals: dict[str, float] | None,
    title: str = "Daily Spending Trend",
) -> go.Figure:
    if not daily_totals:
        return create_empty_figure("No spending trend data available")

    sorted_dates = sorted(daily_totals.keys())
    values = [daily_totals[d] for d in sorted_dates]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=sorted_dates,
            y=values,
            mode="lines+markers",
            name="Daily Spend",
            line={"color": "#38bdf8", "width": 2.5, "shape": "spline"},
            marker={"size": 5, "color": "#0ea5e9"},
            fill="tozeroy",
            fillcolor="rgba(56, 189, 248, 0.15)",
            hovertemplate="<b>%{x}</b><br>Spend: $%{y:,.2f}<extra></extra>",
        )
    )

    if len(values) >= 7:
        rolling_avg = pd.Series(values).rolling(window=7, min_periods=1).mean().tolist()
        fig.add_trace(
            go.Scatter(
                x=sorted_dates,
                y=rolling_avg,
                mode="lines",
                name="7-Day Avg",
                line={"color": "#fbbf24", "width": 2, "dash": "dot"},
                hovertemplate="<b>%{x}</b><br>7-Day Avg: $%{y:,.2f}<extra></extra>",
            )
        )

    fig.update_xaxes(title_text="Date")
    fig.update_yaxes(title_text="Spend ($)", tickprefix="$")
    return _apply_dark_layout(fig, title=title, height=340)


def create_service_donut_figure(
    cost_by_service: dict[str, float] | None,
    title: str = "Cost Breakdown by Service",
) -> go.Figure:
    if not cost_by_service or sum(cost_by_service.values()) == 0:
        return create_empty_figure("No service cost breakdown available")

    sorted_items = sorted(cost_by_service.items(), key=lambda x: x[1], reverse=True)
    labels = [k for k, v in sorted_items]
    values = [v for k, v in sorted_items]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.55,
                marker={"colors": PALETTE * 3},
                textinfo="percent",
                textposition="inside",
                hovertemplate="<b>%{label}</b><br>Cost: $%{value:,.2f}<br>Share: %{percent}<extra></extra>",
            )
        ]
    )

    total_cost = sum(values)
    fig.add_annotation(
        text=f"Total<br><b>${total_cost:,.0f}</b>",
        x=0.5,
        y=0.5,
        font={"size": 13, "color": "#f8fafc"},
        showarrow=False,
    )

    return _apply_dark_layout(fig, title=title, height=340)


def create_region_bar_figure(
    cost_by_region: dict[str, float] | None,
    title: str = "Cost by Cloud Region",
) -> go.Figure:
    if not cost_by_region or sum(cost_by_region.values()) == 0:
        return create_empty_figure("No region cost data available")

    sorted_items = sorted(cost_by_region.items(), key=lambda x: x[1], reverse=True)[:10]
    regions = [k for k, v in sorted_items]
    costs = [v for k, v in sorted_items]

    fig = go.Figure(
        data=[
            go.Bar(
                x=costs,
                y=regions,
                orientation="h",
                marker={"color": "#34d399", "line": {"color": "#059669", "width": 1}},
                text=[f"${c:,.2f}" for c in costs],
                textposition="auto",
                hovertemplate="<b>%{y}</b><br>Cost: $%{x:,.2f}<extra></extra>",
            )
        ]
    )
    fig.update_layout(yaxis={"autorange": "reversed"})
    fig.update_xaxes(title_text="Spend ($)", tickprefix="$")
    fig.update_yaxes(title_text="Region")
    return _apply_dark_layout(fig, title=title, height=340, show_legend=False)


def create_sunburst_figure(
    records: list[CostRecord] | None,
    title: str = "Spending Hierarchy (Service → Region → Item)",
) -> go.Figure:
    if not records:
        return create_empty_figure("No cost line items for hierarchy analysis")

    data = [
        {
            "Service": r.service,
            "Region": r.region,
            "Provider": r.provider.value if hasattr(r.provider, "value") else str(r.provider),
            "UsageType": r.usage_type or r.service,
            "Amount": max(0.01, r.amount),
        }
        for r in records
    ]
    df = pd.DataFrame(data)

    fig = px.sunburst(
        df,
        path=["Provider", "Service", "Region"],
        values="Amount",
        color="Service",
        color_discrete_sequence=PALETTE,
    )
    fig.update_traces(
        hovertemplate="<b>%{label}</b><br>Spend: $%{value:,.2f}<br>Parent: %{parent}<extra></extra>"
    )
    return _apply_dark_layout(fig, title=title, height=420)


def create_stacked_service_area_figure(
    records: list[CostRecord] | None,
    title: str = "Service Spend Distribution Over Time",
) -> go.Figure:
    if not records:
        return create_empty_figure("No cost timeline data available")

    rows = []
    for r in records:
        rows.append(
            {
                "date": r.date.isoformat(),
                "service": r.service,
                "amount": r.amount,
            }
        )
    df = pd.DataFrame(rows)
    pivot_df = df.groupby(["date", "service"])["amount"].sum().reset_index()

    top_services = (
        pivot_df.groupby("service")["amount"]
        .sum()
        .sort_values(ascending=False)
        .head(8)
        .index.tolist()
    )

    pivot_df["service_grouped"] = pivot_df["service"].apply(
        lambda s: s if s in top_services else "Other"
    )
    grouped = pivot_df.groupby(["date", "service_grouped"])["amount"].sum().reset_index()

    fig = px.area(
        grouped,
        x="date",
        y="amount",
        color="service_grouped",
        color_discrete_sequence=PALETTE,
        labels={"amount": "Spend ($)", "date": "Date", "service_grouped": "Service"},
    )
    fig.update_traces(
        hovertemplate="<b>%{fullData.name}</b><br>%{x}<br>Spend: $%{y:,.2f}<extra></extra>"
    )
    fig.update_xaxes(title_text="Date")
    fig.update_yaxes(title_text="Spend ($)", tickprefix="$")
    return _apply_dark_layout(fig, title=title, height=380)


def create_anomaly_scatter_figure(
    records: list[CostRecord] | None,
    anomalies: list[AnomalyResult] | None,
    title: str = "Spending Timeline with Detected Anomalies",
) -> go.Figure:
    daily_map: dict[str, float] = {}
    if records:
        for r in records:
            d_str = r.date.isoformat()
            daily_map[d_str] = round(daily_map.get(d_str, 0.0) + r.amount, 2)

    sorted_dates = sorted(daily_map.keys())
    values = [daily_map[d] for d in sorted_dates]

    fig = go.Figure()

    if sorted_dates:
        fig.add_trace(
            go.Scatter(
                x=sorted_dates,
                y=values,
                mode="lines",
                name="Daily Actual Spend",
                line={"color": "#64748b", "width": 2},
                hovertemplate="<b>%{x}</b><br>Daily Spend: $%{y:,.2f}<extra></extra>",
            )
        )

        mean_val = float(np.mean(values)) if values else 0.0
        std_val = float(np.std(values)) if values else 0.0
        upper_bound = [mean_val + 2 * std_val] * len(sorted_dates)
        lower_bound = [max(0.0, mean_val - 2 * std_val)] * len(sorted_dates)

        fig.add_trace(
            go.Scatter(
                x=sorted_dates,
                y=upper_bound,
                mode="lines",
                name="Upper Expected Threshold (+2 sigma)",
                line={"color": "#fbbf24", "width": 1.5, "dash": "dash"},
                hovertemplate="Threshold: $%{y:,.2f}<extra></extra>",
            )
        )

        fig.add_trace(
            go.Scatter(
                x=sorted_dates,
                y=lower_bound,
                mode="lines",
                name="Lower Expected Threshold (-2 sigma)",
                line={"color": "#34d399", "width": 1.5, "dash": "dash"},
                hovertemplate="Lower Bound: $%{y:,.2f}<extra></extra>",
            )
        )

    if anomalies:
        sev_color_map = {
            Severity.LOW: "#38bdf8",
            Severity.MEDIUM: "#fbbf24",
            Severity.HIGH: "#fb923c",
            Severity.CRITICAL: "#ef4444",
        }

        a_x = [a.date.isoformat() for a in anomalies]
        a_y = [a.actual_cost for a in anomalies]
        a_colors = [
            sev_color_map.get(
                a.severity if isinstance(a.severity, Severity) else Severity(a.severity), "#ef4444"
            )
            for a in anomalies
        ]
        a_text = [
            f"<b>{a.service}</b><br>Observed: ${a.actual_cost:,.2f}<br>Expected: ${a.expected_cost:,.2f}<br>Deviation: {a.deviation_score:.2f} sigma<br>Severity: {a.severity.value.upper()}"
            for a in anomalies
        ]

        fig.add_trace(
            go.Scatter(
                x=a_x,
                y=a_y,
                mode="markers",
                name="Anomaly Spike",
                marker={
                    "size": 12,
                    "color": a_colors,
                    "symbol": "diamond",
                    "line": {"color": "#ffffff", "width": 1.5},
                },
                text=a_text,
                hoverinfo="text",
            )
        )

    fig.update_xaxes(title_text="Date")
    fig.update_yaxes(title_text="Daily Spend ($)", tickprefix="$")
    return _apply_dark_layout(fig, title=title, height=380)


def create_utilization_heatmap_figure(
    resources: list[CloudResource] | None,
    title: str = "Resource Efficiency Heatmap by Type",
) -> go.Figure:
    if not resources:
        return create_empty_figure("No resource inventory data available")

    type_counts: dict[str, list[int]] = {}
    for r in resources:
        t = r.type.value if hasattr(r.type, "value") else str(r.type)
        if t not in type_counts:
            type_counts[t] = [0, 0, 0, 0]

        if r.utilization_pct < 5.0:
            type_counts[t][0] += 1
        elif r.utilization_pct < 20.0:
            type_counts[t][1] += 1
        elif r.utilization_pct < 50.0:
            type_counts[t][2] += 1
        else:
            type_counts[t][3] += 1

    if not type_counts:
        return create_empty_figure("No categorized resource metrics available")

    categories = list(type_counts.keys())
    buckets = ["<5% (Idle)", "5-20% (Low)", "20-50% (Normal)", "50%+ (High)"]
    z_matrix = [type_counts[c] for c in categories]

    fig = go.Figure(
        data=go.Heatmap(
            z=z_matrix,
            x=buckets,
            y=categories,
            colorscale=[
                [0.0, "#0f172a"],
                [0.2, "#1e3a8a"],
                [0.5, "#d97706"],
                [1.0, "#dc2626"],
            ],
            hovertemplate="Type: %{y}<br>Bucket: %{x}<br>Count: %{z}<extra></extra>",
            showscale=True,
        )
    )

    for i, cat in enumerate(categories):
        for j, bucket in enumerate(buckets):
            val = z_matrix[i][j]
            fig.add_annotation(
                x=bucket,
                y=cat,
                text=str(val),
                showarrow=False,
                font={"color": "#f8fafc", "size": 13, "weight": "bold"},
            )

    return _apply_dark_layout(fig, title=title, height=320)


def create_cost_vs_utilization_bubble_figure(
    resources: list[CloudResource] | None,
    title: str = "Resource Spend vs. Utilization Efficiency",
) -> go.Figure:
    if not resources:
        return create_empty_figure("No resource cost vs. utilization data available")

    rows = []
    for r in resources:
        rows.append(
            {
                "name": r.name,
                "type": r.type.value if hasattr(r.type, "value") else str(r.type),
                "utilization": r.utilization_pct,
                "cost": max(1.0, r.monthly_cost),
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                "region": r.region,
            }
        )
    df = pd.DataFrame(rows)

    fig = px.scatter(
        df,
        x="utilization",
        y="cost",
        size="cost",
        color="status",
        hover_name="name",
        hover_data={"region": True, "type": True, "cost": ":$,.2f", "utilization": ":.1f%"},
        color_discrete_map={
            "idle": "#ef4444",
            "orphaned": "#f97316",
            "underutilized": "#fbbf24",
            "running": "#34d399",
            "stopped": "#94a3b8",
        },
        labels={"utilization": "Average Utilization (%)", "cost": "Monthly Cost ($)"},
    )

    fig.add_shape(
        type="rect",
        x0=0,
        x1=20,
        y0=0,
        y1=df["cost"].max() * 1.1 if not df.empty else 100,
        fillcolor="rgba(239, 68, 68, 0.08)",
        line={"width": 0},
        layer="below",
    )
    fig.add_annotation(
        x=10,
        y=df["cost"].max() * 0.9 if not df.empty else 50,
        text="High Waste Zone (<20% Util)",
        showarrow=False,
        font={"size": 11, "color": "#f87171"},
    )

    fig.update_xaxes(title_text="Utilization (%)", range=[-2, 102])
    fig.update_yaxes(title_text="Monthly Cost ($)", tickprefix="$")
    return _apply_dark_layout(fig, title=title, height=380)
