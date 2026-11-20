from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        with contextlib.suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        with contextlib.suppress(Exception):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from cloudguard.analysis.anomaly_detector import CompositeDetector
from cloudguard.analysis.iqr_detector import IQRDetector
from cloudguard.analysis.rolling_detector import RollingWindowDetector
from cloudguard.analysis.zscore_detector import ZScoreDetector
from cloudguard.cli.formatters import (
    format_currency,
    render_anomalies_table,
    render_config_table,
    render_cost_summary_panel,
    render_daily_trends_table,
    render_markdown_summary,
    render_recommendations_table,
    render_region_breakdown_table,
    render_resources_table,
    render_scan_summary_panel,
    render_scan_tree,
    render_service_breakdown_table,
)
from cloudguard.core.config import get_settings
from cloudguard.core.exceptions import CloudGuardError
from cloudguard.core.models import (
    AnomalyResult,
    CloudProviderType,
    CostRecord,
    CostSummary,
    Granularity,
    Recommendation,
    ScanResult,
)
from cloudguard.engine import CostAnalysisEngine
from cloudguard.reports.generator import PDFReportGenerator

app = typer.Typer(
    name="cloudguard",
    help="Intelligent Cloud Cost Optimizer & FinOps Observability Platform",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        from cloudguard import __version__

        console.print(
            f"[bold cyan]CloudGuard[/bold cyan] version [bold green]{__version__}[/bold green]"
        )
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-v",
        help="Show CloudGuard version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    pass


def parse_date(date_str: str | None, default_date: date) -> date:
    if not date_str:
        return default_date
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.fromisoformat(date_str).date()
        except ValueError:
            console.print(
                f"[bold red]Invalid date format:[/bold red] '{date_str}'. Please use YYYY-MM-DD."
            )
            raise typer.Exit(code=1) from None


@app.command(name="version", help="Display CloudGuard version and runtime environment.")
def version_cmd() -> None:
    from cloudguard import __version__

    settings = get_settings()

    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(style="bold white")
    grid.add_column(style="cyan")
    grid.add_row("CloudGuard Version:", __version__)
    grid.add_row("Python Version:", sys.version.split()[0])
    grid.add_row("Environment:", settings.app_env)
    grid.add_row("Default Provider:", settings.default_provider)

    console.print(
        Panel(
            grid,
            title="[bold cyan][*] CloudGuard FinOps Platform[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


@app.command(name="analyze", help="Analyze cloud cost consumption and detect spending anomalies.")
def analyze(
    provider: str = typer.Option(
        "mock", "--provider", "-p", help="Cloud provider (azure, aws, mock, all)"
    ),
    start: str | None = typer.Option(
        None, "--start", "-s", help="Start date (YYYY-MM-DD), default 30 days ago"
    ),
    end: str | None = typer.Option(
        None, "--end", "-e", help="End date (YYYY-MM-DD), default today"
    ),
    granularity: str = typer.Option(
        "daily", "--granularity", "-g", help="Granularity (daily, monthly, hourly)"
    ),
    anomalies: bool = typer.Option(
        True, "--anomalies/--no-anomalies", help="Detect spending anomalies"
    ),
    parallel: bool = typer.Option(
        False, "--parallel/--no-parallel", help="Use parallel analysis engine"
    ),
    output: str = typer.Option(
        "table", "--output", "-o", help="Output format: table, json, markdown"
    ),
) -> None:
    async def _run() -> None:
        today = date.today()
        default_start = today - timedelta(days=30)
        start_dt = parse_date(start, default_start)
        end_dt = parse_date(end, today)

        if start_dt > end_dt:
            console.print("[bold red]Error:[/bold red] Start date cannot be after end date.")
            raise typer.Exit(code=1)

        try:
            gran_enum = Granularity(granularity.lower())
        except ValueError:
            gran_enum = Granularity.DAILY

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[cyan]Analyzing cloud costs for {provider.upper()}...", total=100
            )

            settings = get_settings()
            records: list[CostRecord] = []
            detected_anomalies: list[AnomalyResult] = []

            progress.update(task, advance=20, description="[cyan]Connecting to provider...")

            if provider.lower() == "all":
                provider_names = []
                if settings.has_azure_credentials:
                    provider_names.append("azure")
                if settings.has_aws_credentials:
                    provider_names.append("aws")
                if not provider_names:
                    provider_names = ["mock"]

                for p_name in provider_names:
                    with contextlib.suppress(Exception):
                        eng = CostAnalysisEngine(provider=p_name, settings=settings)
                        p_records = await eng.get_cost_data(start_dt, end_dt, gran_enum)
                        records.extend(p_records)
                if not records:
                    eng = CostAnalysisEngine(provider="mock", settings=settings)
                    records = await eng.get_cost_data(start_dt, end_dt, gran_enum)
                summary = CostSummary.from_records(records, start_dt, end_dt)
            else:
                eng = CostAnalysisEngine(provider=provider, settings=settings)
                if parallel:
                    progress.update(
                        task,
                        advance=20,
                        description="[cyan]Executing parallel chunked processing...",
                    )
                    p_result = await eng.analyze_parallel(start_dt, end_dt)
                    summary = p_result.summary
                    records = await eng.get_cost_data(start_dt, end_dt, gran_enum)
                else:
                    progress.update(
                        task, advance=30, description="[cyan]Querying cost line items..."
                    )
                    records = await eng.get_cost_data(start_dt, end_dt, gran_enum)
                    summary = await eng.get_cost_summary(start_dt, end_dt)

            progress.update(
                task, advance=25, description="[cyan]Processing anomalies and metrics..."
            )
            if anomalies and records:
                detector = CompositeDetector(
                    strategies=[
                        ZScoreDetector(threshold=settings.anomaly_zscore_threshold),
                        IQRDetector(multiplier=settings.anomaly_iqr_multiplier),
                        RollingWindowDetector(window=14, std_dev_multiplier=2.5),
                    ],
                    min_votes=1,
                )
                detected_anomalies = detector.detect(records)

            progress.update(task, advance=25, description="[green]Analysis complete.")

        if output.lower() == "json":
            out_data = {
                "summary": summary.model_dump(mode="json"),
                "anomalies": [a.model_dump(mode="json") for a in detected_anomalies],
            }
            console.print_json(json.dumps(out_data))
            return

        if output.lower() == "markdown":
            md_text = f"""# CloudGuard Cost Analysis Report
- **Provider**: {provider.upper()}
- **Period**: {start_dt.isoformat()} to {end_dt.isoformat()}
- **Total Spend**: {format_currency(summary.total_cost, summary.currency)}
- **Daily Average**: {format_currency(summary.average_daily_cost, summary.currency)}
- **Records Processed**: {summary.record_count:,}
- **Anomalies Detected**: {len(detected_anomalies)}

## Top Services
"""
            for svc, c in summary.top_services:
                md_text += f"- **{svc}**: {format_currency(c)}\n"
            console.print(render_markdown_summary(md_text))
            return

        console.print()
        console.print(render_cost_summary_panel(summary, provider))
        console.print()

        col1 = render_service_breakdown_table(summary)
        col2 = render_region_breakdown_table(summary)
        console.print(col1)
        console.print()
        console.print(col2)
        console.print()

        if summary.daily_totals:
            console.print(render_daily_trends_table(summary, limit=10))
            console.print()

        if detected_anomalies:
            console.print(render_anomalies_table(detected_anomalies))
            console.print()
        elif anomalies:
            console.print(
                "[bold green][v] No spending anomalies detected in the selected period.[/bold green]"
            )
            console.print()

    try:
        asyncio.run(_run())
    except CloudGuardError as e:
        console.print(f"[bold red]CloudGuard Error:[/bold red] {e}")
        raise typer.Exit(code=1) from None
    except Exception as e:
        console.print(f"[bold red]Execution Error:[/bold red] {e}")
        raise typer.Exit(code=1) from None


@app.command(name="scan", help="Scan cloud infrastructure for idle VMs, orphaned disks, and waste.")
def scan(
    provider: str = typer.Option(
        "mock", "--provider", "-p", help="Cloud provider (azure, aws, mock, all)"
    ),
    scan_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Comma-separated scan filter (e.g. idle-vms,orphaned-storage,underutilized-vms,untagged-resources,all)",
    ),
    idle_threshold: float | None = typer.Option(
        None, "--idle-threshold", help="Idle CPU threshold percentage"
    ),
    orphaned_days: int | None = typer.Option(
        None, "--orphaned-days", help="Days unattached before marked orphaned"
    ),
    underutilized_threshold: float | None = typer.Option(
        None, "--underutilized-threshold", help="Underutilized CPU threshold percentage"
    ),
    recommendations: bool = typer.Option(
        True, "--recommendations/--no-recommendations", help="Generate optimization recommendations"
    ),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table, json, tree"),
) -> None:
    async def _run() -> None:
        settings = get_settings()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[yellow]Scanning infrastructure on {provider.upper()}...", total=100
            )

            if provider.lower() == "all":
                provider_names = []
                if settings.has_azure_credentials:
                    provider_names.append("azure")
                if settings.has_aws_credentials:
                    provider_names.append("aws")
                if not provider_names:
                    provider_names = ["mock"]

                scan_dict = await CostAnalysisEngine.multi_cloud_scan(
                    provider_names, settings=settings
                )
                idle_res = []
                orphan_res = []
                under_res = []
                untagged_res = []
                total_scanned = 0
                total_waste = 0.0
                for s in scan_dict.values():
                    idle_res.extend(s.idle_resources)
                    orphan_res.extend(s.orphaned_storage)
                    under_res.extend(s.underutilized_vms)
                    untagged_res.extend(s.untagged_resources)
                    total_scanned += s.total_resources_scanned
                    total_waste += s.total_waste_monthly

                scan_result = ScanResult(
                    provider=CloudProviderType.MOCK,
                    idle_resources=idle_res,
                    orphaned_storage=orphan_res,
                    underutilized_vms=under_res,
                    untagged_resources=untagged_res,
                    total_resources_scanned=total_scanned,
                    total_waste_monthly=total_waste,
                )
                eng = CostAnalysisEngine(provider="mock", settings=settings)
            else:
                eng = CostAnalysisEngine(provider=provider, settings=settings)
                progress.update(
                    task,
                    advance=40,
                    description="[yellow]Auditing virtual machines and storage accounts...",
                )
                scan_result = await eng.scan_infrastructure(
                    idle_threshold_pct=idle_threshold,
                    orphaned_days=orphaned_days,
                    underutilized_threshold_pct=underutilized_threshold,
                )

            recs: list[Recommendation] = []
            progress.update(
                task, advance=30, description="[yellow]Evaluating FinOps optimization rules..."
            )
            if recommendations:
                recs = await eng.get_recommendations(scan_result=scan_result)

            progress.update(task, advance=30, description="[green]Scan complete.")

        filter_types = [t.strip().lower() for t in scan_type.split(",")] if scan_type else ["all"]
        show_all = "all" in filter_types

        if output.lower() == "json":
            out_data = {
                "scan_result": scan_result.model_dump(mode="json"),
                "recommendations": [r.model_dump(mode="json") for r in recs],
            }
            console.print_json(json.dumps(out_data))
            return

        if output.lower() == "tree":
            console.print()
            console.print(render_scan_tree(scan_result))
            console.print()
            return

        console.print()
        console.print(render_scan_summary_panel(scan_result, provider))
        console.print()

        if (
            show_all or "idle-vms" in filter_types or "idle" in filter_types
        ) and scan_result.idle_resources:
            console.print(
                render_resources_table(
                    "Idle Compute Workloads", scan_result.idle_resources, "yellow"
                )
            )
            console.print()

        if (
            show_all or "orphaned-storage" in filter_types or "orphaned" in filter_types
        ) and scan_result.orphaned_storage:
            console.print(
                render_resources_table(
                    "Orphaned Storage Volumes & Disks", scan_result.orphaned_storage, "red"
                )
            )
            console.print()

        if (
            show_all or "underutilized-vms" in filter_types or "underutilized" in filter_types
        ) and scan_result.underutilized_vms:
            console.print(
                render_resources_table(
                    "Underutilized Instances", scan_result.underutilized_vms, "magenta"
                )
            )
            console.print()

        if (
            show_all or "untagged-resources" in filter_types or "untagged" in filter_types
        ) and scan_result.untagged_resources:
            console.print(
                render_resources_table(
                    "Untagged Assets (Governance Risk)", scan_result.untagged_resources, "blue"
                )
            )
            console.print()

        if recommendations and recs:
            console.print(render_recommendations_table(recs))
            console.print()

    try:
        asyncio.run(_run())
    except CloudGuardError as e:
        console.print(f"[bold red]CloudGuard Error:[/bold red] {e}")
        raise typer.Exit(code=1) from None
    except Exception as e:
        console.print(f"[bold red]Execution Error:[/bold red] {e}")
        raise typer.Exit(code=1) from None


