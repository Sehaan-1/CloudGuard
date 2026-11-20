from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from cloudguard.core.models import (
    CloudResource,
    CostRecord,
    Recommendation,
    RecommendationPriority,
    RecommendationStatus,
    ResourceStatus,
    ResourceType,
)


class OptimizationRule(ABC):
    def __init__(
        self,
        rule_id: str,
        name: str,
        description: str,
        category: str = "general",
        default_priority: RecommendationPriority = RecommendationPriority.MEDIUM,
    ) -> None:
        self.rule_id = rule_id
        self.name = name
        self.description = description
        self.category = category
        self.default_priority = default_priority

    @abstractmethod
    def evaluate(
        self,
        resource: CloudResource,
        context: dict[str, Any] | None = None,
    ) -> Recommendation | None:
        pass

    def evaluate_batch(
        self,
        resources: Sequence[CloudResource],
        cost_data: Sequence[CostRecord] | None = None,
    ) -> list[Recommendation]:
        recs: list[Recommendation] = []
        ctx: dict[str, Any] = {"cost_data": cost_data} if cost_data is not None else {}
        for r in resources:
            rec = self.evaluate(r, context=ctx)
            if rec is not None:
                recs.append(rec)
        return recs


class IdleVMRule(OptimizationRule):
    def __init__(self) -> None:
        super().__init__(
            rule_id="RULE-001",
            name="Idle Virtual Machine Rule",
            description="Detects running compute instances with utilization below 5%",
            category="compute",
            default_priority=RecommendationPriority.HIGH,
        )

    def evaluate(
        self,
        resource: CloudResource,
        context: dict[str, Any] | None = None,
    ) -> Recommendation | None:
        if resource.type != ResourceType.VM:
            return None

        if not resource.is_idle:
            return None

        prio = (
            RecommendationPriority.URGENT
            if resource.monthly_cost >= 500.0
            else (
                RecommendationPriority.HIGH
                if resource.monthly_cost >= 150.0
                else RecommendationPriority.MEDIUM
            )
        )

        return Recommendation(
            id=str(uuid.uuid4()),
            resource_id=resource.id,
            resource_name=resource.name,
            action="terminate_idle",
            title=f"Stop or terminate idle VM '{resource.name}'",
            description=(
                f"Virtual machine '{resource.name}' is averaging {resource.utilization_pct:.1f}% CPU utilization (<5%). "
                f"Stopping or deleting this unutilized compute instance saves 100% of its monthly cost."
            ),
            estimated_savings=round(resource.monthly_cost, 2),
            currency=resource.currency if hasattr(resource, "currency") else "USD",
            confidence=0.95,
            priority=prio,
            resource_type=resource.type,
            provider=resource.provider,
            status=RecommendationStatus.OPEN,
        )


class OversizedVMRule(OptimizationRule):
    def __init__(self, target_downsize_pct: float = 0.4) -> None:
        super().__init__(
            rule_id="RULE-002",
            name="Oversized Virtual Machine Rule",
            description="Identifies underutilized instances operating below 20% capacity",
            category="compute",
            default_priority=RecommendationPriority.MEDIUM,
        )
        self.target_downsize_pct = target_downsize_pct

    def evaluate(
        self,
        resource: CloudResource,
        context: dict[str, Any] | None = None,
    ) -> Recommendation | None:
        if resource.type != ResourceType.VM:
            return None

        if resource.is_idle:
            return None

        is_underutilized = (
            resource.status == ResourceStatus.UNDERUTILIZED or resource.utilization_pct < 20.0
        )
        if not is_underutilized:
            return None

        savings = round(resource.monthly_cost * self.target_downsize_pct, 2)
        prio = RecommendationPriority.HIGH if savings >= 200.0 else RecommendationPriority.MEDIUM

        return Recommendation(
            id=str(uuid.uuid4()),
            resource_id=resource.id,
            resource_name=resource.name,
            action="rightsize_vm",
            title=f"Rightsize oversized VM '{resource.name}' to smaller SKU",
            description=(
                f"Instance '{resource.name}' operates at {resource.utilization_pct:.1f}% utilization (<20%). "
                f"Downsizing by one instance tier will safely handle load while reducing monthly spend by {int(self.target_downsize_pct * 100)}%."
            ),
            estimated_savings=savings,
            currency="USD",
            confidence=0.85,
            priority=prio,
            resource_type=resource.type,
            provider=resource.provider,
            status=RecommendationStatus.OPEN,
        )


