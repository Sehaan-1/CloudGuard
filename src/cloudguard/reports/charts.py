from __future__ import annotations

import base64
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from cloudguard.core.models import (
    AnomalyResult,
    CloudResource,
    CostRecord,
    CostSummary,
    Recommendation,
    ScanResult,
    Severity,
)

PALETTE = [
    "#3b82f6",
    "#10b981",
    "#f59e0b",
    "#8b5cf6",
    "#ec4899",
    "#06b6d4",
    "#6366f1",
    "#14b8a6",
    "#f97316",
    "#64748b",
]


def _format_output(png_bytes: bytes, output_format: str) -> str | bytes:
    if output_format == "bytes":
        return png_bytes
    encoded = base64.b64encode(png_bytes).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def _fig_to_png(fig: plt.Figure, dpi: int = 150) -> bytes:
    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=dpi,
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
        edgecolor="none",
    )
    plt.close(fig)
    return buf.getvalue()


def cost_breakdown_pie(
    summary: CostSummary | dict[str, float] | None,
    output_format: str = "base64",
) -> str | bytes:
    if isinstance(summary, CostSummary):
        data = summary.cost_by_service
    elif isinstance(summary, dict):
        data = summary
    else:
        data = {}

    labels = list(data.keys())
    values = list(data.values())

    if not labels or sum(values) == 0:
        labels = ["No Data Available"]
        values = [1.0]

    fig, ax = plt.subplots(figsize=(6.5, 3.4), facecolor="#ffffff")
    colors = (
        PALETTE[: len(labels)]
        if len(labels) <= len(PALETTE)
        else PALETTE * (len(labels) // len(PALETTE) + 1)
    )

    wedges, texts, autotexts = ax.pie(
        values,
        labels=labels if len(labels) <= 5 else None,
        autopct="%1.1f%%" if sum(values) > 1.0 else "",
        pctdistance=0.75,
        startangle=140,
        colors=colors[: len(labels)],
        wedgeprops={"width": 0.45, "edgecolor": "#ffffff", "linewidth": 2},
    )

    for at in autotexts:
        at.set_color("#ffffff")
        at.set_fontsize(8)
        at.set_weight("bold")

    for t in texts:
        t.set_fontsize(8.5)
        t.set_color("#1e293b")

    if len(labels) > 5:
        ax.legend(
            wedges,
            [f"{lbl[:18]}: ${v:,.2f}" for lbl, v in zip(labels, values, strict=False)],
            title="Services",
            loc="center left",
            bbox_to_anchor=(1, 0, 0.5, 1),
            fontsize=7.5,
            frameon=False,
        )

    ax.set_title(
        "Cost Breakdown by Service", fontsize=11, fontweight="bold", color="#0f172a", pad=12
    )
    plt.tight_layout()
    png_bytes = _fig_to_png(fig)
    return _format_output(png_bytes, output_format)


def cost_trend_line(
    data_source: CostSummary | list[CostRecord] | dict[str, float] | None,
    output_format: str = "base64",
) -> str | bytes:
    dates: list[str] = []
    amounts: list[float] = []

    if isinstance(data_source, CostSummary):
        sorted_items = sorted(data_source.daily_totals.items(), key=lambda x: x[0])
        dates = [item[0] for item in sorted_items]
        amounts = [item[1] for item in sorted_items]
    elif isinstance(data_source, dict):
        sorted_items = sorted(data_source.items(), key=lambda x: str(x[0]))
        dates = [str(item[0]) for item in sorted_items]
        amounts = [float(item[1]) for item in sorted_items]
    elif isinstance(data_source, list):
        grouped: dict[str, float] = {}
        for r in data_source:
            if isinstance(r, CostRecord):
                d_str = r.date.isoformat()
                grouped[d_str] = grouped.get(d_str, 0.0) + r.amount
        sorted_items = sorted(grouped.items(), key=lambda x: x[0])
        dates = [item[0] for item in sorted_items]
        amounts = [item[1] for item in sorted_items]

    if not dates:
        dates = ["Day 1", "Day 2", "Day 3"]
        amounts = [0.0, 0.0, 0.0]

    fig, ax = plt.subplots(figsize=(6.5, 3.2), facecolor="#ffffff")
    x_indices = np.arange(len(dates))

    ax.plot(
        x_indices,
        amounts,
        color="#2563eb",
        linewidth=2,
        marker="o",
        markersize=4,
        label="Daily Spend",
    )
    ax.fill_between(x_indices, amounts, color="#3b82f6", alpha=0.15)

    step = max(1, len(dates) // 8)
    ax.set_xticks(x_indices[::step])
    ax.set_xticklabels(
        [dates[i][-5:] if len(dates[i]) >= 5 else dates[i] for i in x_indices[::step]],
        rotation=30,
        fontsize=8,
        color="#475569",
    )
    ax.tick_params(axis="y", labelsize=8, colors="#475569")

    ax.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#cbd5e1")
    ax.spines["bottom"].set_color("#cbd5e1")

    ax.set_ylabel("Daily Spend ($)", fontsize=8.5, fontweight="bold", color="#1e293b")
    ax.set_title("Daily Spending Trend", fontsize=11, fontweight="bold", color="#0f172a", pad=10)
    plt.tight_layout()
    png_bytes = _fig_to_png(fig)
    return _format_output(png_bytes, output_format)


def cost_by_region_bar(
    summary: CostSummary | dict[str, float] | None,
    output_format: str = "base64",
) -> str | bytes:
    if isinstance(summary, CostSummary):
        data = summary.cost_by_region
    elif isinstance(summary, dict):
        data = summary
    else:
        data = {}

    sorted_data = sorted(data.items(), key=lambda x: x[1], reverse=True)[:8]
    regions = [item[0] for item in sorted_data]
    costs = [item[1] for item in sorted_data]

    if not regions:
        regions = ["Global"]
        costs = [0.0]

    fig, ax = plt.subplots(figsize=(6.5, 3.2), facecolor="#ffffff")
    y_pos = np.arange(len(regions))

    bars = ax.barh(y_pos, costs, color="#0ea5e9", edgecolor="#0284c7", height=0.55, align="center")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(regions, fontsize=8.5, color="#1e293b")
    ax.invert_yaxis()

    max_c = max(costs) if costs and max(costs) > 0 else 1.0
    for bar, cost in zip(bars, costs, strict=False):
        ax.text(
            bar.get_width() + (max_c * 0.02),
            bar.get_y() + bar.get_height() / 2,
            f"${cost:,.2f}",
            va="center",
            ha="left",
            fontsize=8,
            color="#0f172a",
            fontweight="bold",
        )

    ax.set_xlim(0, max_c * 1.25)
    ax.grid(axis="x", linestyle="--", alpha=0.5, color="#cbd5e1")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#cbd5e1")
    ax.spines["bottom"].set_color("#cbd5e1")

    ax.set_xlabel("Spend ($)", fontsize=8.5, fontweight="bold", color="#1e293b")
    ax.set_title(
        "Cost Distribution by Cloud Region", fontsize=11, fontweight="bold", color="#0f172a", pad=10
    )
    plt.tight_layout()
    png_bytes = _fig_to_png(fig)
    return _format_output(png_bytes, output_format)


def anomaly_timeline(
    anomalies: list[AnomalyResult] | None,
    output_format: str = "base64",
) -> str | bytes:
    items = anomalies or []

    severity_colors = {
        Severity.LOW: "#3b82f6",
        Severity.MEDIUM: "#f59e0b",
        Severity.HIGH: "#f97316",
        Severity.CRITICAL: "#ef4444",
    }

    fig, ax = plt.subplots(figsize=(6.5, 3.2), facecolor="#ffffff")

    if not items:
        ax.text(
            0.5,
            0.5,
            "No Anomalies Detected in Period",
            ha="center",
            va="center",
            fontsize=11,
            fontweight="bold",
            color="#10b981",
            transform=ax.transAxes,
        )
        ax.set_xticks([])
        ax.set_yticks([])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.spines["bottom"].set_visible(False)
        ax.set_title(
            "Anomaly Detection Timeline", fontsize=11, fontweight="bold", color="#0f172a", pad=10
        )
        plt.tight_layout()
        return _format_output(_fig_to_png(fig), output_format)

    dates = [a.date.isoformat()[-5:] for a in items]
    actuals = [a.actual_cost for a in items]
    expecteds = [a.expected_cost for a in items]
    colors = [severity_colors.get(a.severity, "#ef4444") for a in items]
    sizes = [max(40, min(180, int(abs(a.deviation_score) * 35))) for a in items]

    x_pos = np.arange(len(dates))
    ax.plot(
        x_pos, expecteds, color="#94a3b8", linestyle="--", linewidth=1.5, label="Expected Baseline"
    )
    ax.scatter(
        x_pos,
        actuals,
        c=colors,
        s=sizes,
        edgecolors="#1e293b",
        linewidth=1,
        zorder=5,
        label="Anomaly Spike",
    )

    for i, a in enumerate(items):
        ax.annotate(
            f"{a.service[:12]}\n${a.actual_cost:,.0f}",
            (x_pos[i], actuals[i]),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=7.5,
            fontweight="bold",
            color="#0f172a",
        )

    ax.set_xticks(x_pos)
    ax.set_xticklabels(dates, fontsize=8, color="#475569")
    ax.tick_params(axis="y", labelsize=8, colors="#475569")

    ax.grid(True, linestyle="--", alpha=0.5, color="#cbd5e1")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#cbd5e1")
    ax.spines["bottom"].set_color("#cbd5e1")

    ax.set_ylabel("Cost ($)", fontsize=8.5, fontweight="bold", color="#1e293b")
    ax.set_title(
        "Cost Anomaly Events & Severity", fontsize=11, fontweight="bold", color="#0f172a", pad=10
    )
    ax.legend(loc="upper left", fontsize=7.5, frameon=False)
    plt.tight_layout()
    png_bytes = _fig_to_png(fig)
    return _format_output(png_bytes, output_format)


def utilization_heatmap(
    resources_data: list[CloudResource] | ScanResult | None,
    output_format: str = "base64",
) -> str | bytes:
    resources: list[CloudResource] = []
    if isinstance(resources_data, ScanResult):
        resources.extend(resources_data.idle_resources)
        resources.extend(resources_data.orphaned_storage)
        resources.extend(resources_data.underutilized_vms)
        resources.extend(resources_data.untagged_resources)
    elif isinstance(resources_data, list):
        resources = resources_data

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
        type_counts = {"vm": [0, 1, 2, 3], "storage": [1, 0, 1, 0]}

    categories = list(type_counts.keys())
    buckets = ["<5% (Idle)", "5-20% (Low)", "20-50% (Normal)", "50%+ (High)"]
    matrix = np.array([type_counts[c] for c in categories])

    fig, ax = plt.subplots(figsize=(6.5, 2.8), facecolor="#ffffff")
    cmap = matplotlib.colors.LinearSegmentedColormap.from_list(
        "custom_heat", ["#f8fafc", "#fed7aa", "#f87171", "#dc2626"]
    )
    ax.imshow(matrix, cmap=cmap, aspect="auto")

    ax.set_xticks(np.arange(len(buckets)))
    ax.set_yticks(np.arange(len(categories)))
    ax.set_xticklabels(buckets, fontsize=8, color="#1e293b")
    ax.set_yticklabels(categories, fontsize=8.5, color="#1e293b")

    for i in range(len(categories)):
        for j in range(len(buckets)):
            val = matrix[i, j]
            text_color = "#ffffff" if val > np.max(matrix) * 0.6 else "#1e293b"
            ax.text(
                j,
                i,
                str(val),
                ha="center",
                va="center",
                color=text_color,
                fontweight="bold",
                fontsize=9,
            )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.set_title(
        "Resource Utilization Heatmap by Type",
        fontsize=11,
        fontweight="bold",
        color="#0f172a",
        pad=10,
    )
    plt.tight_layout()
    png_bytes = _fig_to_png(fig)
    return _format_output(png_bytes, output_format)


def savings_waterfall(
    recommendations: list[Recommendation] | None,
    output_format: str = "base64",
) -> str | bytes:
    recs = recommendations or []

    fig, ax = plt.subplots(figsize=(6.5, 3.2), facecolor="#ffffff")

    if not recs:
        ax.text(
            0.5,
            0.5,
            "No Actionable Recommendations Available",
            ha="center",
            va="center",
            fontsize=10,
            fontweight="bold",
            color="#64748b",
            transform=ax.transAxes,
        )
        ax.set_xticks([])
        ax.set_yticks([])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.spines["bottom"].set_visible(False)
        ax.set_title(
            "Potential Monthly Savings", fontsize=11, fontweight="bold", color="#0f172a", pad=10
        )
        plt.tight_layout()
        return _format_output(_fig_to_png(fig), output_format)

    sorted_recs = sorted(recs, key=lambda x: x.estimated_savings, reverse=True)[:7]
    titles = [r.title[:22] + ".." if len(r.title) > 22 else r.title for r in sorted_recs]
    savings = [r.estimated_savings for r in sorted_recs]

    y_pos = np.arange(len(titles))
    bars = ax.barh(
        y_pos, savings, color="#10b981", edgecolor="#047857", height=0.55, align="center"
    )
    ax.set_yticks(y_pos)
    ax.set_yticklabels(titles, fontsize=8, color="#1e293b")
    ax.invert_yaxis()

    max_s = max(savings) if savings and max(savings) > 0 else 1.0
    for bar, val in zip(bars, savings, strict=False):
        ax.text(
            bar.get_width() + (max_s * 0.02),
            bar.get_y() + bar.get_height() / 2,
            f"${val:,.2f}/mo",
            va="center",
            ha="left",
            fontsize=8,
            color="#047857",
            fontweight="bold",
        )

    ax.set_xlim(0, max_s * 1.3)
    ax.grid(axis="x", linestyle="--", alpha=0.5, color="#cbd5e1")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#cbd5e1")
    ax.spines["bottom"].set_color("#cbd5e1")

    ax.set_xlabel("Estimated Monthly Savings ($)", fontsize=8.5, fontweight="bold", color="#1e293b")
    ax.set_title(
        "Top Monthly Savings Opportunities", fontsize=11, fontweight="bold", color="#0f172a", pad=10
    )
    plt.tight_layout()
    png_bytes = _fig_to_png(fig)
    return _format_output(png_bytes, output_format)