@app.command(name="report", help="Generate FinOps PDF/HTML/JSON reports.")
def report(
    provider: str = typer.Option(
        "all", "--provider", "-p", help="Cloud provider (azure, aws, mock, all)"
    ),
    start: str | None = typer.Option(None, "--start", "-s", help="Start date (YYYY-MM-DD)"),
    end: str | None = typer.Option(None, "--end", "-e", help="End date (YYYY-MM-DD)"),
    format: str = typer.Option(
        "pdf", "--format", "-f", help="Output format: pdf, html, json, markdown"
    ),
    output: str = typer.Option(
        "./reports/", "--output", "-o", help="Output directory or file path"
    ),
    title: str = typer.Option(
        "CloudGuard FinOps Executive Report", "--title", "-t", help="Report title"
    ),
) -> None:
    async def _run() -> None:
        today = date.today()
        default_start = today - timedelta(days=30)
        start_dt = parse_date(start, default_start)
        end_dt = parse_date(end, today)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Building FinOps report data...", total=100)

            eng = CostAnalysisEngine(provider="mock" if provider.lower() == "all" else provider)
            progress.update(
                task, advance=25, description="[cyan]Aggregating financial metrics & spend..."
            )
            report_data = await eng.build_report_data(
                start_date=start_dt, end_date=end_dt, title=title
            )

            progress.update(
                task, advance=25, description="[cyan]Rendering charts and document templates..."
            )
            out_path = Path(output)
            fmt = format.lower()

            if fmt == "pdf":
                if out_path.is_dir() or str(output).endswith("/") or str(output).endswith("\\"):
                    out_path.mkdir(parents=True, exist_ok=True)
                    target_file = out_path / f"cloudguard_report_{provider}_{today.isoformat()}.pdf"
                else:
                    target_file = out_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                generator = PDFReportGenerator()
                progress.update(task, advance=30, description="[cyan]Compiling PDF document...")
                final_path = generator.generate(report_data, output_path=target_file)

            elif fmt == "html":
                if out_path.is_dir() or str(output).endswith("/") or str(output).endswith("\\"):
                    out_path.mkdir(parents=True, exist_ok=True)
                    target_file = (
                        out_path / f"cloudguard_report_{provider}_{today.isoformat()}.html"
                    )
                else:
                    target_file = out_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                generator = PDFReportGenerator()
                html_str = generator.render_html(report_data)
                target_file.write_text(html_str, encoding="utf-8")
                final_path = target_file

            elif fmt == "json":
                if out_path.is_dir() or str(output).endswith("/") or str(output).endswith("\\"):
                    out_path.mkdir(parents=True, exist_ok=True)
                    target_file = (
                        out_path / f"cloudguard_report_{provider}_{today.isoformat()}.json"
                    )
                else:
                    target_file = out_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                target_file.write_text(report_data.model_dump_json(indent=2), encoding="utf-8")
                final_path = target_file

            elif fmt == "markdown":
                if out_path.is_dir() or str(output).endswith("/") or str(output).endswith("\\"):
                    out_path.mkdir(parents=True, exist_ok=True)
                    target_file = out_path / f"cloudguard_report_{provider}_{today.isoformat()}.md"
                else:
                    target_file = out_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                md_content = f"""# {report_data.title}
**Generated**: {report_data.generated_at.strftime("%Y-%m-%d %H:%M UTC")}
**Provider**: {report_data.provider.value.upper()}
**Period**: {report_data.summary.period_start} to {report_data.summary.period_end}

## Financial Summary
- **Total Cost**: {format_currency(report_data.summary.total_cost)}
- **Average Daily Spend**: {format_currency(report_data.summary.average_daily_cost)}
- **Identified Monthly Waste**: {format_currency(report_data.scan_result.total_waste_monthly)}
- **Projected Optimization Savings**: {format_currency(sum(r.estimated_savings for r in report_data.recommendations))}

## Top Cost Centers
"""
                for svc, c in report_data.summary.top_services:
                    md_content += f"- **{svc}**: {format_currency(c)}\n"

                target_file.write_text(md_content, encoding="utf-8")
                final_path = target_file
            else:
                console.print(
                    f"[bold red]Unsupported format:[/bold red] {format}. Supported: pdf, html, json, markdown."
                )
                raise typer.Exit(code=1)

            progress.update(task, advance=20, description="[green]Report written successfully.")

        total_savings = sum(r.estimated_savings for r in report_data.recommendations)

        grid = Table.grid(expand=True, padding=(0, 2))
        grid.add_column(style="bold white")
        grid.add_column(style="green")
        grid.add_row("Report Generated:", str(final_path.resolve()))
        grid.add_row("Format:", fmt.upper())
        grid.add_row("Period Analyzed:", f"{start_dt.isoformat()} to {end_dt.isoformat()}")
        grid.add_row("Total Spend Analyzed:", format_currency(report_data.summary.total_cost))
        grid.add_row("Identified Savings Potential:", format_currency(total_savings))

        console.print()
        console.print(
            Panel(
                grid,
                title="[bold green][*] FinOps Executive Report Ready[/bold green]",
                border_style="green",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        console.print()

    try:
        asyncio.run(_run())
    except CloudGuardError as e:
        console.print(f"[bold red]CloudGuard Error:[/bold red] {e}")
        raise typer.Exit(code=1) from None
    except Exception as e:
        console.print(f"[bold red]Execution Error:[/bold red] {e}")
        raise typer.Exit(code=1) from None


@app.command(name="dashboard", help="Start real-time FinOps observability web dashboard.")
def dashboard(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host interface to bind"),
    port: int = typer.Option(8050, "--port", "-p", help="Port to bind dashboard server"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
) -> None:
    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(style="bold white")
    grid.add_column(style="cyan")
    grid.add_row("Dashboard UI:", f"http://{host}:{port}")
    grid.add_row("REST API Docs:", f"http://{host}:{port}/docs")
    grid.add_row("Auto Reload:", str(reload))

    console.print()
    console.print(
        Panel(
            grid,
            title="[bold cyan][*] Launching CloudGuard Observability Dashboard[/bold cyan]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    console.print()

    try:
        import uvicorn

        try:
            from cloudguard.dashboard.app import app as dash_backend_app

            uvicorn.run(dash_backend_app, host=host, port=port, reload=reload)
        except ImportError:
            from fastapi import FastAPI
            from fastapi.responses import HTMLResponse

            temp_app = FastAPI(title="CloudGuard Observability API", version="1.0.0")

            @temp_app.get("/", response_class=HTMLResponse)
            def index() -> str:
                return f"""
                <html>
                    <head><title>CloudGuard Observability</title></head>
                    <body style="font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 40px;">
                        <h1>CloudGuard Observability Dashboard</h1>
                        <p>Server running on port {port}. API endpoints available at <a style="color: #38bdf8;" href="/docs">/docs</a>.</p>
                    </body>
                </html>
                """

            @temp_app.get("/api/v1/health")
            def health() -> dict[str, str]:
                return {"status": "healthy", "service": "cloudguard-dashboard"}

            uvicorn.run(temp_app, host=host, port=port, reload=reload)
    except Exception as e:
        console.print(f"[bold red]Failed to start dashboard server:[/bold red] {e}")
        raise typer.Exit(code=1) from None


@app.command(name="config", help="View, configure, or test CloudGuard settings.")
def config(
    set_val: str | None = typer.Option(
        None, "--set", help="Set configuration value (e.g. azure.subscription_id=xxx or key=value)"
    ),
    get_val: str | None = typer.Option(None, "--get", help="Get a specific configuration setting"),
    show: bool = typer.Option(
        False, "--show", "--list", "-l", help="List all current configuration values"
    ),
    test: bool = typer.Option(False, "--test", help="Test cloud provider connection"),
    provider: str | None = typer.Option(
        None, "--provider", "-p", help="Provider to test connection for"
    ),
) -> None:
    settings = get_settings()

    if set_val:
        if "=" not in set_val:
            console.print(
                "[bold red]Invalid syntax for --set.[/bold red] Use: [cyan]--set key=value[/cyan] or [cyan]--set azure.subscription_id=value[/cyan]"
            )
            raise typer.Exit(code=1)

        raw_key, val = set_val.split("=", 1)
        raw_key = raw_key.strip()
        val = val.strip()

        key = raw_key.replace(".", "_").lower()

        env_file = Path(".env")
        lines = []
        if env_file.exists():
            lines = env_file.read_text(encoding="utf-8").splitlines()

        key_found = False
        target_env_var = key.upper()
        new_lines = []
        for line in lines:
            if line.strip().startswith(f"{target_env_var}=") or line.strip().startswith(f"{key}="):
                new_lines.append(f"{target_env_var}={val}")
                key_found = True
            else:
                new_lines.append(line)

        if not key_found:
            new_lines.append(f"{target_env_var}={val}")

        env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        console.print(
            f"[bold green][v] Updated configuration:[/bold green] [cyan]{target_env_var}[/cyan] = [white]{'********' if 'secret' in key or 'key' in key else val}[/white] (saved to [dim].env[/dim])"
        )
        return

    if get_val:
        k = get_val.strip().replace(".", "_").lower()
        if hasattr(settings, k):
            val = getattr(settings, k)
            if "secret" in k or ("key" in k and val):
                val = "********"
            console.print(f"[bold cyan]{k}[/bold cyan] = [white]{val}[/white]")
        else:
            console.print(f"[bold red]Unknown configuration key:[/bold red] '{get_val}'")
            raise typer.Exit(code=1)
        return

    if test:
        target_prov = provider or settings.default_provider

        async def _test() -> bool:
            eng = CostAnalysisEngine(provider=target_prov, settings=settings)
            return await eng.test_connection()

        console.print(
            f"[cyan]Testing connection to cloud provider '[bold]{target_prov}[/bold]'...[/cyan]"
        )
        try:
            success = asyncio.run(_test())
            if success:
                console.print(
                    f"[bold green][v] Connection to '{target_prov}' successful![/bold green]"
                )
            else:
                console.print(f"[bold red][x] Connection to '{target_prov}' failed.[/bold red]")
                raise typer.Exit(code=1)
        except Exception as e:
            console.print(f"[bold red][x] Connection test error:[/bold red] {e}")
            raise typer.Exit(code=1) from None
        return

    console.print()
    console.print(render_config_table(settings))
    console.print()
