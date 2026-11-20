from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from cloudguard.analysis.anomaly_detector import (
    AnomalyDetectionStrategy,
    CompositeDetector,
)
from cloudguard.analysis.cost_analyzer import CostAnalyzer
from cloudguard.analysis.iqr_detector import IQRDetector
from cloudguard.analysis.rolling_detector import RollingWindowDetector
from cloudguard.analysis.zscore_detector import ZScoreDetector
from cloudguard.core.config import Settings, get_settings
from cloudguard.core.exceptions import AnalysisEngineError
from cloudguard.core.logging import get_logger
from cloudguard.core.models import (
    AnomalyResult,
    CostRecord,
    CostSummary,
    Granularity,
    Recommendation,
    ReportData,
    ScanResult,
)
from cloudguard.processing.parallel import AnalysisResult, ParallelProcessor
from cloudguard.processing.pipeline import (
    PipelineContext,
    ProcessingPipeline,
    create_default_pipeline,
)
from cloudguard.providers.base import CloudProvider
from cloudguard.providers.factory import ProviderFactory
from cloudguard.recommendations.engine import RecommendationEngine
from cloudguard.reports.generator import PDFReportGenerator

logger = get_logger("engine")


class CostAnalysisEngine:
    def __init__(
        self,
        provider: CloudProvider | str | None = None,
        settings: Settings | None = None,
        **provider_kwargs: Any,
    ) -> None:
        self.settings = settings or get_settings()

        if isinstance(provider, CloudProvider):
            self.provider = provider
        elif isinstance(provider, str):
            self.provider = ProviderFactory.create(provider, **provider_kwargs)
        else:
            self.provider = ProviderFactory.create(
                self.settings.default_provider, **provider_kwargs
            )

        logger.info(
            f"Initialized CostAnalysisEngine with provider: {self.provider.provider_name()}"
        )

    async def test_connection(self) -> bool:
        return await self.provider.test_connection()

    async def get_cost_data(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        granularity: Granularity = Granularity.DAILY,
    ) -> list[CostRecord]:
        end = end_date or date.today()
        start = start_date or (end - timedelta(days=30))

        try:
            logger.info(f"Querying cost data from {start} to {end} [{granularity.value}]")
            return await self.provider.get_cost_data(start, end, granularity)
        except Exception as e:
            logger.error(f"Failed to fetch cost data in engine: {e}")
            raise AnalysisEngineError(f"Cost analysis engine failed to fetch records: {e}") from e

    async def get_cost_summary(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> CostSummary:
        end = end_date or date.today()
        start = start_date or (end - timedelta(days=30))

        try:
            return await self.provider.get_cost_summary(start, end)
        except Exception as e:
            logger.error(f"Failed to compute cost summary in engine: {e}")
            raise AnalysisEngineError(f"Cost summary computation failed: {e}") from e

    async def scan_infrastructure(
        self,
        idle_threshold_pct: float | None = None,
        period_days: int | None = None,
        orphaned_days: int | None = None,
        underutilized_threshold_pct: float | None = None,
    ) -> ScanResult:
        idle_th = (
            idle_threshold_pct
            if idle_threshold_pct is not None
            else self.settings.idle_cpu_threshold_pct
        )
        days = period_days if period_days is not None else self.settings.idle_period_days
        orphan_days = (
            orphaned_days if orphaned_days is not None else self.settings.orphaned_storage_days
        )
        underutilized_th = (
            underutilized_threshold_pct
            if underutilized_threshold_pct is not None
            else self.settings.underutilized_vm_threshold_pct
        )

        try:
            return await self.provider.scan(
                idle_threshold_pct=idle_th,
                period_days=days,
                orphaned_days=orphan_days,
                underutilized_threshold_pct=underutilized_th,
            )
        except Exception as e:
            logger.error(f"Infrastructure scan failed in engine: {e}")
            raise AnalysisEngineError(f"Infrastructure scan failed: {e}") from e

    async def detect_anomalies(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        strategy: AnomalyDetectionStrategy | None = None,
        min_votes: int = 1,
    ) -> list[AnomalyResult]:
        records = await self.get_cost_data(start_date=start_date, end_date=end_date)
        if not records:
            return []

        detector = strategy
        if detector is None:
            detector = CompositeDetector(
                strategies=[
                    ZScoreDetector(threshold=self.settings.anomaly_zscore_threshold),
                    IQRDetector(multiplier=self.settings.anomaly_iqr_multiplier),
                    RollingWindowDetector(window=14, std_dev_multiplier=2.5),
                ],
                min_votes=min_votes,
            )

        try:
            return detector.detect(records)
        except Exception as e:
            logger.error(f"Anomaly detection failed in engine: {e}")
            raise AnalysisEngineError(f"Anomaly detection failed: {e}") from e

    async def get_recommendations(
        self,
        scan_result: ScanResult | None = None,
        cost_records: list[CostRecord] | None = None,
    ) -> list[Recommendation]:
        try:
            scan = scan_result if scan_result is not None else await self.scan_infrastructure()
            records = cost_records if cost_records is not None else await self.get_cost_data()
            engine = RecommendationEngine()
            return engine.analyze(scan, cost_data=records)
        except Exception as e:
            logger.error(f"Recommendation generation failed in engine: {e}")
            raise AnalysisEngineError(f"Recommendation generation failed: {e}") from e

    async def analyze_parallel(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        max_workers: int | None = None,
        chunk_size: int = 500,
    ) -> AnalysisResult:
        records = await self.get_cost_data(start_date=start_date, end_date=end_date)
        processor = ParallelProcessor(max_workers=max_workers, chunk_size=chunk_size)
        return processor.process_records(records)

    async def run_pipeline(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        pipeline: ProcessingPipeline | None = None,
    ) -> PipelineContext:
        records = await self.get_cost_data(start_date=start_date, end_date=end_date)
        pipe = pipeline or create_default_pipeline()
        return pipe.run(records)

    async def analyze_trends(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        days_ahead: int = 30,
    ) -> dict[str, Any]:
        records = await self.get_cost_data(start_date=start_date, end_date=end_date)
        analyzer = CostAnalyzer()
        try:
            return analyzer.full_analysis(records, days_ahead=days_ahead)
        except Exception as e:
            logger.error(f"Cost trend analysis failed in engine: {e}")
            raise AnalysisEngineError(f"Cost trend analysis failed: {e}") from e

    async def project_costs(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        days_ahead: int = 30,
    ) -> dict[str, Any]:
        records = await self.get_cost_data(start_date=start_date, end_date=end_date)
        analyzer = CostAnalyzer()
        try:
            return analyzer.project_costs(records, days_ahead=days_ahead)
        except Exception as e:
            logger.error(f"Cost projection failed in engine: {e}")
            raise AnalysisEngineError(f"Cost projection failed: {e}") from e

    async def build_report_data(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        title: str = "CloudGuard FinOps Executive Report",
    ) -> ReportData:
        end = end_date or date.today()
        start = start_date or (end - timedelta(days=30))
        summary = await self.get_cost_summary(start, end)
        scan_res = await self.scan_infrastructure()
        anomalies = await self.detect_anomalies(start_date=start, end_date=end)
        recs = await self.get_recommendations(scan_result=scan_res)
        return ReportData(
            title=title,
            provider=self.provider.provider_type,
            summary=summary,
            scan_result=scan_res,
            anomalies=anomalies,
            recommendations=recs,
        )

    async def generate_report(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        output_path: Path | str | None = None,
        report_data: ReportData | None = None,
        title: str = "CloudGuard FinOps Executive Report",
    ) -> Path:
        data = report_data or await self.build_report_data(
            start_date=start_date, end_date=end_date, title=title
        )
        generator = PDFReportGenerator()
        return generator.generate(data, output_path=output_path)

    @classmethod
    async def multi_cloud_scan(
        cls,
        provider_names: list[str],
        settings: Settings | None = None,
    ) -> dict[str, ScanResult]:
        results: dict[str, ScanResult] = {}
        for name in provider_names:
            engine = cls(provider=name, settings=settings)
            results[name] = await engine.scan_infrastructure()
        return results

    @classmethod
    async def multi_cloud_summary(
        cls,
        provider_names: list[str],
        start_date: date,
        end_date: date,
        settings: Settings | None = None,
    ) -> CostSummary:
        all_records: list[CostRecord] = []
        for name in provider_names:
            engine = cls(provider=name, settings=settings)
            records = await engine.get_cost_data(start_date, end_date)
            all_records.extend(records)

        return CostSummary.from_records(all_records, start_date, end_date)
