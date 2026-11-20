from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from cloudguard.core.models import (
    Recommendation,
    RecommendationPriority,
)


class SavingsEstimator:
    @staticmethod
    def calculate_monthly_savings(recommendations: Sequence[Recommendation]) -> float:
        return round(sum(r.estimated_savings for r in recommendations), 2)

    @staticmethod
    def calculate_annual_savings(recommendations: Sequence[Recommendation]) -> float:
        return round(sum(r.estimated_savings * 12.0 for r in recommendations), 2)

    @staticmethod
    def calculate_savings_by_priority(
        recommendations: Sequence[Recommendation],
    ) -> dict[str, float]:
        res: dict[str, float] = {p.value: 0.0 for p in RecommendationPriority}
        for r in recommendations:
            p_val = r.priority.value if hasattr(r.priority, "value") else str(r.priority)
            res[p_val] = round(res.get(p_val, 0.0) + r.estimated_savings, 2)
        return res

    @staticmethod
    def calculate_savings_by_resource_type(
        recommendations: Sequence[Recommendation],
    ) -> dict[str, float]:
        res: dict[str, float] = {}
        for r in recommendations:
            t_val = (
                r.resource_type.value if hasattr(r.resource_type, "value") else str(r.resource_type)
            )
            res[t_val] = round(res.get(t_val, 0.0) + r.estimated_savings, 2)
        return res

    @staticmethod
    def calculate_savings_by_action(
        recommendations: Sequence[Recommendation],
    ) -> dict[str, float]:
        res: dict[str, float] = {}
        for r in recommendations:
            res[r.action] = round(res.get(r.action, 0.0) + r.estimated_savings, 2)
        return res

    def summarize(self, recommendations: Sequence[Recommendation]) -> dict[str, Any]:
        monthly = self.calculate_monthly_savings(recommendations)
        annual = self.calculate_annual_savings(recommendations)
        by_prio = self.calculate_savings_by_priority(recommendations)
        by_type = self.calculate_savings_by_resource_type(recommendations)
        by_action = self.calculate_savings_by_action(recommendations)

        quick_wins = sum(
            r.estimated_savings
            for r in recommendations
            if r.confidence >= 0.9
            and r.priority in (RecommendationPriority.HIGH, RecommendationPriority.URGENT)
        )

        return {
            "total_monthly_savings": monthly,
            "total_annual_savings": annual,
            "recommendation_count": len(recommendations),
            "quick_wins_monthly_savings": round(quick_wins, 2),
            "savings_by_priority": by_prio,
            "savings_by_resource_type": by_type,
            "savings_by_action": by_action,
        }
