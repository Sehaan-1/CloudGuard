from __future__ import annotations

import concurrent.futures
import os
import time
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from cloudguard.analysis.anomaly_detector import to_cost_dataframe
from cloudguard.analysis.iqr_detector import IQRDetector
from cloudguard.analysis.zscore_detector import ZScoreDetector
from cloudguard.core.models import (
    AnomalyResult,
    CloudResource,
    CostRecord,
    ResourceStatus,
)
from cloudguard.processing.chunker import Chunker

T = TypeVar("T")
R = TypeVar("R")


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_records: int = Field(default=0, ge=0)
    processed_records: int = Field(default=0, ge=0)
    execution_time_seconds: float = Field(default=0.0, ge=0.0)
    stage_timings: dict[str, float] = Field(default_factory=dict)
    anomalies: list[AnomalyResult] = Field(default_factory=list)
    waste_summary: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


def _default_df_worker(
    chunk: pd.DataFrame, func: Callable[[pd.DataFrame], pd.DataFrame]
) -> pd.DataFrame:
    return func(chunk)


def _process_cost_chunk(chunk_df: pd.DataFrame) -> dict[str, Any]:
    if chunk_df.empty:
        return {
            "record_count": 0,
            "total_amount": 0.0,
            "anomalies": [],
            "service_totals": {},
        }

    total_amount = float(chunk_df["amount"].sum()) if "amount" in chunk_df.columns else 0.0
    service_totals: dict[str, float] = {}
    if "service" in chunk_df.columns and "amount" in chunk_df.columns:
        grouped = chunk_df.groupby("service")["amount"].sum()
        service_totals = {str(k): float(v) for k, v in grouped.items()}

    anomalies: list[AnomalyResult] = []
    if len(chunk_df) >= 3 and "amount" in chunk_df.columns:
        z_det = ZScoreDetector(threshold=3.0, use_rolling=False)
        iqr_det = IQRDetector(multiplier=1.5)
        anomalies.extend(z_det.detect(chunk_df))
        anomalies.extend(iqr_det.detect(chunk_df))

    return {
        "record_count": len(chunk_df),
        "total_amount": total_amount,
        "anomalies": anomalies,
        "service_totals": service_totals,
    }


def _process_resource_chunk(resources: list[CloudResource]) -> dict[str, Any]:
    idle_count = 0
    orphaned_count = 0
    underutilized_count = 0
    untagged_count = 0
    total_waste = 0.0

    for r in resources:
        if r.is_idle:
            idle_count += 1
            total_waste += r.monthly_cost
        if r.is_orphaned:
            orphaned_count += 1
            total_waste += r.monthly_cost
        if r.status == ResourceStatus.UNDERUTILIZED or (r.utilization_pct < 20.0 and not r.is_idle):
            underutilized_count += 1
            total_waste += r.monthly_cost * 0.4
        if r.is_untagged:
            untagged_count += 1

    return {
        "count": len(resources),
        "idle_count": idle_count,
        "orphaned_count": orphaned_count,
        "underutilized_count": underutilized_count,
        "untagged_count": untagged_count,
        "total_waste": round(total_waste, 2),
    }


