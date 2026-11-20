from __future__ import annotations

from dash import dcc, html


def layout_overview() -> html.Div:
    return html.Div(
        id="overview-page",
        children=[
            html.Div(
                id="overview-kpi-container",
                children=[
                    html.Div(
                        "Loading overview financial metrics...",
                        style={"color": "#94a3b8", "padding": "20px"},
                    )
                ],
            ),
            html.Div(
                children=[
                    html.Div(
                        children=[
                            html.Div(
                                "Daily Spend Trend",
                                style={
                                    "color": "#f8fafc",
                                    "fontSize": "1.1rem",
                                    "fontWeight": "600",
                                    "marginBottom": "12px",
                                },
                            ),
                            dcc.Loading(
                                id="loading-trend",
                                type="circle",
                                color="#38bdf8",
                                children=dcc.Graph(
                                    id="overview-trend-graph",
                                    config={"displayModeBar": True, "displaylogo": False},
                                ),
                            ),
                        ],
                        style={
                            "backgroundColor": "#1e293b",
                            "border": "1px solid #334155",
                            "borderRadius": "12px",
                            "padding": "20px",
                            "flex": "2",
                            "minWidth": "340px",
                        },
                    ),
                    html.Div(
                        children=[
                            html.Div(
                                "Spend by Service",
                                style={
                                    "color": "#f8fafc",
                                    "fontSize": "1.1rem",
                                    "fontWeight": "600",
                                    "marginBottom": "12px",
                                },
                            ),
                            dcc.Loading(
                                id="loading-donut",
                                type="circle",
                                color="#38bdf8",
                                children=dcc.Graph(
                                    id="overview-service-donut-graph",
                                    config={"displayModeBar": True, "displaylogo": False},
                                ),
                            ),
                        ],
                        style={
                            "backgroundColor": "#1e293b",
                            "border": "1px solid #334155",
                            "borderRadius": "12px",
                            "padding": "20px",
                            "flex": "1",
                            "minWidth": "300px",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "flexWrap": "wrap",
                    "gap": "20px",
                    "marginBottom": "24px",
                },
            ),
            html.Div(
                children=[
                    html.Div(
                        children=[
                            html.Div(
                                [
                                    html.Span(
                                        "Detected Spending Anomalies",
                                        style={
                                            "color": "#f8fafc",
                                            "fontSize": "1.1rem",
                                            "fontWeight": "600",
                                        },
                                    ),
                                    html.Span(
                                        "Real-Time Alerts",
                                        style={
                                            "backgroundColor": "rgba(239, 68, 68, 0.2)",
                                            "color": "#f87171",
                                            "border": "1px solid rgba(239, 68, 68, 0.4)",
                                            "borderRadius": "9999px",
                                            "padding": "2px 8px",
                                            "fontSize": "0.75rem",
                                            "fontWeight": "600",
                                            "marginLeft": "10px",
                                        },
                                    ),
                                ],
                                style={
                                    "marginBottom": "12px",
                                    "display": "flex",
                                    "alignItems": "center",
                                },
                            ),
                            dcc.Loading(
                                id="loading-anomalies-list",
                                type="circle",
                                color="#ef4444",
                                children=html.Div(id="overview-anomalies-container"),
                            ),
                        ],
                        style={
                            "backgroundColor": "#1e293b",
                            "border": "1px solid #334155",
                            "borderRadius": "12px",
                            "padding": "20px",
                            "flex": "1",
                            "minWidth": "340px",
                        },
                    ),
                    html.Div(
                        children=[
                            html.Div(
                                [
                                    html.Span(
                                        "Top FinOps Recommendations",
                                        style={
                                            "color": "#f8fafc",
                                            "fontSize": "1.1rem",
                                            "fontWeight": "600",
                                        },
                                    ),
                                    html.Span(
                                        "Quick Wins",
                                        style={
                                            "backgroundColor": "rgba(16, 185, 129, 0.2)",
                                            "color": "#34d399",
                                            "border": "1px solid rgba(16, 185, 129, 0.4)",
                                            "borderRadius": "9999px",
                                            "padding": "2px 8px",
                                            "fontSize": "0.75rem",
                                            "fontWeight": "600",
                                            "marginLeft": "10px",
                                        },
                                    ),
                                ],
                                style={
                                    "marginBottom": "12px",
                                    "display": "flex",
                                    "alignItems": "center",
                                },
                            ),
                            dcc.Loading(
                                id="loading-recommendations-list",
                                type="circle",
                                color="#10b981",
                                children=html.Div(id="overview-recommendations-container"),
                            ),
                        ],
                        style={
                            "backgroundColor": "#1e293b",
                            "border": "1px solid #334155",
                            "borderRadius": "12px",
                            "padding": "20px",
                            "flex": "1",
                            "minWidth": "340px",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "flexWrap": "wrap",
                    "gap": "20px",
                },
            ),
        ],
    )
