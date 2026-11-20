from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime

import pandas as pd

from cloudguard.core.models import AnomalyResult, CostRecord, Severity


def to_cost_dataframe(data: pd.DataFrame | Sequence[CostRecord]) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        df = data.copy()
        if "date" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["date"]):
            df["date"] = pd.to_datetime(df["date"])
        return df

    if not data:
        return pd.DataFrame(
            columns=[
                "id",
                "resource_id",
                "resource_name",
                "service",
                "date",
                "amount",
                "currency",
                "provider",
                "region",
                "usage_type",
                "tags",
            ]
        )

    records_data = []
    for r in data:
        p_val = r.provider.value if hasattr(r.provider, "value") else str(r.provider)
        records_data.append(
            {
                "id": r.id,
                "resource_id": r.resource_id,
                "resource_name": r.resource_name,
                "service": r.service,
                "date": pd.to_datetime(r.date),
                "amount": float(r.amount),
                "currency": r.currency,
                "provider": p_val,
                "region": r.region,
                "usage_type": r.usage_type,
                "tags": r.tags,
            }
        )

    return pd.DataFrame(records_data)


class AnomalyDetectionStrategy(ABC):
    @abstractmethod
    def detect(
        self,
        data: pd.DataFrame | Sequence[CostRecord],
        column: str = "amount",
    ) -> list[AnomalyResult]:
        pass

    def detect_records(
        self,
        records: Sequence[CostRecord],
        column: str = "amount",
    ) -> list[AnomalyResult]:
        return self.detect(records, column=column)


class CompositeDetector(AnomalyDetectionStrategy):
    def __init__(
        self,
        strategies: Sequence[AnomalyDetectionStrategy] | None = None,
        min_votes: int = 1,
    ) -> None:
        self.strategies = list(strategies) if strategies is not None else []
        self.min_votes = max(1, min_votes)

    def add_strategy(self, strategy: AnomalyDetectionStrategy) -> None:
        self.strategies.append(strategy)

    def detect(
        self,
        data: pd.DataFrame | Sequence[CostRecord],
        column: str = "amount",
    ) -> list[AnomalyResult]:
        if not self.strategies:
            return []

        all_detections: list[list[AnomalyResult]] = []
        for strategy in self.strategies:
            detections = strategy.detect(data, column=column)
            all_detections.append(detections)

        grouped: dict[tuple[str, str, date], list[AnomalyResult]] = defaultdict(list)
        for detections in all_detections:
            for result in detections:
                res_id = result.resource_id or ""
                key = (res_id, result.service, result.date)
                grouped[key].append(result)

        severity_rank = {
            Severity.LOW: 1,
            Severity.MEDIUM: 2,
            Severity.HIGH: 3,
            Severity.CRITICAL: 4,
        }
        rank_to_severity = {v: k for k, v in severity_rank.items()}

        composite_results: list[AnomalyResult] = []
        for (res_id, service, anomaly_date), results in grouped.items():
            if len(results) >= self.min_votes:
                methods = sorted({r.method for r in results})
                max_dev = max(r.deviation_score for r in results)
                avg_expected = sum(r.expected_cost for r in results) / len(results)
                actual_cost = results[0].actual_cost
                highest_rank = max(severity_rank.get(r.severity, 2) for r in results)
                final_severity = rank_to_severity.get(highest_rank, Severity.MEDIUM)

                desc = (
                    f"Composite anomaly detected across {len(results)}/{len(self.strategies)} "
                    f"algorithms ({', '.join(methods)}). Expected: ${avg_expected:.2f}, "
                    f"Actual: ${actual_cost:.2f} (Deviation: {max_dev:.2f}x)"
                )

                composite_results.append(
                    AnomalyResult(
                        id=str(uuid.uuid4()),
                        resource_id=res_id if res_id else None,
                        service=service,
                        date=anomaly_date,
                        expected_cost=round(avg_expected, 2),
                        actual_cost=round(actual_cost, 2),
                        deviation_score=round(max_dev, 2),
                        severity=final_severity,
                        method=f"composite({'+'.join(methods)})",
                        description=desc,
                        is_anomaly=True,
                        resolved=False,
                        detected_at=datetime.utcnow(),
                        metadata={
                            "votes": len(results),
                            "total_strategies": len(self.strategies),
                            "participating_methods": methods,
                        },
                    )
                )

        composite_results.sort(key=lambda x: (-x.deviation_score, x.date))
        return composite_results