class ParallelProcessor:
    def __init__(
        self,
        max_workers: int | None = None,
        chunk_size: int = 500,
        use_processes: bool = False,
    ) -> None:
        cpu_count = os.cpu_count() or 1
        self.max_workers = max_workers if max_workers is not None else min(32, cpu_count + 4)
        self.chunk_size = max(1, chunk_size)
        self.use_processes = use_processes

    def _get_executor(self) -> concurrent.futures.Executor:
        if self.use_processes:
            return concurrent.futures.ProcessPoolExecutor(max_workers=self.max_workers)
        return concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)

    def process_dataframe(
        self,
        df: pd.DataFrame,
        func: Callable[[pd.DataFrame], pd.DataFrame],
        num_chunks: int | None = None,
    ) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()

        chunks = Chunker.split_dataframe(
            df,
            num_chunks=num_chunks or self.max_workers,
            chunk_size=self.chunk_size if num_chunks is None else None,
        )

        if len(chunks) == 1:
            return func(chunks[0])

        with self._get_executor() as executor:
            futures = [executor.submit(_default_df_worker, chunk, func) for chunk in chunks]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        return pd.concat(results, ignore_index=True)

    def map_reduce(
        self,
        data: Sequence[T] | pd.DataFrame,
        mapper: Callable[[Any], R],
        reducer: Callable[[list[R]], R] | None = None,
    ) -> R | list[R]:
        if isinstance(data, pd.DataFrame):
            chunks: Sequence[Any] = Chunker.split_dataframe(data, chunk_size=self.chunk_size)
        else:
            chunks = Chunker.split_list(data, chunk_size=self.chunk_size)

        if not chunks:
            empty_list: list[R] = []
            return reducer(empty_list) if reducer is not None else empty_list

        if len(chunks) == 1:
            mapped_single = [mapper(chunks[0])]
            return reducer(mapped_single) if reducer is not None else mapped_single

        with self._get_executor() as executor:
            futures = [executor.submit(mapper, chunk) for chunk in chunks]
            mapped_results = [f.result() for f in futures]

        if reducer is not None:
            return reducer(mapped_results)
        return mapped_results

    def process_records(
        self,
        records: Sequence[CloudResource] | Sequence[CostRecord] | pd.DataFrame,
        analyzers: list[Callable[..., Any]] | None = None,
    ) -> AnalysisResult:
        start_time = time.perf_counter()
        timings: dict[str, float] = {}
        errors: list[str] = []

        if isinstance(records, pd.DataFrame):
            t0 = time.perf_counter()
            df = records
            timings["ingest_dataframe"] = time.perf_counter() - t0
            total_count = len(df)
            is_cost_data = "amount" in df.columns
        elif records and isinstance(records[0], CloudResource):
            t0 = time.perf_counter()
            total_count = len(records)
            is_cost_data = False
            timings["ingest_resources"] = time.perf_counter() - t0
            df = pd.DataFrame()
        else:
            t0 = time.perf_counter()
            cost_records = list(records)
            total_count = len(cost_records)
            is_cost_data = True
            df = to_cost_dataframe(cost_records)
            timings["convert_to_dataframe"] = time.perf_counter() - t0

        all_anomalies: list[AnomalyResult] = []
        waste_summary: dict[str, Any] = {}
        metrics: dict[str, Any] = {}

        if is_cost_data and not df.empty:
            t1 = time.perf_counter()
            amounts = df["amount"].to_numpy(dtype=np.float64)
            total_cost = float(np.sum(amounts))
            mean_cost = float(np.mean(amounts))
            std_cost = float(np.std(amounts))
            metrics["total_cost"] = round(total_cost, 2)
            metrics["mean_cost"] = round(mean_cost, 2)
            metrics["std_cost"] = round(std_cost, 2)
            metrics["min_cost"] = round(float(np.min(amounts)), 2)
            metrics["max_cost"] = round(float(np.max(amounts)), 2)
            timings["vectorized_metrics"] = time.perf_counter() - t1

            t2 = time.perf_counter()
            if "service" in df.columns:
                service_groups = [group for _, group in df.groupby("service")]
                with self._get_executor() as executor:
                    futures = [executor.submit(_process_cost_chunk, grp) for grp in service_groups]
                    for f in concurrent.futures.as_completed(futures):
                        try:
                            res = f.result()
                            all_anomalies.extend(res["anomalies"])
                        except Exception as e:
                            errors.append(f"Cost chunk processing error: {e}")
            else:
                chunks = Chunker.split_dataframe(df, chunk_size=self.chunk_size)
                with self._get_executor() as executor:
                    futures = [executor.submit(_process_cost_chunk, chunk) for chunk in chunks]
                    for f in concurrent.futures.as_completed(futures):
                        try:
                            res = f.result()
                            all_anomalies.extend(res["anomalies"])
                        except Exception as e:
                            errors.append(f"Cost chunk processing error: {e}")
            timings["parallel_cost_analysis"] = time.perf_counter() - t2

        elif not is_cost_data and records:
            t3 = time.perf_counter()
            resource_records = list(records)
            res_chunks = Chunker.split_list(resource_records, chunk_size=self.chunk_size)

            total_idle = 0
            total_orphaned = 0
            total_underutilized = 0
            total_untagged = 0
            total_waste = 0.0

            with self._get_executor() as executor:
                futures = [executor.submit(_process_resource_chunk, chk) for chk in res_chunks]
                for f in concurrent.futures.as_completed(futures):
                    try:
                        res = f.result()
                        total_idle += res["idle_count"]
                        total_orphaned += res["orphaned_count"]
                        total_underutilized += res["underutilized_count"]
                        total_untagged += res["untagged_count"]
                        total_waste += res["total_waste"]
                    except Exception as e:
                        errors.append(f"Resource chunk processing error: {e}")

            waste_summary = {
                "idle_count": total_idle,
                "orphaned_count": total_orphaned,
                "underutilized_count": total_underutilized,
                "untagged_count": total_untagged,
                "total_waste_monthly": round(total_waste, 2),
            }
            timings["parallel_resource_analysis"] = time.perf_counter() - t3

        if analyzers:
            t4 = time.perf_counter()
            for idx, analyzer in enumerate(analyzers):
                try:
                    res = analyzer(df if is_cost_data else records)
                    metrics[f"custom_analyzer_{idx}"] = res
                except Exception as e:
                    errors.append(f"Custom analyzer {idx} failed: {e}")
            timings["custom_analyzers"] = time.perf_counter() - t4

        total_execution_time = time.perf_counter() - start_time

        return AnalysisResult(
            total_records=total_count,
            processed_records=total_count,
            execution_time_seconds=round(total_execution_time, 4),
            stage_timings={k: round(v, 4) for k, v in timings.items()},
            anomalies=all_anomalies,
            waste_summary=waste_summary,
            metrics=metrics,
            errors=errors,
        )
