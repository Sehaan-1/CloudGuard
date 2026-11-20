from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from cloudguard.analysis.anomaly_detector import CompositeDetector
from cloudguard.analysis.iqr_detector import IQRDetector
from cloudguard.analysis.rolling_detector import RollingWindowDetector
from cloudguard.analysis.zscore_detector import ZScoreDetector
from cloudguard.core.config import Settings, get_settings
from cloudguard.core.models import (
    AnomalyResult,
    CloudProviderType,
    CostRecord,
    CostSummary,
    Granularity,
    Recommendation,
    ReportData,
    ScanResult,
    Severity,
)
from cloudguard.engine import CostAnalysisEngine
from cloudguard.reports.generator import PDFReportGenerator

_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)


def run_async(coro: Any) -> Any:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        future = concurrent.futures.Future()

        def _run_in_new_loop():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                result = new_loop.run_until_complete(coro)
                future.set_result(result)
            except Exception as exc:
                future.set_exception(exc)
            finally:
                new_loop.close()

        t = threading.Thread(target=_run_in_new_loop)
        t.start()
        t.join()
        return future.result()
    else:
        return asyncio.run(coro)


class DashboardService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._cached_anomalies: dict[str, AnomalyResult] = {}
        self._cached_recommendations: dict[str, Recommendation] = {}

    def get_engine(self, provider: str = "mock") -> CostAnalysisEngine:
        return CostAnalysisEngine(provider=provider, settings=self.settings)

    def resolve_dates(
        self, start_date: date | None = None, end_date: date | None = None, days_back: int = 30
    ) -> tuple[date, date]:
        today = date.today()
        end = end_date or today
        start = start_date or (end - timedelta(days=days_back))
        if start > end:
            start, end = end, start
        return start, end

    async def get_cost_summary(
        self,
        provider: str = "mock",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> CostSummary:
        start, end = self.resolve_dates(start_date, end_date)
        if provider.lower() == "all":
            provider_names = []
            if self.settings.has_azure_credentials:
                provider_names.append("azure")
            if self.settings.has_aws_credentials:
                provider_names.append("aws")
            if not provider_names:
                provider_names = ["mock"]
            return await CostAnalysisEngine.multi_cloud_summary(
                provider_names, start, end, settings=self.settings
            )
        engine = self.get_engine(provider)
        return await engine.get_cost_summary(start, end)

    async def get_cost_records(
        self,
        provider: str = "mock",
        start_date: date | None = None,
        end_date: date | None = None,
        granularity: Granularity = Granularity.DAILY,
    ) -> list[CostRecord]:
        start, end = self.resolve_dates(start_date, end_date)
        if provider.lower() == "all":
            provider_names = []
            if self.settings.has_azure_credentials:
                provider_names.append("azure")
            if self.settings.has_aws_credentials:
                provider_names.append("aws")
            if not provider_names:
                provider_names = ["mock"]
            all_records: list[CostRecord] = []
            for p in provider_names:
                engine = self.get_engine(p)
                recs = await engine.get_cost_data(start, end, granularity)
                all_records.extend(recs)
            return all_records
        engine = self.get_engine(provider)
        return await engine.get_cost_data(start, end, granularity)

    async def get_cost_by_service(
        self,
        provider: str = "mock",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, float]:
        summary = await self.get_cost_summary(provider, start_date, end_date)
        return summary.cost_by_service

    async def get_cost_trend(
        self,
        provider: str = "mock",
        start_date: date | None = None,
        end_date: date | None = None,
        granularity: Granularity = Granularity.DAILY,
    ) -> dict[str, float]:
        summary = await self.get_cost_summary(provider, start_date, end_date)
        return summary.daily_totals

    async def get_anomalies(
        self,
        provider: str = "mock",
        start_date: date | None = None,
        end_date: date | None = None,
        method: str | None = None,
        threshold: float | None = None,
        severity: str | None = None,
    ) -> list[AnomalyResult]:
        start, end = self.resolve_dates(start_date, end_date)
        records = await self.get_cost_records(provider, start, end)
        if not records:
            return []

        z_thresh = threshold or self.settings.anomaly_zscore_threshold
        iqr_mult = threshold or self.settings.anomaly_iqr_multiplier

        if method == "zscore":
            detector = ZScoreDetector(threshold=z_thresh)
            results = detector.detect(records)
        elif method == "iqr":
            detector = IQRDetector(multiplier=iqr_mult)
            results = detector.detect(records)
        elif method == "rolling":
            detector = RollingWindowDetector(window=14, std_dev_multiplier=2.5)
            results = detector.detect(records)
        else:
            detector = CompositeDetector(
                strategies=[
                    ZScoreDetector(threshold=z_thresh),
                    IQRDetector(multiplier=iqr_mult),
                    RollingWindowDetector(window=14, std_dev_multiplier=2.5),
                ],
                min_votes=1,
            )
            results = detector.detect(records)

        for a in results:
            self._cached_anomalies[a.id] = a

        if severity:
            sev_enum = Severity(severity.lower())
            results = [a for a in results if a.severity == sev_enum]

        return results

    async def get_anomaly_by_id(
        self,
        anomaly_id: str,
        provider: str = "mock",
    ) -> AnomalyResult | None:
        if anomaly_id in self._cached_anomalies:
            return self._cached_anomalies[anomaly_id]
        await self.get_anomalies(provider=provider)
        return self._cached_anomalies.get(anomaly_id)

    async def get_scan_result(
        self,
        provider: str = "mock",
        idle_threshold: float | None = None,
        orphaned_days: int | None = None,
        underutilized_threshold: float | None = None,
    ) -> ScanResult:
        if provider.lower() == "all":
            provider_names = []
            if self.settings.has_azure_credentials:
                provider_names.append("azure")
            if self.settings.has_aws_credentials:
                provider_names.append("aws")
            if not provider_names:
                provider_names = ["mock"]

            scan_dict = await CostAnalysisEngine.multi_cloud_scan(
                provider_names, settings=self.settings
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

            return ScanResult(
                provider=CloudProviderType.MOCK,
                idle_resources=idle_res,
                orphaned_storage=orphan_res,
                underutilized_vms=under_res,
                untagged_resources=untagged_res,
                total_resources_scanned=total_scanned,
                total_waste_monthly=round(total_waste, 2),
            )

        engine = self.get_engine(provider)
        return await engine.scan_infrastructure(
            idle_threshold_pct=idle_threshold,
            orphaned_days=orphaned_days,
            underutilized_threshold_pct=underutilized_threshold,
        )

    async def get_recommendations(
        self,
        provider: str = "mock",
        scan_result: ScanResult | None = None,
    ) -> list[Recommendation]:
        scan_res = scan_result or await self.get_scan_result(provider)
        engine = self.get_engine(provider if provider.lower() != "all" else "mock")
        recs = await engine.get_recommendations(scan_result=scan_res)
        for r in recs:
            self._cached_recommendations[r.id] = r
        return recs

    async def get_recommendation_by_id(
        self,
        recommendation_id: str,
        provider: str = "mock",
    ) -> Recommendation | None:
        if recommendation_id in self._cached_recommendations:
            return self._cached_recommendations[recommendation_id]
        await self.get_recommendations(provider=provider)
        return self._cached_recommendations.get(recommendation_id)

    async def build_report_data(
        self,
        provider: str = "mock",
        start_date: date | None = None,
        end_date: date | None = None,
        title: str = "CloudGuard FinOps Executive Report",
    ) -> ReportData:
        start, end = self.resolve_dates(start_date, end_date)
        engine = self.get_engine(provider if provider.lower() != "all" else "mock")
        return await engine.build_report_data(start_date=start, end_date=end, title=title)

    async def generate_report(
        self,
        provider: str = "mock",
        start_date: date | None = None,
        end_date: date | None = None,
        title: str = "CloudGuard FinOps Executive Report",
        fmt: str = "pdf",
        output_dir: Path | str | None = None,
    ) -> tuple[str, Path]:
        report_data = await self.build_report_data(
            provider=provider, start_date=start_date, end_date=end_date, title=title
        )
        report_id = str(uuid.uuid4())
        out_dir = Path(output_dir or "./reports")
        out_dir.mkdir(parents=True, exist_ok=True)

        target_file = out_dir / f"report_{report_id}.{fmt.lower()}"

        if fmt.lower() == "pdf":
            generator = PDFReportGenerator()
            generator.generate(report_data, output_path=target_file)
        elif fmt.lower() == "html":
            generator = PDFReportGenerator()
            html_content = generator.render_html(report_data)
            target_file.write_text(html_content, encoding="utf-8")
        elif fmt.lower() == "json":
            target_file.write_text(report_data.model_dump_json(indent=2), encoding="utf-8")
        else:
            generator = PDFReportGenerator()
            generator.generate(report_data, output_path=target_file)

        return report_id, target_file


dashboard_service = DashboardService()
