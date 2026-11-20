from __future__ import annotations

from datetime import date

from rich import box
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from cloudguard.core.config import Settings
from cloudguard.core.models import (
    AnomalyResult,
    CloudResource,
    CostSummary,
    Recommendation,
    RecommendationPriority,
    ScanResult,
    Severity,
)


def format_currency(amount: float, currency: str = "USD") -> str:
    symbol = "$" if currency.upper() == "USD" else f"{currency} "
    return f"{symbol}{amount:,.2f}"


def format_percentage(pct: float) -> str:
    return f"{pct:.1f}%"


def get_severity_style(severity: Severity | str) -> str:
    val = severity.value if isinstance(severity, Severity) else str(severity).lower()
    if val in ("critical", "urgent"):
        return "bold white on red"
    elif val == "high":
        return "bold red"
    elif val == "medium":
        return "bold yellow"
    elif val == "low":
        return "bold green"
    return "dim"


def make_bar(pct: float, width: int = 15) -> str:
    filled = round((pct / 100.0) * width)
    filled = max(0, min(width, filled))
    empty = width - filled
    return f"[cyan]{'=' * filled}[/cyan][dim]{'-' * empty}[/dim]"


def render_cost_summary_panel(summary: CostSummary, provider: str) -> Panel:
    period_str = f"{summary.period_start.isoformat()} to {summary.period_end.isoformat()}"
    days = max(1, (summary.period_end - summary.period_start).days + 1)

    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(justify="left", style="bold white")
    grid.add_column(justify="right", style="cyan")
    grid.add_column(justify="left", style="bold white")
    grid.add_column(justify="right", style="green")

    grid.add_row(
        "Provider:",
        provider.upper(),
        "Total Spend:",
        format_currency(summary.total_cost, summary.currency),
    )
    grid.add_row(
        "Period:",
        period_str,
        "Daily Average:",
        format_currency(summary.average_daily_cost, summary.currency),
    )
    grid.add_row("Days Analyzed:", str(days), "Records Processed:", f"{summary.record_count:,}")

    return Panel(
        grid,
        title="[bold cyan][*] Cloud Cost Analysis Summary[/bold cyan]",
        subtitle=f"[dim]{summary.record_count} cost line items[/dim]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def render_service_breakdown_table(summary: CostSummary) -> Table:
    table = Table(
        title="[bold]Service Cost Breakdown[/bold]",
        box=box.ROUNDED,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
    )
    table.add_column("Service Name", style="bold white", ratio=4)
    table.add_column("Cost (USD)", justify="right", style="green", ratio=2)
    table.add_column("Share", justify="right", style="magenta", ratio=2)
    table.add_column("Distribution", justify="left", ratio=3)

    sorted_services = sorted(summary.cost_by_service.items(), key=lambda x: x[1], reverse=True)
    total = summary.total_cost if summary.total_cost > 0 else 1.0

    for svc, cost in sorted_services:
        share = (cost / total) * 100.0
        bar = make_bar(share, width=15)
        table.add_row(svc, format_currency(cost), format_percentage(share), bar)

    return table


def render_region_breakdown_table(summary: CostSummary) -> Table:
    table = Table(
        title="[bold]Regional Spend Distribution[/bold]",
        box=box.ROUNDED,
        header_style="bold magenta",
        border_style="dim",
        expand=True,
    )
    table.add_column("Region", style="bold white", ratio=4)
    table.add_column("Cost (USD)", justify="right", style="green", ratio=2)
    table.add_column("Share", justify="right", style="magenta", ratio=2)
    table.add_column("Distribution", justify="left", ratio=3)

    sorted_regions = sorted(summary.cost_by_region.items(), key=lambda x: x[1], reverse=True)
    total = summary.total_cost if summary.total_cost > 0 else 1.0

    for reg, cost in sorted_regions:
        share = (cost / total) * 100.0
        bar = make_bar(share, width=15)
        table.add_row(reg, format_currency(cost), format_percentage(share), bar)

    return table


def render_daily_trends_table(summary: CostSummary, limit: int = 10) -> Table:
    table = Table(
        title=f"[bold]Recent Daily Spend (Last {limit} Days)[/bold]",
        box=box.ROUNDED,
        header_style="bold blue",
        border_style="dim",
        expand=True,
    )
    table.add_column("Date", style="bold white", ratio=3)
    table.add_column("Daily Cost", justify="right", style="green", ratio=3)
    table.add_column("Variance to Avg", justify="right", ratio=3)
    table.add_column("Activity", justify="left", ratio=3)

    sorted_dates = sorted(summary.daily_totals.items(), key=lambda x: x[0], reverse=True)[:limit]
    avg = summary.average_daily_cost if summary.average_daily_cost > 0 else 1.0
    max_daily = max([c for _, c in sorted_dates] + [avg, 1.0])

    for dt_str, cost in reversed(sorted_dates):
        diff_pct = ((cost - avg) / avg) * 100.0 if avg > 0 else 0.0
        if diff_pct > 20:
            diff_style = "bold red"
            diff_text = f"+{diff_pct:.1f}% [^]"
        elif diff_pct < -20:
            diff_style = "bold green"
            diff_text = f"{diff_pct:.1f}% [v]"
        else:
            diff_style = "dim"
            diff_text = f"{diff_pct:+.1f}%"

        bar_pct = (cost / max_daily) * 100.0
        bar = make_bar(bar_pct, width=12)
        table.add_row(
            dt_str, format_currency(cost), f"[{diff_style}]{diff_text}[/{diff_style}]", bar
        )

    return table


def render_anomalies_table(anomalies: list[AnomalyResult]) -> Table:
    table = Table(
        title="[bold red][!] Detected Spending Anomalies[/bold red]",
        box=box.ROUNDED,
        header_style="bold red",
        border_style="red",
        expand=True,
    )
    table.add_column("Severity", justify="center", ratio=2)
    table.add_column("Date", style="bold white", ratio=2)
    table.add_column("Service", style="cyan", ratio=3)
    table.add_column("Actual Spend", justify="right", style="bold red", ratio=2)
    table.add_column("Expected", justify="right", style="dim", ratio=2)
    table.add_column("Deviation", justify="right", ratio=2)
    table.add_column("Detection Method", style="dim", ratio=2)

    for anom in anomalies:
        sev_style = get_severity_style(anom.severity)
        sev_badge = f"[{sev_style}] {anom.severity.value.upper()} [/{sev_style}]"
        dev_str = (
            f"+{anom.deviation_score:.2f} std"
            if anom.deviation_score > 0
            else f"{anom.deviation_score:.2f}"
        )
        table.add_row(
            sev_badge,
            anom.date.isoformat() if isinstance(anom.date, date) else str(anom.date),
            anom.service,
            format_currency(anom.actual_cost),
            format_currency(anom.expected_cost),
            dev_str,
            anom.method,
        )

    return table


def render_scan_summary_panel(scan: ScanResult, provider: str) -> Panel:
    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(justify="left", style="bold white")
    grid.add_column(justify="right", style="cyan")
    grid.add_column(justify="left", style="bold white")
    grid.add_column(justify="right", style="bold red")

    grid.add_row(
        "Provider:",
        provider.upper(),
        "Estimated Monthly Waste:",
        format_currency(scan.total_waste_monthly, scan.currency),
    )
    grid.add_row(
        "Scanned Resources:",
        f"{scan.total_resources_scanned:,}",
        "Annualized Potential Waste:",
        format_currency(scan.total_waste_monthly * 12, scan.currency),
    )
    grid.add_row(
        "Idle Instances:", str(scan.idle_count), "Orphaned Disks/Storage:", str(scan.orphaned_count)
    )
    grid.add_row(
        "Underutilized Workloads:",
        str(scan.underutilized_count),
        "Untagged Assets:",
        str(scan.untagged_count),
    )

    return Panel(
        grid,
        title="[bold yellow][?] Infrastructure Waste & Audit Summary[/bold yellow]",
        subtitle=f"[bold red]{scan.idle_count + scan.orphaned_count + scan.underutilized_count + scan.untagged_count} flagged issues[/bold red]",
        border_style="yellow",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def render_scan_tree(scan: ScanResult) -> Tree:
    p_name = (
        scan.provider.value.upper()
        if hasattr(scan.provider, "value")
        else str(scan.provider).upper()
    )
    root = Tree(f"[bold cyan]{p_name} Infrastructure Waste Tree[/bold cyan]")

    idle_branch = root.add(
        f"[bold yellow]Idle Compute Instances ({len(scan.idle_resources)})[/bold yellow]"
    )
    for r in scan.idle_resources:
        idle_branch.add(
            f"[bold white]{r.name}[/bold white] [dim]({r.id})[/dim] - [yellow]{r.utilization_pct:.1f}% CPU[/yellow] - [bold green]{format_currency(r.monthly_cost)}/mo[/bold green] [dim]({r.region})[/dim]"
        )

    orphan_branch = root.add(
        f"[bold red]Orphaned Storage & Disks ({len(scan.orphaned_storage)})[/bold red]"
    )
    for r in scan.orphaned_storage:
        orphan_branch.add(
            f"[bold white]{r.name}[/bold white] [dim]({r.id})[/dim] - [bold red]Unattached[/bold red] - [bold green]{format_currency(r.monthly_cost)}/mo[/bold green] [dim]({r.region})[/dim]"
        )

    under_branch = root.add(
        f"[bold magenta]Underutilized Workloads ({len(scan.underutilized_vms)})[/bold magenta]"
    )
    for r in scan.underutilized_vms:
        under_branch.add(
            f"[bold white]{r.name}[/bold white] [dim]({r.id})[/dim] - [magenta]{r.utilization_pct:.1f}% Avg Utilization[/magenta] - [bold green]{format_currency(r.monthly_cost)}/mo[/bold green] [dim]({r.region})[/dim]"
        )

    untagged_branch = root.add(
        f"[bold blue]Untagged Assets ({len(scan.untagged_resources)})[/bold blue]"
    )
    for r in scan.untagged_resources:
        untagged_branch.add(
            f"[bold white]{r.name}[/bold white] [dim]({r.id})[/dim] - [blue]{r.type.value if hasattr(r.type, 'value') else str(r.type)}[/blue] - [bold green]{format_currency(r.monthly_cost)}/mo[/bold green] [dim]({r.region})[/dim]"
        )

    return root


def render_resources_table(
    title: str, resources: list[CloudResource], header_color: str = "yellow"
) -> Table:
    table = Table(
        title=f"[bold {header_color}]{title}[/bold {header_color}]",
        box=box.ROUNDED,
        header_style=f"bold {header_color}",
        border_style="dim",
        expand=True,
    )
    table.add_column("Resource Name", style="bold white", ratio=3)
    table.add_column("Resource ID", style="dim", ratio=4)
    table.add_column("Region", style="cyan", ratio=2)
    table.add_column("Utilization", justify="right", ratio=2)
    table.add_column("Monthly Cost", justify="right", style="bold green", ratio=2)
    table.add_column("Status", justify="center", ratio=2)

    for r in resources:
        stat_style = "bold red" if r.is_orphaned else ("bold yellow" if r.is_idle else "dim")
        table.add_row(
            r.name,
            r.id,
            r.region,
            f"{r.utilization_pct:.1f}%",
            format_currency(r.monthly_cost),
            f"[{stat_style}]{r.status.value.upper()}[/{stat_style}]",
        )
    return table


def render_recommendations_table(recommendations: list[Recommendation]) -> Table:
    table = Table(
        title="[bold green][+] FinOps Optimization Recommendations[/bold green]",
        box=box.ROUNDED,
        header_style="bold green",
        border_style="green",
        expand=True,
    )
    table.add_column("Priority", justify="center", ratio=2)
    table.add_column("Recommendation", style="bold white", ratio=4)
    table.add_column("Action", style="cyan", ratio=2)
    table.add_column("Target Resource", style="dim", ratio=3)
    table.add_column("Est. Monthly Savings", justify="right", style="bold green", ratio=3)
    table.add_column("Confidence", justify="right", style="magenta", ratio=2)

    for rec in recommendations:
        pri_style = get_severity_style(
            rec.priority.value
            if isinstance(rec.priority, RecommendationPriority)
            else str(rec.priority)
        )
        pri_badge = f"[{pri_style}] {rec.priority.value.upper()} [/{pri_style}]"
        table.add_row(
            pri_badge,
            rec.title,
            rec.action,
            rec.resource_name or rec.resource_id,
            format_currency(rec.estimated_savings, rec.currency),
            f"{rec.confidence * 100:.0f}%",
        )

    return table


def render_config_table(settings: Settings) -> Table:
    table = Table(
        title="[bold cyan][*] CloudGuard Configuration Settings[/bold cyan]",
        box=box.ROUNDED,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
    )
    table.add_column("Configuration Key", style="bold white", ratio=3)
    table.add_column("Current Value", ratio=5)
    table.add_column("Status / Source", style="dim", ratio=2)

    fields = [
        ("app_env", settings.app_env, "Environment"),
        ("log_level", settings.log_level, "Logging"),
        ("default_provider", settings.default_provider, "Default Provider"),
        ("data_dir", str(settings.data_dir), "Storage Path"),
        (
            "azure_subscription_id",
            settings.azure_subscription_id or "[dim]Not configured[/dim]",
            "Azure Credential",
        ),
        (
            "azure_tenant_id",
            settings.azure_tenant_id or "[dim]Not configured[/dim]",
            "Azure Credential",
        ),
        (
            "azure_client_id",
            settings.azure_client_id or "[dim]Not configured[/dim]",
            "Azure Credential",
        ),
        (
            "azure_client_secret",
            "********" if settings.azure_client_secret else "[dim]Not configured[/dim]",
            "Azure Secret",
        ),
        ("aws_default_region", settings.aws_default_region, "AWS Region"),
        (
            "aws_access_key_id",
            settings.aws_access_key_id or "[dim]Not configured[/dim]",
            "AWS Credential",
        ),
        (
            "aws_secret_access_key",
            "********" if settings.aws_secret_access_key else "[dim]Not configured[/dim]",
            "AWS Secret",
        ),
        ("zscore_threshold", str(settings.zscore_threshold), "Anomaly Detection"),
        ("iqr_multiplier", str(settings.iqr_multiplier), "Anomaly Detection"),
        ("idle_cpu_threshold_pct", f"{settings.idle_cpu_threshold_pct}%", "Waste Detection"),
        ("idle_period_days", f"{settings.idle_period_days} days", "Waste Detection"),
        ("orphaned_storage_days", f"{settings.orphaned_storage_days} days", "Waste Detection"),
        (
            "underutilized_vm_threshold_pct",
            f"{settings.underutilized_vm_threshold_pct}%",
            "Waste Detection",
        ),
        ("database_url", settings.database_url, "Persistence"),
        ("redis_url", settings.redis_url, "Cache"),
    ]

    for key, val, src in fields:
        table.add_row(key, str(val), src)

    return table


def render_markdown_summary(markdown_text: str) -> Panel:
    return Panel(
        Markdown(markdown_text),
        title="[bold cyan][#] Executive Takeaways[/bold cyan]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )
