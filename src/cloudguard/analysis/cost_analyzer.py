from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from cloudguard.analysis.anomaly_detector import to_cost_dataframe
from cloudguard.core.models import CostRecord


class CostAnalyzer:
    def __init__(self, data: pd.DataFrame | Sequence[CostRecord] | None = None) -> None:
        self._raw_data = data

    def calculate_mom_growth(
        self,
        data: pd.DataFrame | Sequence[CostRecord] | None = None,
    ) -> dict[str, Any]:
        target_data = data if data is not None else self._raw_data
        df = to_cost_dataframe(target_data)
        if df.empty:
            return {
                "monthly_totals": {},
                "overall_mom_pct": 0.0,
                "monthly_growth_breakdown": [],
                "service_mom_growth": {},
            }

        df = df.copy()
        df["month"] = df["date"].dt.to_period("M").astype(str)

        monthly_totals = df.groupby("month")["amount"].sum().round(2).to_dict()
        sorted_months = sorted(monthly_totals.keys())

        growth_breakdown = []
        for i in range(len(sorted_months)):
            m = sorted_months[i]
            cur_amt = monthly_totals[m]
            if i > 0:
                prev_m = sorted_months[i - 1]
                prev_amt = monthly_totals[prev_m]
                diff = cur_amt - prev_amt
                pct = ((diff / prev_amt) * 100.0) if prev_amt > 0 else 0.0
            else:
                diff = 0.0
                pct = 0.0

            growth_breakdown.append(
                {
                    "month": m,
                    "total_cost": cur_amt,
                    "change_amount": round(diff, 2),
                    "growth_pct": round(pct, 2),
                }
            )

        overall_mom = growth_breakdown[-1]["growth_pct"] if len(growth_breakdown) > 1 else 0.0

        service_monthly = df.groupby(["service", "month"])["amount"].sum().unstack(fill_value=0.0)
        service_mom = {}
        if len(sorted_months) >= 2:
            last_m = sorted_months[-1]
            prev_m = sorted_months[-2]
            for svc in service_monthly.index:
                cur_val = float(service_monthly.loc[svc, last_m])
                prev_val = float(service_monthly.loc[svc, prev_m])
                diff_val = cur_val - prev_val
                growth_rate = (
                    ((diff_val / prev_val) * 100.0)
                    if prev_val > 0
                    else (100.0 if cur_val > 0 else 0.0)
                )
                service_mom[svc] = {
                    "previous_month_cost": round(prev_val, 2),
                    "current_month_cost": round(cur_val, 2),
                    "change_amount": round(diff_val, 2),
                    "growth_pct": round(growth_rate, 2),
                }

        return {
            "monthly_totals": monthly_totals,
            "overall_mom_pct": round(overall_mom, 2),
            "monthly_growth_breakdown": growth_breakdown,
            "service_mom_growth": service_mom,
        }

    def calculate_daily_burn_rate(
        self,
        data: pd.DataFrame | Sequence[CostRecord] | None = None,
    ) -> dict[str, Any]:
        target_data = data if data is not None else self._raw_data
        df = to_cost_dataframe(target_data)
        if df.empty:
            return {
                "average_daily_cost": 0.0,
                "recent_7d_average": 0.0,
                "recent_30d_average": 0.0,
                "projected_monthly_run_rate": 0.0,
                "daily_std": 0.0,
                "min_daily_cost": 0.0,
                "max_daily_cost": 0.0,
                "daily_totals": {},
            }

        daily = df.groupby(df["date"].dt.date)["amount"].sum().sort_index()
        daily_dict = {d.isoformat(): round(float(v), 2) for d, v in daily.items()}

        total_mean = float(daily.mean())
        total_std = float(daily.std()) if len(daily) > 1 else 0.0
        min_cost = float(daily.min())
        max_cost = float(daily.max())

        recent_7d = float(daily.tail(7).mean()) if len(daily) >= 1 else 0.0
        recent_30d = float(daily.tail(30).mean()) if len(daily) >= 1 else 0.0
        run_rate_30d = recent_30d * 30.0 if recent_30d > 0 else total_mean * 30.0

        return {
            "average_daily_cost": round(total_mean, 2),
            "recent_7d_average": round(recent_7d, 2),
            "recent_30d_average": round(recent_30d, 2),
            "projected_monthly_run_rate": round(run_rate_30d, 2),
            "daily_std": round(total_std, 2),
            "min_daily_cost": round(min_cost, 2),
            "max_daily_cost": round(max_cost, 2),
            "daily_totals": daily_dict,
        }

    def identify_top_cost_drivers(
        self,
        data: pd.DataFrame | Sequence[CostRecord] | None = None,
        top_n: int = 5,
    ) -> list[dict[str, Any]]:
        target_data = data if data is not None else self._raw_data
        df = to_cost_dataframe(target_data)
        if df.empty:
            return []

        total_spend = df["amount"].sum()
        if total_spend <= 0:
            total_spend = 1e-6

        grouped = (
            df.groupby("service")
            .agg(
                total_cost=("amount", "sum"),
                record_count=("amount", "count"),
                daily_avg=("amount", "mean"),
            )
            .sort_values(by="total_cost", ascending=False)
        )

        top_drivers: list[dict[str, Any]] = []
        for svc, row in grouped.head(top_n).iterrows():
            cost_val = float(row["total_cost"])
            pct = (cost_val / total_spend) * 100.0

            svc_daily = (
                df[df["service"] == svc].groupby(df["date"].dt.date)["amount"].sum().sort_index()
            )
            trend = "stable"
            if len(svc_daily) >= 4:
                first_half = float(svc_daily.head(len(svc_daily) // 2).mean())
                second_half = float(svc_daily.tail(len(svc_daily) // 2).mean())
                if second_half > first_half * 1.05:
                    trend = "growing"
                elif second_half < first_half * 0.95:
                    trend = "declining"

            top_drivers.append(
                {
                    "service": str(svc),
                    "total_cost": round(cost_val, 2),
                    "percentage_of_total": round(pct, 2),
                    "record_count": int(row["record_count"]),
                    "daily_average": round(float(row["daily_avg"]), 2),
                    "trend": trend,
                }
            )

        return top_drivers

    def project_costs(
        self,
        data: pd.DataFrame | Sequence[CostRecord] | None = None,
        days_ahead: int = 30,
    ) -> dict[str, Any]:
        target_data = data if data is not None else self._raw_data
        df = to_cost_dataframe(target_data)
        if df.empty:
            return {
                "slope": 0.0,
                "intercept": 0.0,
                "r_squared": 0.0,
                "projected_cost_next_period": 0.0,
                "projections": [],
            }

        daily = df.groupby(df["date"].dt.date)["amount"].sum().sort_index()
        dates_list = list(daily.keys())
        y = np.array(daily.values, dtype=float)
        x = np.arange(len(y), dtype=float)

        if len(y) < 2:
            single_val = float(y[0]) if len(y) == 1 else 0.0
            last_date = dates_list[-1] if dates_list else date.today()
            proj = []
            for i in range(1, days_ahead + 1):
                proj_date = last_date + timedelta(days=i)
                proj.append(
                    {"date": proj_date.isoformat(), "projected_amount": round(single_val, 2)}
                )

            return {
                "slope": 0.0,
                "intercept": single_val,
                "r_squared": 1.0,
                "projected_cost_next_period": round(single_val * days_ahead, 2),
                "projections": proj,
            }

        slope, intercept, r_val, _, _ = stats.linregress(x, y)
        r_squared = float(r_val**2) if not np.isnan(r_val) else 0.0

        last_date = dates_list[-1]
        projections: list[dict[str, Any]] = []
        projected_total = 0.0

        for i in range(1, days_ahead + 1):
            future_x = len(y) - 1 + i
            projected_val = max(0.0, float(slope * future_x + intercept))
            projected_total += projected_val
            proj_date = last_date + timedelta(days=i)
            projections.append(
                {
                    "date": proj_date.isoformat(),
                    "projected_amount": round(projected_val, 2),
                }
            )

        return {
            "slope": round(float(slope), 4),
            "intercept": round(float(intercept), 2),
            "r_squared": round(r_squared, 4),
            "projected_cost_next_period": round(projected_total, 2),
            "projections": projections,
        }

    def get_service_breakdown_trends(
        self,
        data: pd.DataFrame | Sequence[CostRecord] | None = None,
    ) -> dict[str, Any]:
        target_data = data if data is not None else self._raw_data
        df = to_cost_dataframe(target_data)
        if df.empty:
            return {"services": {}, "region_totals": {}}

        svc_totals = df.groupby("service")["amount"].sum().round(2).to_dict()
        region_totals = df.groupby("region")["amount"].sum().round(2).to_dict()

        daily_pivot = (
            df.pivot_table(
                index=df["date"].dt.strftime("%Y-%m-%d"),
                columns="service",
                values="amount",
                aggfunc="sum",
                fill_value=0.0,
            )
            .round(2)
            .to_dict()
        )

        return {
            "service_totals": svc_totals,
            "region_totals": region_totals,
            "daily_by_service": daily_pivot,
        }

    def full_analysis(
        self,
        data: pd.DataFrame | Sequence[CostRecord] | None = None,
        days_ahead: int = 30,
        top_n: int = 5,
    ) -> dict[str, Any]:
        target_data = data if data is not None else self._raw_data
        df = to_cost_dataframe(target_data)

        return {
            "mom_growth": self.calculate_mom_growth(df),
            "burn_rate": self.calculate_daily_burn_rate(df),
            "top_cost_drivers": self.identify_top_cost_drivers(df, top_n=top_n),
            "projections": self.project_costs(df, days_ahead=days_ahead),
            "service_breakdown": self.get_service_breakdown_trends(df),
        }
