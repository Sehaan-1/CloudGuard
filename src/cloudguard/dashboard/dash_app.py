from __future__ import annotations

from datetime import date, timedelta

import dash
from dash import Input, Output, dcc, html

from cloudguard.dashboard.callbacks import register_callbacks
from cloudguard.dashboard.layouts.anomalies import layout_anomalies
from cloudguard.dashboard.layouts.cost_explorer import layout_cost_explorer
from cloudguard.dashboard.layouts.overview import layout_overview
from cloudguard.dashboard.layouts.resources import layout_resources


def create_dash_app(requests_pathname_prefix: str = "/") -> dash.Dash:
    app = dash.Dash(
        __name__,
        requests_pathname_prefix=requests_pathname_prefix,
        suppress_callback_exceptions=True,
        title="CloudGuard | FinOps Observability Platform",
    )

    today = date.today()
    default_start = today - timedelta(days=30)

    header = html.Header(
        children=[
            html.Div(
                children=[
                    html.Div(
                        children=[
                            html.Span("🛡️", style={"fontSize": "1.8rem", "marginRight": "10px"}),
                            html.Span(
                                "CloudGuard",
                                style={
                                    "fontSize": "1.4rem",
                                    "fontWeight": "800",
                                    "color": "#f8fafc",
                                    "letterSpacing": "-0.02em",
                                },
                            ),
                            html.Span(
                                "OBSERVABILITY",
                                style={
                                    "backgroundColor": "#0284c7",
                                    "color": "#f0f9ff",
                                    "fontSize": "0.65rem",
                                    "fontWeight": "800",
                                    "letterSpacing": "0.08em",
                                    "padding": "2px 6px",
                                    "borderRadius": "4px",
                                    "marginLeft": "8px",
                                },
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center"},
                    ),
                    html.Nav(
                        children=[
                            dcc.Link("Overview", href="/", id="nav-overview", className="nav-btn"),
                            dcc.Link(
                                "Cost Explorer",
                                href="/cost-explorer",
                                id="nav-cost",
                                className="nav-btn",
                            ),
                            dcc.Link(
                                "Anomalies",
                                href="/anomalies",
                                id="nav-anomalies",
                                className="nav-btn",
                            ),
                            dcc.Link(
                                "Resources",
                                href="/resources",
                                id="nav-resources",
                                className="nav-btn",
                            ),
                        ],
                        style={"display": "flex", "gap": "8px", "marginLeft": "24px"},
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "flexWrap": "wrap",
                    "gap": "16px",
                },
            ),
            html.Div(
                children=[
                    html.Div(
                        children=[
                            html.Label(
                                "Provider",
                                style={
                                    "color": "#94a3b8",
                                    "fontSize": "0.75rem",
                                    "fontWeight": "600",
                                    "marginRight": "6px",
                                },
                            ),
                            dcc.Dropdown(
                                id="global-provider-select",
                                options=[
                                    {"label": "Mock / Demo", "value": "mock"},
                                    {"label": "Azure Cloud", "value": "azure"},
                                    {"label": "AWS Cloud", "value": "aws"},
                                    {"label": "All Providers", "value": "all"},
                                ],
                                value="mock",
                                clearable=False,
                                style={
                                    "minWidth": "140px",
                                    "fontSize": "0.85rem",
                                    "color": "#0f172a",
                                },
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center"},
                    ),
                    html.Div(
                        children=[
                            html.Label(
                                "Date Range",
                                style={
                                    "color": "#94a3b8",
                                    "fontSize": "0.75rem",
                                    "fontWeight": "600",
                                    "marginRight": "6px",
                                },
                            ),
                            dcc.DatePickerRange(
                                id="global-date-picker",
                                start_date=default_start,
                                end_date=today,
                                max_date_allowed=today + timedelta(days=1),
                                display_format="YYYY-MM-DD",
                                style={"fontSize": "0.85rem"},
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center"},
                    ),
                    html.Div(
                        children=[
                            html.Label(
                                "Auto Refresh",
                                style={
                                    "color": "#94a3b8",
                                    "fontSize": "0.75rem",
                                    "fontWeight": "600",
                                    "marginRight": "6px",
                                },
                            ),
                            dcc.Dropdown(
                                id="global-refresh-select",
                                options=[
                                    {"label": "Off", "value": 0},
                                    {"label": "30s", "value": 30000},
                                    {"label": "1m", "value": 60000},
                                    {"label": "5m", "value": 300000},
                                ],
                                value=0,
                                clearable=False,
                                style={
                                    "minWidth": "90px",
                                    "fontSize": "0.85rem",
                                    "color": "#0f172a",
                                },
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center"},
                    ),
                ],
                style={
                    "display": "flex",
                    "alignItems": "center",
                    "gap": "14px",
                    "flexWrap": "wrap",
                },
            ),
        ],
        style={
            "backgroundColor": "#0f172a",
            "borderBottom": "1px solid #1e293b",
            "padding": "12px 24px",
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "flexWrap": "wrap",
            "gap": "16px",
            "position": "sticky",
            "top": "0",
            "zIndex": "1000",
        },
    )

    app.layout = html.Div(
        children=[
            dcc.Location(id="url", refresh=False),
            dcc.Interval(id="auto-refresh-interval", interval=60000, disabled=True, n_intervals=0),
            header,
            html.Main(
                id="page-content",
                style={
                    "maxWidth": "1440px",
                    "margin": "0 auto",
                    "padding": "24px 20px",
                },
            ),
        ],
        style={
            "backgroundColor": "#0b0f19",
            "minHeight": "100vh",
            "color": "#f8fafc",
            "fontFamily": "Segoe UI, -apple-system, BlinkMacSystemFont, Roboto, sans-serif",
        },
    )

    @app.callback(
        Output("auto-refresh-interval", "disabled"),
        Output("auto-refresh-interval", "interval"),
        Input("global-refresh-select", "value"),
    )
    def handle_refresh_interval(val: int | None):
        if not val or val == 0:
            return True, 60000
        return False, val

    @app.callback(
        Output("page-content", "children"),
        Input("url", "pathname"),
    )
    def render_page_content(pathname: str | None) -> html.Div:
        path = (pathname or "/").rstrip("/")
        if path in ("/cost-explorer", "cost-explorer"):
            return layout_cost_explorer()
        if path in ("/anomalies", "anomalies"):
            return layout_anomalies()
        if path in ("/resources", "resources"):
            return layout_resources()
        return layout_overview()

    @app.callback(
        Output("nav-overview", "style"),
        Output("nav-cost", "style"),
        Output("nav-anomalies", "style"),
        Output("nav-resources", "style"),
        Input("url", "pathname"),
    )
    def update_active_nav(pathname: str | None):
        path = (pathname or "/").rstrip("/")

        base_style = {
            "color": "#94a3b8",
            "textDecoration": "none",
            "padding": "6px 14px",
            "borderRadius": "6px",
            "fontSize": "0.9rem",
            "fontWeight": "600",
            "transition": "all 0.2s",
        }
        active_style = {
            **base_style,
            "backgroundColor": "#1e293b",
            "color": "#38bdf8",
            "boxShadow": "0 1px 3px rgba(0, 0, 0, 0.3)",
        }

        s_ov = active_style if path in ("", "/") else base_style
        s_cost = active_style if path in ("/cost-explorer", "cost-explorer") else base_style
        s_anom = active_style if path in ("/anomalies", "anomalies") else base_style
        s_res = active_style if path in ("/resources", "resources") else base_style

        return s_ov, s_cost, s_anom, s_res

    register_callbacks(app)
    return app