class OrphanedDiskRule(OptimizationRule):
    def __init__(self) -> None:
        super().__init__(
            rule_id="RULE-003",
            name="Orphaned Storage Disk Rule",
            description="Identifies persistent disks and block volumes unattached from instances",
            category="storage",
            default_priority=RecommendationPriority.HIGH,
        )

    def evaluate(
        self,
        resource: CloudResource,
        context: dict[str, Any] | None = None,
    ) -> Recommendation | None:
        if resource.type != ResourceType.STORAGE:
            return None

        if not resource.is_orphaned:
            return None

        is_disk = (
            "disk" in resource.name.lower()
            or "volume" in resource.name.lower()
            or "ebs" in resource.name.lower()
            or "managed disk" in str(resource.metadata.get("service_name", "")).lower()
            or resource.metadata.get("is_attached") is False
        )

        if not is_disk:
            return None

        return Recommendation(
            id=str(uuid.uuid4()),
            resource_id=resource.id,
            resource_name=resource.name,
            action="delete_orphaned_disk",
            title=f"Delete unattached storage disk '{resource.name}'",
            description=(
                f"Block storage volume '{resource.name}' has been unattached for >30 days. "
                f"Deleting unassociated volumes removes unneeded persistent storage costs."
            ),
            estimated_savings=round(resource.monthly_cost, 2),
            currency="USD",
            confidence=0.98,
            priority=RecommendationPriority.HIGH,
            resource_type=resource.type,
            provider=resource.provider,
            status=RecommendationStatus.OPEN,
        )


class OrphanedIPRule(OptimizationRule):
    def __init__(self, default_ip_cost: float = 3.65) -> None:
        super().__init__(
            rule_id="RULE-004",
            name="Orphaned Public IP Rule",
            description="Identifies static or elastic IP addresses not associated with running workloads",
            category="network",
            default_priority=RecommendationPriority.LOW,
        )
        self.default_ip_cost = default_ip_cost

    def evaluate(
        self,
        resource: CloudResource,
        context: dict[str, Any] | None = None,
    ) -> Recommendation | None:
        if resource.type != ResourceType.NETWORK:
            return None

        is_ip = (
            "ip" in resource.name.lower()
            or "eip" in resource.name.lower()
            or "public-ip" in resource.name.lower()
            or "address" in resource.name.lower()
        )

        if not is_ip and not resource.is_orphaned:
            return None

        savings = resource.monthly_cost if resource.monthly_cost > 0 else self.default_ip_cost

        return Recommendation(
            id=str(uuid.uuid4()),
            resource_id=resource.id,
            resource_name=resource.name,
            action="release_orphaned_ip",
            title=f"Release unassociated public IP '{resource.name}'",
            description=(
                f"Allocated public IP '{resource.name}' is not bound to an active network interface. "
                f"Releasing unattached static addresses eliminates recurring reservation surcharges."
            ),
            estimated_savings=round(savings, 2),
            currency="USD",
            confidence=0.95,
            priority=RecommendationPriority.LOW,
            resource_type=resource.type,
            provider=resource.provider,
            status=RecommendationStatus.OPEN,
        )


class OldSnapshotRule(OptimizationRule):
    def __init__(self, age_days_threshold: int = 90) -> None:
        super().__init__(
            rule_id="RULE-005",
            name="Obsolete Backup Snapshot Rule",
            description="Flags snapshots and backups older than retention policy threshold",
            category="storage",
            default_priority=RecommendationPriority.LOW,
        )
        self.age_days_threshold = age_days_threshold

    def evaluate(
        self,
        resource: CloudResource,
        context: dict[str, Any] | None = None,
    ) -> Recommendation | None:
        if resource.type != ResourceType.STORAGE:
            return None

        is_snapshot = (
            "snapshot" in resource.name.lower()
            or "backup" in resource.name.lower()
            or resource.metadata.get("is_snapshot") is True
        )

        if not is_snapshot:
            return None

        age_days = resource.metadata.get("age_days")
        if age_days is None:
            age_days = (datetime.utcnow() - resource.created_at).days

        if age_days < self.age_days_threshold:
            return None

        savings = round(resource.monthly_cost * 0.8, 2) if resource.monthly_cost > 0 else 25.0

        return Recommendation(
            id=str(uuid.uuid4()),
            resource_id=resource.id,
            resource_name=resource.name,
            action="delete_old_snapshot",
            title=f"Delete or archive stale snapshot '{resource.name}'",
            description=(
                f"Backup snapshot '{resource.name}' is {age_days} days old (exceeds {self.age_days_threshold}-day policy). "
                f"Archiving or deleting obsolete snapshots recovers cumulative storage spend."
            ),
            estimated_savings=savings,
            currency="USD",
            confidence=0.90,
            priority=RecommendationPriority.LOW,
            resource_type=resource.type,
            provider=resource.provider,
            status=RecommendationStatus.OPEN,
        )


