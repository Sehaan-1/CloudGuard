from __future__ import annotations

from dash import dash_table, dcc, html


def layout_anomalies() -> html.Div:
    return html.Div(
        id="anomalies-page",
        children=[
            html.Div(
                children=[
                    html.Div(
                        children=[
                            html.Label(
                                "Detection Strategy",
                                style={
                                    "color": "#94a3b8",
                                    "fontSize": "0.8rem",
                                    "fontWeight": "600",
                                    "display": "block",
                                    "marginBottom": "6px",
                                },
                            ),
                            dcc.Dropdown(
                                id="anomaly-method-dropdown",
                                options=[
                                    {
                                        "label": "Composite (Multi-Strategy Consensus)",
                                        "value": "composite",
                                    },
                                    {"label": "Z-Score (Standard Deviations)", "value": "zscore"},
                                    {"label": "IQR (Interquartile Range)", "value": "iqr"},
                                    {
                                        "label": "Rolling Window (Dynamic Baseline)",
                                        "value": "rolling",
                                    },
                                ],
                                value="composite",
                                clearable=False,
                                style={
                                    "backgroundColor": "#0f172a",
                                    "color": "#0f172a",
                                    "minWidth": "240px",
                                },
                            ),
                        ],
                        style={"flex": "1", "minWidth": "220px"},
                    ),
                    html.Div(
                        children=[
                            html.Label(
                                "Severity Filter",
                                style={
                                    "color": "#94a3b8",
                                    "fontSize": "0.8rem",
                                    "fontWeight": "600",
                                    "display": "block",
                                    "marginBottom": "6px",
                                },
                            ),
                            dcc.Dropdown(
                                id="anomaly-severity-filter",
                                options=[
                                    {"label": "All Severities", "value": "all"},
                                    {"label": "Critical Only", "value": "critical"},
                                    {"label": "High & Critical", "value": "high"},
                                    {"label": "Medium & Above", "value": "medium"},
                                    {"label": "Low", "value": "low"},
                                ],
                                value="all",
                                clearable=False,
                                style={
                                    "backgroundColor": "#0f172a",
                                    "color": "#0f172a",
                                    "minWidth": "180px",
                                },
                            ),
                        ],
                        style={"flex": "1", "minWidth": "180px"},
                    ),
                    html.Div(
                        children=[
                            html.Label(
                                "Detection Sensitivity (Threshold: 1.0 - 5.0)",
                                style={
                                    "color": "#94a3b8",
                                    "fontSize": "0.8rem",
                                    "fontWeight": "600",
                                    "display": "block",
                                    "marginBottom": "6px",
                                },
                            ),
                            dcc.Slider(
                                id="anomaly-sensitivity-slider",
                                min=1.0,
                                max=5.0,
                                step=0.5,
                                value=3.0,
                                marks={1.0: "1.0", 2.0: "2.0", 3.0: "3.0", 4.0: "4.0", 5.0: "5.0"},
                                tooltip={"placement": "bottom", "always_visible": False},
                            ),
                        ],
                        style={"flex": "2", "minWidth": "240px"},
                    ),
                ],
                style={
                    "backgroundColor": "#1e293b",
                    "border": "1px solid #334155",
                    "borderRadius": "12px",
                    "padding": "16px 20px",
                    "display": "flex",
                    "flexWrap": "wrap",
                    "gap": "20px",
                    "alignItems": "center",
                    "marginBottom": "24px",
                },
            ),
            html.Div(
                children=[
                    html.Div(
                        "Spending Spike Timeline & Statistical Bounds",
                        style={
                            "color": "#f8fafc",
                            "fontSize": "1.1rem",
                            "fontWeight": "600",
                            "marginBottom": "12px",
                        },
                    ),
                    dcc.Loading(
                        type="circle",
                        color="#ef4444",
                        children=dcc.Graph(
                            id="anomaly-timeline-graph",
                            config={"displayModeBar": True, "displaylogo": False},
                        ),
                    ),
                ],
                style={
                    "backgroundColor": "#1e293b",
                    "border": "1px solid #334155",
                    "borderRadius": "12px",
                    "padding": "20px",
                    "marginBottom": "24px",
                },
            ),
            html.Div(
                children=[
                    html.Div(
                        "Detected Anomaly Incidents",
                        style={
                            "color": "#f8fafc",
                            "fontSize": "1.1rem",
                            "fontWeight": "600",
                            "marginBottom": "16px",
                        },
                    ),
                    dcc.Loading(
                        type="circle",
                        color="#ef4444",
                        children=dash_table.DataTable(
                            id="anomaly-detail-table",
                            columns=[
                                {"name": "Date", "id": "date"},
                                {"name": "Service", "id": "service"},
                                {"name": "Expected ($)", "id": "expected_cost"},
                                {"name": "Actual ($)", "id": "actual_cost"},
                                {"name": "Deviation", "id": "deviation_score"},
                                {"name": "Severity", "id": "severity"},
                                {"name": "Method", "id": "method"},
                                {"name": "Description", "id": "description"},
                            ],
                            page_size=10,
                            sort_action="native",
                            style_header={
                                "backgroundColor": "#0f172a",
                                "color": "#f8fafc",
                                "fontWeight": "bold",
                                "border": "1px solid #334155",
                            },
                            style_cell={
                                "backgroundColor": "#1e293b",
                                "color": "#cbd5e1",
                                "border": "1px solid #334155",
                                "fontFamily": "Segoe UI, -apple-system, sans-serif",
                                "fontSize": "0.85rem",
                                "padding": "10px",
                                "whiteSpace": "normal",
                                "height": "auto",
                            },
                            style_data_conditional=[
                                {
                                    "if": {"row_index": "odd"},
                                    "backgroundColor": "#182234",
                                },
                                {
                                    "if": {
                                        "filter_query": '{severity} eq "CRITICAL" || {severity} eq "critical"'
                                    },
                                    "color": "#f87171",
                                    "fontWeight": "bold",
                                },
                                {
                                    "if": {
                                        "filter_query": '{severity} eq "HIGH" || {severity} eq "high"'
                                    },
                                    "color": "#fb923c",
                                    "fontWeight": "bold",
                                },
                                {
                                    "if": {
                                        "filter_query": '{severity} eq "MEDIUM" || {severity} eq "medium"'
                                    },
                                    "color": "#fbbf24",
                                },
                            ],
                        ),
                    ),
                ],
                style={
                    "backgroundColor": "#1e293b",
                    "border": "1px solid #334155",
                    "borderRadius": "12px",
                    "padding": "20px",
                },
            ),
        ],
    )
