from __future__ import annotations

from dash import dash_table, dcc, html


def layout_cost_explorer() -> html.Div:
    return html.Div(
        id="cost-explorer-page",
        children=[
            html.Div(
                children=[
                    html.Div(
                        children=[
                            html.Div(
                                "Spending Hierarchy (Sunburst)",
                                style={
                                    "color": "#f8fafc",
                                    "fontSize": "1.1rem",
                                    "fontWeight": "600",
                                    "marginBottom": "12px",
                                },
                            ),
                            dcc.Loading(
                                type="circle",
                                color="#38bdf8",
                                children=dcc.Graph(
                                    id="cost-sunburst-graph",
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
                            "minWidth": "340px",
                        },
                    ),
                    html.Div(
                        children=[
                            html.Div(
                                "Cost by Cloud Region",
                                style={
                                    "color": "#f8fafc",
                                    "fontSize": "1.1rem",
                                    "fontWeight": "600",
                                    "marginBottom": "12px",
                                },
                            ),
                            dcc.Loading(
                                type="circle",
                                color="#38bdf8",
                                children=dcc.Graph(
                                    id="cost-region-graph",
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
                            "minWidth": "340px",
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
                        "Daily Spend Composition by Service",
                        style={
                            "color": "#f8fafc",
                            "fontSize": "1.1rem",
                            "fontWeight": "600",
                            "marginBottom": "12px",
                        },
                    ),
                    dcc.Loading(
                        type="circle",
                        color="#38bdf8",
                        children=dcc.Graph(
                            id="cost-stacked-graph",
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
                        children=[
                            html.Div(
                                "Cost Line Items Data",
                                style={
                                    "color": "#f8fafc",
                                    "fontSize": "1.1rem",
                                    "fontWeight": "600",
                                },
                            ),
                            html.Button(
                                "📥 Export CSV",
                                id="btn-export-cost-csv",
                                style={
                                    "backgroundColor": "#334155",
                                    "color": "#f8fafc",
                                    "border": "1px solid #475569",
                                    "borderRadius": "6px",
                                    "padding": "6px 14px",
                                    "fontSize": "0.85rem",
                                    "cursor": "pointer",
                                    "fontWeight": "600",
                                },
                            ),
                            dcc.Download(id="download-cost-csv"),
                        ],
                        style={
                            "display": "flex",
                            "justifyContent": "space-between",
                            "alignItems": "center",
                            "marginBottom": "16px",
                        },
                    ),
                    dcc.Loading(
                        type="circle",
                        color="#38bdf8",
                        children=dash_table.DataTable(
                            id="cost-data-table",
                            columns=[
                                {"name": "Date", "id": "date"},
                                {"name": "Service", "id": "service"},
                                {"name": "Provider", "id": "provider"},
                                {"name": "Region", "id": "region"},
                                {"name": "Usage Type", "id": "usage_type"},
                                {"name": "Amount ($)", "id": "amount"},
                            ],
                            page_size=10,
                            sort_action="native",
                            filter_action="native",
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
                            },
                            style_data_conditional=[
                                {
                                    "if": {"row_index": "odd"},
                                    "backgroundColor": "#182234",
                                }
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
