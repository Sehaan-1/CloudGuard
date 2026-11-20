from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from cloudguard.analysis.anomaly_detector import CompositeDetector, to_cost_dataframe
from cloudguard.analysis.iqr_detector import IQRDetector
from cloudguard.analysis.rolling_detector import RollingWindowDetector
from cloudguard.analysis.zscore_detector import ZScoreDetector
from cloudguard.core.models import (
    AnomalyResult,
    CloudResource,
    CostRecord,
    CostSummary,
    ScanResult,
)
from cloudguard.processing.parallel import AnalysisResult, ParallelProcessor


class PipelineContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    raw_data: Any = None
    df: pd.DataFrame = Field(default_factory=pd.DataFrame)
    records: list[CostRecord] = Field(default_factory=list)
    resources: list[CloudResource] = Field(default_factory=list)
    anomalies: list[AnomalyResult] = Field(default_factory=list)
    scan_result: ScanResult | None = None
    summary: CostSummary | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    stage_timings: dict[str, float] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    output: Any = None


class PipelineStage(ABC):
    def __init__(self, name: str | None = None) -> None:
        self.name = name or self.__class__.__name__

    @abstractmethod
    def execute(self, context: PipelineContext) -> PipelineContext:
        pass

    def __call__(self, context: PipelineContext) -> PipelineContext:
        return self.execute(context)


class IngestStage(PipelineStage):
    def execute(self, context: PipelineContext) -> PipelineContext:
        raw = context.raw_data
        if raw is None:
            return context

        if isinstance(raw, pd.DataFrame):
            context.df = raw.copy()
        elif isinstance(raw, Sequence):
            if not raw:
                context.df = pd.DataFrame()
            elif isinstance(raw[0], CloudResource):
                context.resources = list(raw)
            elif isinstance(raw[0], CostRecord):
                context.records = list(raw)
                context.df = to_cost_dataframe(context.records)
            elif isinstance(raw[0], dict):
                context.df = pd.DataFrame(raw)
        return context


class NormalizeStage(PipelineStage):
    def execute(self, context: PipelineContext) -> PipelineContext:
        if context.df.empty and not context.resources:
            return context

        if not context.df.empty:
            df = context.df
            df.columns = [str(c).strip().lower() for c in df.columns]

            if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
                df["date"] = pd.to_datetime(df["date"], errors="coerce")

            if "amount" in df.columns:
                df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)

            if "currency" not in df.columns:
                df["currency"] = "USD"

            if "service" in df.columns:
                df["service"] = df["service"].astype(str).str.strip()

            if "provider" in df.columns:
                df["provider"] = df["provider"].astype(str).str.lower().str.strip()

            context.df = df

        return context


class ValidateStage(PipelineStage):
    def execute(self, context: PipelineContext) -> PipelineContext:
        if not context.df.empty:
            df = context.df
            initial_len = len(df)

            if "amount" in df.columns:
                invalid_amounts = df["amount"] < 0
                if invalid_amounts.any():
                    dropped_count = int(invalid_amounts.sum())
                    context.errors.append(
                        f"Validation dropped {dropped_count} records with negative amount"
                    )
                    df = df[~invalid_amounts].copy()

            if "service" in df.columns:
                invalid_services = df["service"].isna() | (df["service"] == "")
                if invalid_services.any():
                    dropped_count = int(invalid_services.sum())
                    context.errors.append(
                        f"Validation dropped {dropped_count} records with missing service"
                    )
                    df = df[~invalid_services].copy()

            context.metrics["validated_record_count"] = len(df)
            context.metrics["dropped_record_count"] = initial_len - len(df)
            context.df = df

        return context


class EnrichStage(PipelineStage):
    def execute(self, context: PipelineContext) -> PipelineContext:
        if not context.df.empty:
            df = context.df
            if "date" in df.columns and pd.api.types.is_datetime64_any_dtype(df["date"]):
                df["day_name"] = df["date"].dt.day_name()
                df["is_weekend"] = df["date"].dt.dayofweek.isin([5, 6])
                df["month_year"] = df["date"].dt.to_period("M").astype(str)

            if "amount" in df.columns and len(df) > 0:
                q33 = float(df["amount"].quantile(0.33))
                q66 = float(df["amount"].quantile(0.66))
                conditions = [
                    df["amount"] <= q33,
                    (df["amount"] > q33) & (df["amount"] <= q66),
                    df["amount"] > q66,
                ]
                choices = ["low", "medium", "high"]
                df["cost_tier"] = np.select(conditions, choices, default="medium")

            if "tags" in df.columns:
                df["has_tags"] = df["tags"].apply(
                    lambda t: bool(t) if isinstance(t, dict) else False
                )

            context.df = df

        return context


class AnalyzeStage(PipelineStage):
    def __init__(
        self,
        name: str | None = None,
        processor: ParallelProcessor | None = None,
        min_votes: int = 1,
    ) -> None:
        super().__init__(name=name)
        self.processor = processor or ParallelProcessor()
        self.min_votes = min_votes

    def execute(self, context: PipelineContext) -> PipelineContext:
        if not context.df.empty:
            df = context.df
            if len(df) > 5000:
                z_det = ZScoreDetector(threshold=3.0, use_rolling=False)
                iqr_det = IQRDetector(multiplier=1.5)
                context.anomalies = z_det.detect(df) + iqr_det.detect(df)
            else:
                detector = CompositeDetector(
                    strategies=[
                        ZScoreDetector(threshold=3.0, use_rolling=False),
                        IQRDetector(multiplier=1.5),
                        RollingWindowDetector(window=14, std_dev_multiplier=2.5),
                    ],
                    min_votes=self.min_votes,
                )
                context.anomalies = detector.detect(df)

        elif context.resources:
            res_result = self.processor.process_records(context.resources)
            context.metrics["waste_summary"] = res_result.waste_summary

        return context


