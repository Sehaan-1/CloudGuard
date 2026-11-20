from __future__ import annotations

import dash
from dash import Input, Output, html

from cloudguard.dashboard.components.charts import (
    create_cost_vs_utilization_bubble_figure,
    create_utilization_heatmap_figure,
)
from cloudguard.dashboard.components.kpi_cards import render_kpi_card
from cloudguard.dashboard.services import dashboard_service, run_async


def register_resource_callbacks(app: dash.Dash) -> None:

    @app.callback(
        [
            Output("resource-metrics-container", "children"),
            Output("resource-heatmap-graph", "figure"),
            Output("resource-bubble-graph", "figure"),
            Output("resource-inventory-table", "data"),
        ],
        [
            Input("global-provider-select", "value"),
            Input("resource-table-filter", "value"),
            Input("auto-refresh-interval", "n_intervals"),
        ],
    )
    def update_resource_efficiency(
        provider: str | None,
        table_filter: str | None,
        _n: int,
    ):
        p = provider or "mock"

        async def _fetch():
            return await dashboard_service.get_scan_result(p)

        scan = run_async(_fetch())

        kpi_row = html.Div(
            children=[
                render_kpi_card(
                    title="Idle Compute",
                    value=str(scan.idle_count),
                    subtitle="VMs <5% CPU",
                    icon="💤",
                    color="#f59e0b",
                    badge_text=f"{scan.idle_count} Hosts",
                    badge_color="#f59e0b",
                ),
                render_kpi_card(
                    title="Orphaned Disks",
                    value=str(scan.orphaned_count),
                    subtitle="Unattached Storage",
                    icon="💾",
                    color="#ef4444",
                    badge_text=f"{scan.orphaned_count} Disks",
                    badge_color="#ef4444",
                ),
                render_kpi_card(
                    title="Underutilized",
                    value=str(scan.underutilized_count),
                    subtitle="Instances <20% CPU",
                    icon="📉",
                    color="#a855f7",
                    badge_text=f"{scan.underutilized_count} VMs",
                    badge_color="#a855f7",
                ),
                render_kpi_card(
                    title="Untagged Assets",
                    value=str(scan.untagged_count),
                    subtitle="Missing Cost Centers",
                    icon="🏷️",
                    color="#38bdf8",
                    badge_text=f"{scan.untagged_count} Items",
                    badge_color="#38bdf8",
                ),
            ],
            style={
                "display": "grid",
                "gridTemplateColumns": "repeat(auto-fit, minmax(220px, 1fr))",
                "gap": "16px",
            },
        )

        all_res = []
        all_res.extend(scan.idle_resources)
        all_res.extend(scan.orphaned_storage)
        all_res.extend(scan.underutilized_vms)
        all_res.extend(scan.untagged_resources)

        seen_ids = set()
        deduped_res = []
        for r in all_res:
            if r.id not in seen_ids:
                seen_ids.add(r.id)
                deduped_res.append(r)

        heatmap_fig = create_utilization_heatmap_figure(deduped_res)
        bubble_fig = create_cost_vs_utilization_bubble_figure(deduped_res)

        f = table_filter or "all"
        if f == "idle":
            target_list = scan.idle_resources
        elif f == "orphaned":
            target_list = scan.orphaned_storage
        elif f == "underutilized":
            target_list = scan.underutilized_vms
        elif f == "untagged":
            target_list = scan.untagged_resources
        else:
            target_list = deduped_res

        table_data = [
            {
                "name": r.name,
                "type": r.type.value if hasattr(r.type, "value") else str(r.type),
                "provider": (
                    r.provider.value if hasattr(r.provider, "value") else str(r.provider)
                ).upper(),
                "region": r.region,
                "status": (r.status.value if hasattr(r.status, "value") else str(r.status)).upper(),
                "utilization_pct": f"{r.utilization_pct:.1f}%",
                "monthly_cost": f"${r.monthly_cost:,.2f}",
            }
            for r in target_list
        ]

        return kpi_row, heatmap_fig, bubble_fig, table_data
