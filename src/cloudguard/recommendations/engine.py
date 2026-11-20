from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from cloudguard.core.models import (
    CloudResource,
    CostRecord,
    Recommendation,
    RecommendationPriority,
    ScanResult,
)
from cloudguard.recommendations.estimator import SavingsEstimator
from cloudguard.recommendations.rules import (
    IdleVMRule,
    OldSnapshotRule,
    OptimizationRule,
    OrphanedDiskRule,
    OrphanedIPRule,
    OversizedVMRule,
    ReservedInstanceRule,
    StorageClassRule,
    UntaggedResourceRule,
)


class RecommendationEngine:
    def __init__(
        self,
        rules: list[OptimizationRule] | None = None,
        estimator: SavingsEstimator | None = None,
    ) -> None:
        if rules is not None:
            self.rules = list(rules)
        else:
            self.rules = [
                IdleVMRule(),
                OversizedVMRule(),
                OrphanedDiskRule(),
                OrphanedIPRule(),
                OldSnapshotRule(),
                ReservedInstanceRule(),
                StorageClassRule(),
                UntaggedResourceRule(),
            ]
        self.estimator = estimator or SavingsEstimator()

    def add_rule(self, rule: OptimizationRule) -> None:
        self.rules.append(rule)

    def remove_rule(self, rule_id: str) -> None:
        self.rules = [r for r in self.rules if r.rule_id != rule_id]

    def _extract_resources(
        self,
        target: ScanResult | Sequence[CloudResource],
    ) -> list[CloudResource]:
        if isinstance(target, ScanResult):
            all_res: list[CloudResource] = []
            seen_ids: set[str] = set()
            for r in (
                target.idle_resources
                + target.orphaned_storage
                + target.underutilized_vms
                + target.untagged_resources
            ):
                if r.id not in seen_ids:
                    seen_ids.add(r.id)
                    all_res.append(r)
            return all_res

        seen: set[str] = set()
        unique_res: list[CloudResource] = []
        for r in target:
            if r.id not in seen:
                seen.add(r.id)
                unique_res.append(r)
        return unique_res

    def analyze(
        self,
        scan_result: ScanResult | Sequence[CloudResource],
        cost_data: list[CostRecord] | None = None,
    ) -> list[Recommendation]:
        resources = self._extract_resources(scan_result)
        if not resources:
            return []

        all_recommendations: list[Recommendation] = []
        seen_rec_keys: set[tuple[str, str]] = set()

        for rule in self.rules:
            recs = rule.evaluate_batch(resources, cost_data=cost_data)
            for rec in recs:
                rec_key = (rec.resource_id, rec.action)
                if rec_key not in seen_rec_keys:
                    seen_rec_keys.add(rec_key)
                    all_recommendations.append(rec)

        prio_rank = {
            RecommendationPriority.URGENT: 4,
            RecommendationPriority.HIGH: 3,
            RecommendationPriority.MEDIUM: 2,
            RecommendationPriority.LOW: 1,
        }

        all_recommendations.sort(
            key=lambda x: (
                -prio_rank.get(x.priority, 1),
                -x.estimated_savings,
                -x.confidence,
            )
        )

        return all_recommendations

    def get_top_recommendations(
        self,
        recommendations: list[Recommendation],
        limit: int = 5,
    ) -> list[Recommendation]:
        return recommendations[:limit]

    def estimate_savings(
        self,
        recommendations: list[Recommendation],
    ) -> dict[str, Any]:
        return self.estimator.summarize(recommendations)
