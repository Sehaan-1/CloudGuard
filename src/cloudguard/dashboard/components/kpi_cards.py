from __future__ import annotations

from typing import Any

from dash import html


def render_kpi_card(
    title: str,
    value: str,
    subtitle: str | None = None,
    icon: str = "💰",
    color: str = "#38bdf8",
    badge_text: str | None = None,
    badge_color: str = "#10b981",
    card_id: str | None = None,
) -> html.Div:
    card_style: dict[str, Any] = {
        "backgroundColor": "#1e293b",
        "border": "1px solid #334155",
        "borderRadius": "12px",
        "padding": "20px",
        "position": "relative",
        "overflow": "hidden",
        "boxShadow": "0 4px 12px rgba(0, 0, 0, 0.25)",
        "transition": "transform 0.2s, box-shadow 0.2s",
        "flex": "1",
        "minWidth": "220px",
    }

    accent_bar_style: dict[str, Any] = {
        "position": "absolute",
        "top": "0",
        "left": "0",
        "right": "0",
        "height": "4px",
        "backgroundColor": color,
    }

    header_children = [
        html.Span(
            title,
            style={
                "color": "#94a3b8",
                "fontSize": "0.85rem",
                "fontWeight": "600",
                "textTransform": "uppercase",
                "letterSpacing": "0.05em",
            },
        ),
        html.Span(icon, style={"fontSize": "1.4rem"}),
    ]

    badge_element = None
    if badge_text:
        badge_element = html.Span(
            badge_text,
            style={
                "backgroundColor": f"{badge_color}20",
                "color": badge_color,
                "border": f"1px solid {badge_color}50",
                "borderRadius": "9999px",
                "padding": "2px 8px",
                "fontSize": "0.75rem",
                "fontWeight": "600",
                "marginLeft": "8px",
            },
        )

    return html.Div(
        id=card_id or f"kpi-card-{title.lower().replace(' ', '-')}",
        children=[
            html.Div(style=accent_bar_style),
            html.Div(
                children=header_children,
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "marginBottom": "8px",
                },
            ),
            html.Div(
                children=[
                    html.Span(
                        value,
                        style={
                            "fontSize": "1.75rem",
                            "fontWeight": "700",
                            "color": "#f8fafc",
                            "fontFamily": "Segoe UI, -apple-system, sans-serif",
                        },
                    ),
                    badge_element,
                ],
                style={"display": "flex", "alignItems": "baseline", "marginBottom": "4px"},
            ),
            html.Div(
                subtitle or "",
                style={
                    "color": "#64748b",
                    "fontSize": "0.8rem",
                    "fontWeight": "500",
                },
            )
            if subtitle
            else html.Div(),
        ],
        style=card_style,
    )


def render_kpi_grid(
    total_cost: float = 0.0,
    currency: str = "USD",
    total_waste: float = 0.0,
    potential_savings: float = 0.0,
    anomalies_count: int = 0,
    avg_daily: float = 0.0,
) -> html.Div:
    symbol = "$" if currency == "USD" else currency

    cards = [
        render_kpi_card(
            title="Total Spend",
            value=f"{symbol}{total_cost:,.2f}",
            subtitle=f"Avg {symbol}{avg_daily:,.2f} / day",
            icon="💳",
            color="#38bdf8",
            badge_text="Analyzed",
            badge_color="#38bdf8",
            card_id="kpi-total-spend",
        ),
        render_kpi_card(
            title="Monthly Waste",
            value=f"{symbol}{total_waste:,.2f}",
            subtitle="Idle & orphaned assets",
            icon="⚠️",
            color="#f59e0b",
            badge_text="Audited",
            badge_color="#f59e0b",
            card_id="kpi-monthly-waste",
        ),
        render_kpi_card(
            title="Savings Potential",
            value=f"{symbol}{potential_savings:,.2f}",
            subtitle="Actionable FinOps rules",
            icon="🎯",
            color="#10b981",
            badge_text="Opportunities",
            badge_color="#10b981",
            card_id="kpi-savings-potential",
        ),
        render_kpi_card(
            title="Active Anomalies",
            value=str(anomalies_count),
            subtitle="Cost spikes requiring review",
            icon="🚨",
            color="#ef4444" if anomalies_count > 0 else "#10b981",
            badge_text=f"{anomalies_count} Events",
            badge_color="#ef4444" if anomalies_count > 0 else "#10b981",
            card_id="kpi-active-anomalies",
        ),
    ]

    return html.Div(
        children=cards,
        style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fit, minmax(220px, 1fr))",
            "gap": "16px",
            "marginBottom": "24px",
        },
    )
