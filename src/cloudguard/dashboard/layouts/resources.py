from __future__ import annotations

from dash import dash_table, dcc, html


def layout_resources() -> html.Div:
    return html.Div(
        id="resources-page",
        children=[
            html.Div(
                id="resource-metrics-container",
                style={"marginBottom": "24px"},
            ),
            html.Div(
                children=[
                    html.Div(
                        children=[
                            html.Div(
                                "Resource Efficiency Heatmap by Type",
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
                                    id="resource-heatmap-graph",
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
                                "Spend vs. Utilization Efficiency (Bubble)",
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
                                    id="resource-bubble-graph",
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
                        children=[
                            html.Div(
                                "Resource Inventory & Waste Audit",
                                style={
                                    "color": "#f8fafc",
                                    "fontSize": "1.1rem",
                                    "fontWeight": "600",
                                },
                            ),
                            dcc.RadioItems(
                                id="resource-table-filter",
                                options=[
                                    {"label": " All Scanned", "value": "all"},
                                    {"label": " Idle Compute", "value": "idle"},
                                    {"label": " Orphaned Storage", "value": "orphaned"},
                                    {"label": " Underutilized", "value": "underutilized"},
                                    {"label": " Untagged", "value": "untagged"},
                                ],
                                value="all",
                                inline=True,
                                style={"color": "#cbd5e1", "fontSize": "0.9rem"},
                                inputStyle={"marginRight": "4px", "marginLeft": "12px"},
                            ),
                        ],
                        style={
                            "display": "flex",
                            "justifyContent": "space-between",
                            "alignItems": "center",
                            "marginBottom": "16px",
                            "flexWrap": "wrap",
                            "gap": "10px",
                        },
                    ),
                    dcc.Loading(
                        type="circle",
                        color="#38bdf8",
                        children=dash_table.DataTable(
                            id="resource-inventory-table",
                            columns=[
                                {"name": "Resource Name", "id": "name"},
                                {"name": "Type", "id": "type"},
                                {"name": "Provider", "id": "provider"},
                                {"name": "Region", "id": "region"},
                                {"name": "Status", "id": "status"},
                                {"name": "Utilization", "id": "utilization_pct"},
                                {"name": "Est. Cost/Mo ($)", "id": "monthly_cost"},
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
                                },
                                {
                                    "if": {
                                        "filter_query": '{status} eq "idle" || {status} eq "IDLE"'
                                    },
                                    "color": "#f87171",
                                    "fontWeight": "bold",
                                },
                                {
                                    "if": {
                                        "filter_query": '{status} eq "orphaned" || {status} eq "ORPHANED"'
                                    },
                                    "color": "#fb923c",
                                    "fontWeight": "bold",
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
