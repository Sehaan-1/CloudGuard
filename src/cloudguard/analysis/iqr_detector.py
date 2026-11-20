from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime

import numpy as np
import pandas as pd

from cloudguard.analysis.anomaly_detector import AnomalyDetectionStrategy, to_cost_dataframe
from cloudguard.core.models import AnomalyResult, CostRecord, Severity


class IQRDetector(AnomalyDetectionStrategy):
    def __init__(
        self,
        multiplier: float = 1.5,
        group_by: str | list[str] | None = "service",
        min_samples: int = 4,
        direction: str = "high",
    ) -> None:
        self.multiplier = float(multiplier)
        self.group_by = [group_by] if isinstance(group_by, str) else group_by
        self.min_samples = max(3, int(min_samples))
        self.direction = direction.lower()

    def _determine_severity(self, deviation_ratio: float) -> Severity:
        abs_dev = abs(deviation_ratio)
        if abs_dev >= 3.5:
            return Severity.CRITICAL
        if abs_dev >= 2.5:
            return Severity.HIGH
        if abs_dev >= 1.5:
            return Severity.MEDIUM
        return Severity.LOW

    def detect(
        self,
        data: pd.DataFrame | Sequence[CostRecord],
        column: str = "amount",
    ) -> list[AnomalyResult]:
        df = to_cost_dataframe(data)
        if df.empty or column not in df.columns:
            return []

        df = df.sort_values(by=["date"]).reset_index(drop=True)
        results: list[AnomalyResult] = []

        if self.group_by and all(g in df.columns for g in self.group_by):
            groups = df.groupby(self.group_by, group_keys=False)
            for _, group_df in groups:
                group_results = self._detect_in_group(group_df, column)
                results.extend(group_results)
        else:
            results = self._detect_in_group(df, column)

        results.sort(key=lambda x: (-x.deviation_score, x.date))
        return results

    def _detect_in_group(self, group_df: pd.DataFrame, column: str) -> list[AnomalyResult]:
        if len(group_df) < self.min_samples:
            return []

        group_df = group_df.sort_values(by="date").copy()
        values = group_df[column].astype(float)
        anomalies: list[AnomalyResult] = []

        q1 = float(np.percentile(values, 25))
        q3 = float(np.percentile(values, 75))
        iqr = max(q3 - q1, 1e-6)
        median_val = float(np.median(values))

        upper_bound = q3 + self.multiplier * iqr
        lower_bound = max(0.0, q1 - self.multiplier * iqr)

        for idx, val in values.items():
            is_anomaly = False
            deviation = 0.0

            if val > upper_bound and self.direction in ("high", "both"):
                is_anomaly = True
                deviation = (val - q3) / iqr
            elif val < lower_bound and self.direction in ("low", "both"):
                is_anomaly = True
                deviation = (q1 - val) / iqr

            if is_anomaly:
                row = group_df.loc[idx]
                actual_cost = float(val)
                expected_cost = max(0.0, median_val)
                sev = self._determine_severity(deviation)
                service_name = str(row.get("service", "unknown"))
                res_id = (
                    str(row.get("resource_id", "")) if pd.notna(row.get("resource_id")) else None
                )

                row_date = row["date"]
                if isinstance(row_date, (pd.Timestamp, datetime)):
                    rec_date = row_date.date()
                elif isinstance(row_date, date):
                    rec_date = row_date
                else:
                    rec_date = pd.to_datetime(row_date).date()

                desc = (
                    f"IQR anomaly detected in {service_name}: Cost ${actual_cost:.2f} "
                    f"exceeds upper threshold ${upper_bound:.2f} (IQR deviation {deviation:.2f}x)."
                )

                anomalies.append(
                    AnomalyResult(
                        id=str(uuid.uuid4()),
                        resource_id=res_id,
                        service=service_name,
                        date=rec_date,
                        expected_cost=round(expected_cost, 2),
                        actual_cost=round(actual_cost, 2),
                        deviation_score=round(deviation, 2),
                        severity=sev,
                        method="iqr",
                        description=desc,
                        is_anomaly=True,
                        resolved=False,
                        detected_at=datetime.utcnow(),
                        metadata={
                            "multiplier": self.multiplier,
                            "q1": round(q1, 2),
                            "q3": round(q3, 2),
                            "iqr": round(iqr, 2),
                            "upper_bound": round(upper_bound, 2),
                            "lower_bound": round(lower_bound, 2),
                        },
                    )
                )

        return anomalies
