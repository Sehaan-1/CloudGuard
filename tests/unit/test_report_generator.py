from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from pypdf import PdfReader

from cloudguard.core.exceptions import ReportGenerationError
from cloudguard.core.models import (
    AnomalyResult,
    CloudProviderType,
    CloudResource,
    CostRecord,
    CostSummary,
    Recommendation,
    RecommendationPriority,
    RecommendationStatus,
    ReportData,
    ResourceStatus,
    ResourceType,
    ScanResult,
    Severity,
)
from cloudguard.engine import CostAnalysisEngine
from cloudguard.providers.mock_provider import MockProvider
from cloudguard.reports.charts import (
    anomaly_timeline,
    cost_breakdown_pie,
    cost_by_region_bar,
    cost_trend_line,
    savings_waterfall,
    utilization_heatmap,
)
from cloudguard.reports.generator import PDFReportGenerator


@pytest.fixture
def sample_report_data() -> ReportData:
    start_date = dt.date(2026, 7, 1)
    end_date = dt.date(2026, 7, 31)

    records = [
        CostRecord(
            service="Virtual Machines",
            date=dt.date(2026, 7, 10),
            amount=150.0,
            provider=CloudProviderType.AZURE,
            region="eastus",
        ),
        CostRecord(
            service="Virtual Machines",
            date=dt.date(2026, 7, 11),
            amount=160.0,
            provider=CloudProviderType.AZURE,
            region="eastus",
        ),
        CostRecord(
            service="Storage",
            date=dt.date(2026, 7, 12),
            amount=80.0,
            provider=CloudProviderType.AZURE,
            region="westus",
        ),
        CostRecord(
            service="SQL Database",
            date=dt.date(2026, 7, 13),
            amount=220.0,
            provider=CloudProviderType.AZURE,
            region="eastus",
        ),
    ]

    summary = CostSummary.from_records(records, start_date, end_date)

    idle_vm = CloudResource(
        id="vm-1",
        name="dev-test-vm",
        type=ResourceType.VM,
        provider=CloudProviderType.AZURE,
        region="eastus",
        status=ResourceStatus.IDLE,
        utilization_pct=1.5,
        monthly_cost=95.0,
    )
    orphaned_disk = CloudResource(
        id="disk-1",
        name="unattached-os-disk",
        type=ResourceType.STORAGE,
        provider=CloudProviderType.AZURE,
        region="eastus",
        status=ResourceStatus.ORPHANED,
        utilization_pct=0.0,
        monthly_cost=40.0,
        metadata={"is_attached": False},
    )

    scan_res = ScanResult(
        provider=CloudProviderType.AZURE,
        idle_resources=[idle_vm],
        orphaned_storage=[orphaned_disk],
        underutilized_vms=[],
        untagged_resources=[],
        total_resources_scanned=15,
        total_waste_monthly=135.0,
    )

    anomalies = [
        AnomalyResult(
            service="Virtual Machines",
            date=dt.date(2026, 7, 15),
            expected_cost=150.0,
            actual_cost=450.0,
            deviation_score=3.8,
            severity=Severity.CRITICAL,
            method="zscore",
            description="Sudden 300% compute spike",
        ),
        AnomalyResult(
            service="Storage",
            date=dt.date(2026, 7, 20),
            expected_cost=80.0,
            actual_cost=160.0,
            deviation_score=2.1,
            severity=Severity.MEDIUM,
            method="iqr",
            description="Storage egress surge",
        ),
    ]

    recs = [
        Recommendation(
            resource_id="vm-1",
            resource_name="dev-test-vm",
            action="terminate_idle",
            title="Terminate Idle Dev VM",
            description="Deallocate VM dev-test-vm with <2% CPU utilization",
            estimated_savings=95.0,
            confidence=0.95,
            priority=RecommendationPriority.HIGH,
            resource_type=ResourceType.VM,
            provider=CloudProviderType.AZURE,
            status=RecommendationStatus.OPEN,
        ),
        Recommendation(
            resource_id="disk-1",
            resource_name="unattached-os-disk",
            action="delete_orphan",
            title="Delete Unattached Disk",
            description="Remove unused 512GB managed disk",
            estimated_savings=40.0,
            confidence=0.99,
            priority=RecommendationPriority.URGENT,
            resource_type=ResourceType.STORAGE,
            provider=CloudProviderType.AZURE,
            status=RecommendationStatus.OPEN,
        ),
    ]

    return ReportData(
        title="Monthly FinOps Executive Summary",
        provider=CloudProviderType.AZURE,
        summary=summary,
        scan_result=scan_res,
        anomalies=anomalies,
        recommendations=recs,
    )