class AggregateStage(PipelineStage):
    def execute(self, context: PipelineContext) -> PipelineContext:
        if not context.df.empty:
            df = context.df
            total_cost = float(df["amount"].sum()) if "amount" in df.columns else 0.0

            service_totals: list[tuple[str, float]] = []
            if "service" in df.columns and "amount" in df.columns:
                grp = df.groupby("service")["amount"].sum().sort_values(ascending=False)
                service_totals = [(str(k), float(v)) for k, v in grp.items()]

            provider_totals: dict[str, float] = {}
            if "provider" in df.columns and "amount" in df.columns:
                p_grp = df.groupby("provider")["amount"].sum()
                provider_totals = {str(k): float(v) for k, v in p_grp.items()}

            region_totals: dict[str, float] = {}
            if "region" in df.columns and "amount" in df.columns:
                r_grp = df.groupby("region")["amount"].sum()
                region_totals = {str(k): float(v) for k, v in r_grp.items()}

            daily_totals_dict: dict[str, float] = {}
            daily_dates: list[date] = []
            if "date" in df.columns and "amount" in df.columns:
                d_grp = df.groupby("date")["amount"].sum().sort_index()
                for d, v in d_grp.items():
                    d_obj = d.date() if isinstance(d, datetime | pd.Timestamp) else d
                    daily_dates.append(d_obj)
                    daily_totals_dict[d_obj.isoformat()] = round(float(v), 2)

            start_d = min(daily_dates) if daily_dates else date.today()
            end_d = max(daily_dates) if daily_dates else date.today()
            days_span = max(1, (end_d - start_d).days + 1)

            context.summary = CostSummary(
                total_cost=round(total_cost, 2),
                currency=str(df["currency"].iloc[0])
                if "currency" in df.columns and not df.empty
                else "USD",
                period_start=start_d,
                period_end=end_d,
                record_count=len(df),
                cost_by_service=dict(service_totals),
                cost_by_region=region_totals,
                cost_by_provider=provider_totals,
                daily_totals=daily_totals_dict,
                average_daily_cost=round(total_cost / days_span, 2),
                top_services=service_totals[:5],
            )

            context.metrics["total_cost"] = round(total_cost, 2)
            context.metrics["service_count"] = len(service_totals)
            context.metrics["top_services"] = service_totals[:5]
            context.metrics["provider_breakdown"] = provider_totals

        return context


class OutputStage(PipelineStage):
    def execute(self, context: PipelineContext) -> PipelineContext:
        total_recs = len(context.df) if not context.df.empty else len(context.resources)
        res = AnalysisResult(
            total_records=total_recs,
            processed_records=total_recs,
            execution_time_seconds=round(sum(context.stage_timings.values()), 4),
            stage_timings={k: round(v, 4) for k, v in context.stage_timings.items()},
            anomalies=context.anomalies,
            waste_summary=context.metrics.get("waste_summary", {}),
            metrics=context.metrics,
            errors=context.errors,
        )
        context.output = res
        return context


class ProcessingPipeline:
    def __init__(
        self,
        stages: list[PipelineStage] | None = None,
        processor: ParallelProcessor | None = None,
    ) -> None:
        self.stages: list[PipelineStage] = list(stages) if stages is not None else []
        self.processor = processor or ParallelProcessor()

    def add_stage(
        self, stage: PipelineStage | Callable[[PipelineContext], PipelineContext]
    ) -> ProcessingPipeline:
        if isinstance(stage, PipelineStage):
            self.stages.append(stage)
        else:

            class FunctionalStage(PipelineStage):
                def __init__(self, func: Callable[[PipelineContext], PipelineContext]) -> None:
                    super().__init__(name=getattr(func, "__name__", "functional_stage"))
                    self.func = func

                def execute(self, context: PipelineContext) -> PipelineContext:
                    return self.func(context)

            self.stages.append(FunctionalStage(stage))
        return self

    def run(self, data: Any = None, context: PipelineContext | None = None) -> PipelineContext:
        ctx = context or PipelineContext()
        if data is not None:
            ctx.raw_data = data

        for stage in self.stages:
            t0 = time.perf_counter()
            ctx = stage.execute(ctx)
            stage_elapsed = time.perf_counter() - t0
            ctx.stage_timings[stage.name] = stage_elapsed

        return ctx

    def run_parallel(
        self, data: Any = None, processor: ParallelProcessor | None = None
    ) -> PipelineContext:
        proc = processor or self.processor
        old_proc = self.processor
        self.processor = proc
        try:
            ctx = PipelineContext(raw_data=data)
            return self.run(data=data, context=ctx)
        finally:
            self.processor = old_proc


def create_default_pipeline(processor: ParallelProcessor | None = None) -> ProcessingPipeline:
    proc = processor or ParallelProcessor()
    pipeline = ProcessingPipeline(processor=proc)
    pipeline.add_stage(IngestStage())
    pipeline.add_stage(NormalizeStage())
    pipeline.add_stage(ValidateStage())
    pipeline.add_stage(EnrichStage())
    pipeline.add_stage(AnalyzeStage(processor=proc))
    pipeline.add_stage(AggregateStage())
    pipeline.add_stage(OutputStage())
    return pipeline