class ReservedInstanceRule(OptimizationRule):
    def __init__(self, discount_pct: float = 0.38) -> None:
        super().__init__(
            rule_id="RULE-006",
            name="Reserved Instance & Savings Plan Rule",
            description="Recommends 1-year or 3-year commitment plans for steady-state workloads",
            category="commitment",
            default_priority=RecommendationPriority.HIGH,
        )
        self.discount_pct = discount_pct

    def evaluate(
        self,
        resource: CloudResource,
        context: dict[str, Any] | None = None,
    ) -> Recommendation | None:
        if resource.type not in (ResourceType.VM, ResourceType.DATABASE):
            return None

        is_under = (
            resource.status == ResourceStatus.UNDERUTILIZED or resource.utilization_pct < 20.0
        )
        if resource.is_idle or is_under:
            return None

        if resource.status != ResourceStatus.RUNNING:
            return None

        age_days = (datetime.utcnow() - resource.created_at).days if resource.created_at else 0
        is_steady = (
            age_days >= 60
            or resource.monthly_cost >= 150.0
            or resource.metadata.get("steady_state") is True
        )

        if not is_steady:
            return None

        savings = round(resource.monthly_cost * self.discount_pct, 2)
        prio = RecommendationPriority.HIGH if savings >= 150.0 else RecommendationPriority.MEDIUM

        return Recommendation(
            id=str(uuid.uuid4()),
            resource_id=resource.id,
            resource_name=resource.name,
            action="purchase_reserved_instance",
            title=f"Purchase 1-Year / 3-Year Reservation for '{resource.name}'",
            description=(
                f"Workload '{resource.name}' has demonstrated persistent stable utilization. "
                f"Switching from on-demand to a 1-year or 3-year commitment provides ~{int(self.discount_pct * 100)}% monthly cost savings."
            ),
            estimated_savings=savings,
            currency="USD",
            confidence=0.88,
            priority=prio,
            resource_type=resource.type,
            provider=resource.provider,
            status=RecommendationStatus.OPEN,
        )


class StorageClassRule(OptimizationRule):
    def __init__(self, tier_discount_pct: float = 0.65) -> None:
        super().__init__(
            rule_id="RULE-007",
            name="Object Storage Lifecycle Tiering Rule",
            description="Recommends transition of infrequent data from Hot to Cold/Archive tiers",
            category="storage",
            default_priority=RecommendationPriority.MEDIUM,
        )
        self.tier_discount_pct = tier_discount_pct

    def evaluate(
        self,
        resource: CloudResource,
        context: dict[str, Any] | None = None,
    ) -> Recommendation | None:
        if resource.type != ResourceType.STORAGE:
            return None

        if resource.is_orphaned:
            return None

        is_object_store = (
            "object" in resource.name.lower()
            or "s3" in resource.name.lower()
            or "blob" in resource.name.lower()
            or "bucket" in resource.name.lower()
            or "object storage" in str(resource.metadata.get("service_name", "")).lower()
        )

        if not is_object_store:
            return None

        savings = round(resource.monthly_cost * self.tier_discount_pct, 2)
        if savings <= 0:
            savings = 30.0

        return Recommendation(
            id=str(uuid.uuid4()),
            resource_id=resource.id,
            resource_name=resource.name,
            action="tier_to_cold_storage",
            title=f"Transition storage bucket '{resource.name}' to Cold/Archive tier",
            description=(
                f"Storage container '{resource.name}' contains low-frequency read datasets in standard pricing tier. "
                f"Setting automatic lifecycle transition rules saves {int(self.tier_discount_pct * 100)}% on storage consumption."
            ),
            estimated_savings=savings,
            currency="USD",
            confidence=0.82,
            priority=RecommendationPriority.MEDIUM,
            resource_type=resource.type,
            provider=resource.provider,
            status=RecommendationStatus.OPEN,
        )


class UntaggedResourceRule(OptimizationRule):
    def __init__(self) -> None:
        super().__init__(
            rule_id="RULE-008",
            name="Untagged Resource Governance Rule",
            description="Flags assets lacking mandatory cost attribution and ownership tags",
            category="governance",
            default_priority=RecommendationPriority.LOW,
        )

    def evaluate(
        self,
        resource: CloudResource,
        context: dict[str, Any] | None = None,
    ) -> Recommendation | None:
        if not resource.is_untagged:
            return None

        return Recommendation(
            id=str(uuid.uuid4()),
            resource_id=resource.id,
            resource_name=resource.name,
            action="enforce_cost_allocation_tags",
            title=f"Apply mandatory cost tags to '{resource.name}'",
            description=(
                f"Asset '{resource.name}' has no cost allocation tags. "
                f"Assigning Owner, Environment, and CostCenter tags is required for cost tracking and chargeback compliance."
            ),
            estimated_savings=0.0,
            currency="USD",
            confidence=1.0,
            priority=RecommendationPriority.LOW,
            resource_type=resource.type,
            provider=resource.provider,
            status=RecommendationStatus.OPEN,
        )
