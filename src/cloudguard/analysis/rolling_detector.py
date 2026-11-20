from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime

import numpy as np
import pandas as pd

from cloudguard.analysis.anomaly_detector import AnomalyDetectionStrategy, to_cost_dataframe
from cloudguard.core.models import AnomalyResult, CostRecord, Severity


class RollingWindowDetector(AnomalyDetectionStrategy):
    def __init__(
        self,
        window: int = 14,
        std_dev_multiplier: float = 2.5,
        method: str = "mean",
        alpha: float = 0.3,
        group_by: str | list[str] | None = "service",
        min_periods: int = 5,
        direction: str = "high",
    ) -> None:
        self.window = max(3, int(window))
        self.std_dev_multiplier = float(std_dev_multiplier)
        self.method = method.lower()
        self.alpha = float(alpha)
        self.group_by = [group_by] if isinstance(group_by, str) else group_by
        self.min_periods = max(2, int(min_periods))
        self.direction = direction.lower()

    def _determine_severity(self, deviation_score: float) -> Severity:
        abs_score = abs(deviation_score)
        if abs_score >= 4.0:
            return Severity.CRITICAL
        if abs_score >= 3.0:
            return Severity.HIGH
        if abs_score >= 2.0:
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
        if len(group_df) < self.min_periods:
            return []

        group_df = group_df.sort_values(by="date").copy()
        values = group_df[column].astype(float)
        anomalies: list[AnomalyResult] = []

        shifted_values = values.shift(1)

        if self.method == "ewm":
            rolling_center = shifted_values.ewm(
                alpha=self.alpha, min_periods=self.min_periods
            ).mean()
            rolling_std = shifted_values.ewm(alpha=self.alpha, min_periods=self.min_periods).std()
        else:
            rolling_center = shifted_values.rolling(
                window=self.window, min_periods=self.min_periods
            ).mean()
            rolling_std = shifted_values.rolling(
                window=self.window, min_periods=self.min_periods
            ).std()

        fallback_mean = values.mean()
        fallback_std = values.std()
        if np.isnan(fallback_std) or fallback_std == 0:
            fallback_std = 1e-6

        rolling_center = rolling_center.fillna(fallback_mean)
        rolling_std = rolling_std.fillna(fallback_std).replace(0.0, 1e-6)

        upper_bound = rolling_center + self.std_dev_multiplier * rolling_std
        lower_bound = (rolling_center - self.std_dev_multiplier * rolling_std).clip(lower=0.0)

        for idx, val in values.items():
            center_val = float(rolling_center.loc[idx])
            std_val = float(rolling_std.loc[idx])
            up_val = float(upper_bound.loc[idx])
            low_val = float(lower_bound.loc[idx])

            is_anomaly = False
            dev_score = 0.0

            if val > up_val and self.direction in ("high", "both"):
                is_anomaly = True
                dev_score = (val - center_val) / max(std_val, 1e-6)
            elif val < low_val and self.direction in ("low", "both"):
                is_anomaly = True
                dev_score = (center_val - val) / max(std_val, 1e-6)

            if is_anomaly:
                row = group_df.loc[idx]
                actual_cost = float(val)
                expected_cost = max(0.0, center_val)
                sev = self._determine_severity(dev_score)
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
                    f"Rolling window anomaly in {service_name}: Cost ${actual_cost:.2f} "
                    f"exceeds rolling baseline ${expected_cost:.2f} by {dev_score:.2f} standard deviations."
                )

                anomalies.append(
                    AnomalyResult(
                        id=str(uuid.uuid4()),
                        resource_id=res_id,
                        service=service_name,
                        date=rec_date,
                        expected_cost=round(expected_cost, 2),
                        actual_cost=round(actual_cost, 2),
                        deviation_score=round(dev_score, 2),
                        severity=sev,
                        method=f"rolling_{self.method}",
                        description=desc,
                        is_anomaly=True,
                        resolved=False,
                        detected_at=datetime.utcnow(),
                        metadata={
                            "window": self.window,
                            "method": self.method,
                            "upper_bound": round(up_val, 2),
                            "lower_bound": round(low_val, 2),
                        },
                    )
                )

        return anomalies
