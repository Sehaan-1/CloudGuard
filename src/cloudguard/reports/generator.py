from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from cloudguard.core.exceptions import ReportGenerationError
from cloudguard.core.logging import get_logger
from cloudguard.core.models import CloudResource, ReportData
from cloudguard.reports import charts

logger = get_logger("reports")


class PDFReportGenerator:
    def __init__(self, template_dir: Path | str | None = None) -> None:
        if template_dir is not None:
            self.template_path = Path(template_dir)
        else:
            self.template_path = Path(__file__).parent / "templates"

        if not self.template_path.exists():
            raise ReportGenerationError(f"Template directory not found: {self.template_path}")

        self.env = Environment(
            loader=FileSystemLoader(str(self.template_path)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def _generate_charts(self, report_data: ReportData) -> dict[str, str]:
        chart_map: dict[str, str] = {}
        try:
            chart_map["cost_breakdown_pie"] = str(
                charts.cost_breakdown_pie(report_data.summary, output_format="base64")
            )
            chart_map["cost_trend_line"] = str(
                charts.cost_trend_line(report_data.summary, output_format="base64")
            )
            chart_map["cost_by_region_bar"] = str(
                charts.cost_by_region_bar(report_data.summary, output_format="base64")
            )
            chart_map["anomaly_timeline"] = str(
                charts.anomaly_timeline(report_data.anomalies, output_format="base64")
            )
            chart_map["utilization_heatmap"] = str(
                charts.utilization_heatmap(report_data.scan_result, output_format="base64")
            )
            chart_map["savings_waterfall"] = str(
                charts.savings_waterfall(report_data.recommendations, output_format="base64")
            )
        except Exception as e:
            logger.warning(f"Error generating one or more report charts: {e}")
        return chart_map

    def _collect_flagged_resources(self, report_data: ReportData) -> list[CloudResource]:
        seen: set[str] = set()
        res_list: list[CloudResource] = []
        scan = report_data.scan_result

        for r in (
            scan.idle_resources
            + scan.orphaned_storage
            + scan.underutilized_vms
            + scan.untagged_resources
        ):
            if r.id not in seen:
                seen.add(r.id)
                res_list.append(r)
        return res_list

    def render_html(self, report_data: ReportData, template_name: str = "report.html") -> str:
        try:
            template = self.env.get_template(template_name)
        except Exception as e:
            raise ReportGenerationError(f"Failed to load template '{template_name}': {e}") from e

        chart_dict = self._generate_charts(report_data)
        flagged = self._collect_flagged_resources(report_data)
        total_savings = sum(r.estimated_savings for r in report_data.recommendations)

        p_name = (
            report_data.provider.value.upper()
            if hasattr(report_data.provider, "value")
            else str(report_data.provider).upper()
        )

        context: dict[str, Any] = {
            "report": report_data,
            "charts": chart_dict,
            "flagged_resources": flagged,
            "total_projected_savings": total_savings,
            "provider_name": p_name,
            "generated_date_str": report_data.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
            "period_start_str": report_data.summary.period_start.isoformat(),
            "period_end_str": report_data.summary.period_end.isoformat(),
        }

        try:
            return template.render(**context)
        except Exception as e:
            raise ReportGenerationError(f"Failed to render HTML report template: {e}") from e

    def generate(
        self,
        report_data: ReportData,
        output_path: Path | str | None = None,
        template_name: str = "report.html",
    ) -> Path:
        if output_path is None:
            out_p = Path("reports") / f"cloudguard_report_{report_data.id[:8]}.pdf"
        else:
            out_p = Path(output_path)

        out_p.parent.mkdir(parents=True, exist_ok=True)
        html_content = self.render_html(report_data, template_name=template_name)

        weasyprint_success = False
        try:
            import weasyprint

            weasyprint.HTML(string=html_content).write_pdf(str(out_p))
            weasyprint_success = True
        except Exception:
            weasyprint_success = False

        if not weasyprint_success:
            try:
                from xhtml2pdf import pisa

                with open(out_p, "wb") as pdf_file:
                    pisa_status = pisa.CreatePDF(
                        src=html_content,
                        dest=pdf_file,
                    )
                    if pisa_status.err:
                        raise ReportGenerationError(
                            f"xhtml2pdf encountered errors: {pisa_status.err}"
                        )
            except Exception as e:
                raise ReportGenerationError(f"Failed to generate PDF report: {e}") from e

        if not out_p.exists() or out_p.stat().st_size == 0:
            raise ReportGenerationError(f"PDF file was not created or is empty: {out_p}")

        logger.info(f"Successfully generated PDF report at: {out_p}")
        return out_p
