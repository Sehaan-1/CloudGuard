from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime

import numpy as np
import pandas as pd

from cloudguard.analysis.anomaly_detector import AnomalyDetectionStrategy, to_cost_dataframe
from cloudguard.core.models import AnomalyResult, CostRecord, Severity


class ZScoreDetector(AnomalyDetectionStrategy):
    def __init__(
        self,
        threshold: float = 3.0,
        use_rolling: bool = True,
        window: int = 30,
        min_periods: int = 7,
        group_by: str | list[str] | None = "service",
        direction: str = "high",
    ) -> None:
        self.threshold = float(threshold)
        self.use_rolling = use_rolling
        self.window = max(3, int(window))
        self.min_periods = max(2, int(min_periods))
        self.group_by = [group_by] if isinstance(group_by, str) else group_by
        self.direction = direction.lower()

    def _determine_severity(self, z_score: float) -> Severity:
        abs_z = abs(z_score)
        if abs_z >= 5.0:
            return Severity.CRITICAL
        if abs_z >= 4.0:
            return Severity.HIGH
        if abs_z >= 3.0:
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
        if len(group_df) < 2:
            return []

        group_df = group_df.sort_values(by="date").copy()
        values = group_df[column].astype(float)
        anomalies: list[AnomalyResult] = []

        if self.use_rolling and len(group_df) >= self.min_periods:
            rolling_mean = (
                values.shift(1).rolling(window=self.window, min_periods=self.min_periods).mean()
            )
            rolling_std = (
                values.shift(1).rolling(window=self.window, min_periods=self.min_periods).std()
            )

            fallback_mean = values.mean()
            fallback_std = values.std()
            if np.isnan(fallback_std) or fallback_std == 0:
                fallback_std = 1e-6

            rolling_mean = rolling_mean.fillna(fallback_mean)
            rolling_std = rolling_std.fillna(fallback_std).replace(0.0, 1e-6)

            z_scores = (values - rolling_mean) / rolling_std
            expected_series = rolling_mean
        else:
            mean_val = values.mean()
            std_val = values.std()
            if np.isnan(std_val) or std_val == 0:
                std_val = 1e-6
            z_scores = (values - mean_val) / std_val
            expected_series = pd.Series(mean_val, index=values.index)

        for idx, z in z_scores.items():
            if np.isnan(z):
                continue

            is_anomaly = False
            if (
                (self.direction == "high" and z >= self.threshold)
                or (self.direction == "low" and z <= -self.threshold)
                or (self.direction == "both" and abs(z) >= self.threshold)
            ):
                is_anomaly = True

            if is_anomaly:
                row = group_df.loc[idx]
                actual_cost = float(row[column])
                expected_cost = max(0.0, float(expected_series.loc[idx]))
                sev = self._determine_severity(float(z))
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
                    f"Z-Score anomaly detected in {service_name}: Cost ${actual_cost:.2f} "
                    f"deviates {float(z):.2f} standard deviations from expected ${expected_cost:.2f}."
                )

                anomalies.append(
                    AnomalyResult(
                        id=str(uuid.uuid4()),
                        resource_id=res_id,
                        service=service_name,
                        date=rec_date,
                        expected_cost=round(expected_cost, 2),
                        actual_cost=round(actual_cost, 2),
                        deviation_score=round(float(z), 2),
                        severity=sev,
                        method="zscore",
                        description=desc,
                        is_anomaly=True,
                        resolved=False,
                        detected_at=datetime.utcnow(),
                        metadata={
                            "threshold": self.threshold,
                            "use_rolling": self.use_rolling,
                            "window": self.window,
                        },
                    )
                )

        return anomalies