def test_charts_render_as_static_images(sample_report_data: ReportData) -> None:
    pie_b64 = cost_breakdown_pie(sample_report_data.summary, output_format="base64")
    assert isinstance(pie_b64, str)
    assert pie_b64.startswith("data:image/png;base64,")

    pie_bytes = cost_breakdown_pie(sample_report_data.summary, output_format="bytes")
    assert isinstance(pie_bytes, bytes)
    assert len(pie_bytes) > 100

    trend_b64 = cost_trend_line(sample_report_data.summary, output_format="base64")
    assert isinstance(trend_b64, str)
    assert trend_b64.startswith("data:image/png;base64,")

    region_b64 = cost_by_region_bar(sample_report_data.summary, output_format="base64")
    assert isinstance(region_b64, str)
    assert region_b64.startswith("data:image/png;base64,")

    anomaly_b64 = anomaly_timeline(sample_report_data.anomalies, output_format="base64")
    assert isinstance(anomaly_b64, str)
    assert anomaly_b64.startswith("data:image/png;base64,")

    heatmap_b64 = utilization_heatmap(sample_report_data.scan_result, output_format="base64")
    assert isinstance(heatmap_b64, str)
    assert heatmap_b64.startswith("data:image/png;base64,")

    waterfall_b64 = savings_waterfall(sample_report_data.recommendations, output_format="base64")
    assert isinstance(waterfall_b64, str)
    assert waterfall_b64.startswith("data:image/png;base64,")


def test_charts_handle_empty_data() -> None:
    assert isinstance(cost_breakdown_pie(None, output_format="base64"), str)
    assert isinstance(cost_breakdown_pie({}, output_format="base64"), str)
    assert isinstance(cost_trend_line(None, output_format="base64"), str)
    assert isinstance(cost_trend_line([], output_format="base64"), str)
    assert isinstance(cost_by_region_bar(None, output_format="base64"), str)
    assert isinstance(anomaly_timeline([], output_format="base64"), str)
    assert isinstance(anomaly_timeline(None, output_format="base64"), str)
    assert isinstance(utilization_heatmap([], output_format="base64"), str)
    assert isinstance(savings_waterfall([], output_format="base64"), str)


def test_render_html_contains_all_sections(sample_report_data: ReportData) -> None:
    generator = PDFReportGenerator()
    html = generator.render_html(sample_report_data)

    assert "FinOps Report" in html
    assert "Executive Summary" in html
    assert "Cost Breakdown" in html
    assert "Spending Anomaly Detection" in html
    assert "Infrastructure Waste" in html
    assert "Actionable Recommendations" in html
    assert "Appendix" in html
    assert "Terminate Idle Dev VM" in html
    assert "Delete Unattached Disk" in html
    assert "$610.00" in html or "610" in html


def test_pdf_report_generates_valid_pdf(sample_report_data: ReportData, tmp_path: Path) -> None:
    generator = PDFReportGenerator()
    output_pdf = tmp_path / "test_report.pdf"

    result_path = generator.generate(sample_report_data, output_path=output_pdf)

    assert result_path.exists()
    assert result_path == output_pdf
    assert result_path.stat().st_size > 0

    reader = PdfReader(str(result_path))
    assert len(reader.pages) >= 1


def test_pdf_contains_all_sections(sample_report_data: ReportData, tmp_path: Path) -> None:
    generator = PDFReportGenerator()
    output_pdf = tmp_path / "test_sections_report.pdf"
    result_path = generator.generate(sample_report_data, output_path=output_pdf)

    assert result_path.exists()
    reader = PdfReader(str(result_path))
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert len(full_text) > 0
    assert "FinOps" in full_text or "Report" in full_text
    assert "Executive Summary" in full_text or "Summary" in full_text


def test_pdf_report_generates_with_empty_data(tmp_path: Path) -> None:
    start_date = dt.date(2026, 7, 1)
    end_date = dt.date(2026, 7, 31)
    empty_summary = CostSummary.from_records([], start_date, end_date)
    empty_scan = ScanResult(
        provider=CloudProviderType.MOCK,
        idle_resources=[],
        orphaned_storage=[],
        underutilized_vms=[],
        untagged_resources=[],
        total_resources_scanned=0,
        total_waste_monthly=0.0,
    )
    empty_report = ReportData(
        title="Empty Environment Report",
        provider=CloudProviderType.MOCK,
        summary=empty_summary,
        scan_result=empty_scan,
        anomalies=[],
        recommendations=[],
    )

    generator = PDFReportGenerator()
    output_pdf = tmp_path / "empty_report.pdf"
    result_path = generator.generate(empty_report, output_path=output_pdf)

    assert result_path.exists()
    assert result_path.stat().st_size > 0

    reader = PdfReader(str(result_path))
    assert len(reader.pages) >= 1


def test_report_generator_invalid_template(sample_report_data: ReportData) -> None:
    generator = PDFReportGenerator()
    with pytest.raises(ReportGenerationError):
        generator.render_html(sample_report_data, template_name="nonexistent.html")


def test_report_generator_invalid_template_dir() -> None:
    with pytest.raises(ReportGenerationError):
        PDFReportGenerator(template_dir="/invalid/directory/path/that/does/not/exist")


@pytest.mark.asyncio
async def test_engine_generate_report_integration(tmp_path: Path) -> None:
    mock_provider = MockProvider(seed=42)
    engine = CostAnalysisEngine(provider=mock_provider)

    start_date = dt.date(2026, 7, 1)
    end_date = dt.date(2026, 7, 30)

    report_data = await engine.build_report_data(start_date=start_date, end_date=end_date)
    assert report_data is not None
    assert report_data.summary.record_count > 0

    output_pdf = tmp_path / "engine_generated_report.pdf"
    generated_path = await engine.generate_report(
        start_date=start_date,
        end_date=end_date,
        output_path=output_pdf,
    )

    assert generated_path.exists()
    assert generated_path.stat().st_size > 0

    reader = PdfReader(str(generated_path))
    assert len(reader.pages) >= 1
