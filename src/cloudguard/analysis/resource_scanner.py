from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from cloudguard.core.models import (
    CloudProviderType,
    CloudResource,
    ResourceStatus,
    ResourceType,
    ScanResult,
)


class ResourceScanner:
    def __init__(
        self,
        idle_cpu_threshold_pct: float = 5.0,
        idle_period_days: int = 7,
        orphaned_days: int = 30,
        underutilized_threshold_pct: float = 20.0,
        required_tags: list[str] | None = None,
    ) -> None:
        self.idle_cpu_threshold_pct = float(idle_cpu_threshold_pct)
        self.idle_period_days = int(idle_period_days)
        self.orphaned_days = int(orphaned_days)
        self.underutilized_threshold_pct = float(underutilized_threshold_pct)
        self.required_tags = required_tags or ["Environment", "Owner", "Project"]

    def find_idle_vms(
        self,
        resources: Sequence[CloudResource],
        threshold_pct: float | None = None,
        min_days: int | None = None,
    ) -> list[CloudResource]:
        th = threshold_pct if threshold_pct is not None else self.idle_cpu_threshold_pct
        idle_list: list[CloudResource] = []

        for r in resources:
            if r.type != ResourceType.VM:
                continue

            is_idle_status = r.status == ResourceStatus.IDLE
            is_low_util = r.utilization_pct < th
            is_stopped = r.status == ResourceStatus.STOPPED

            if is_idle_status or is_low_util or is_stopped:
                idle_list.append(r)

        return idle_list

    def find_orphaned_disks(
        self,
        resources: Sequence[CloudResource],
        unused_days: int | None = None,
    ) -> list[CloudResource]:
        orphaned_list: list[CloudResource] = []

        for r in resources:
            if r.type != ResourceType.STORAGE:
                continue

            is_unattached = r.metadata.get("is_attached") is False
            is_orphaned_status = r.status == ResourceStatus.ORPHANED
            is_unattached_tag = r.tags.get("attached", "").lower() == "false"

            if is_unattached or is_orphaned_status or is_unattached_tag:
                orphaned_list.append(r)

        return orphaned_list

    def find_orphaned_storage(
        self,
        resources: Sequence[CloudResource],
        unused_days: int | None = None,
    ) -> list[CloudResource]:
        orphaned_list: list[CloudResource] = []

        for r in resources:
            if r.type != ResourceType.STORAGE:
                continue

            is_orphaned = r.is_orphaned
            is_empty_or_unused = r.metadata.get("days_since_last_access", 0) >= (
                unused_days or self.orphaned_days
            )

            if is_orphaned or is_empty_or_unused:
                orphaned_list.append(r)

        return orphaned_list

    def find_underutilized_resources(
        self,
        resources: Sequence[CloudResource],
        threshold_pct: float | None = None,
    ) -> list[CloudResource]:
        th = threshold_pct if threshold_pct is not None else self.underutilized_threshold_pct
        idle_th = self.idle_cpu_threshold_pct
        underutilized_list: list[CloudResource] = []

        for r in resources:
            if r.type not in (ResourceType.VM, ResourceType.DATABASE, ResourceType.CONTAINER):
                continue

            if idle_th <= r.utilization_pct < th and r.status != ResourceStatus.STOPPED:
                underutilized_list.append(r)

        return underutilized_list

    def find_untagged_resources(
        self,
        resources: Sequence[CloudResource],
        required_tags: list[str] | None = None,
    ) -> list[CloudResource]:
        tags_to_check = required_tags if required_tags is not None else self.required_tags
        tags_lower = [t.lower() for t in tags_to_check]
        untagged_list: list[CloudResource] = []

        for r in resources:
            if not r.tags:
                untagged_list.append(r)
                continue

            existing_lower = {k.lower() for k in r.tags}
            missing = [t for t in tags_lower if t not in existing_lower]
            if missing:
                untagged_list.append(r)

        return untagged_list

    def calculate_total_waste(
        self,
        idle_resources: Sequence[CloudResource],
        orphaned_storage: Sequence[CloudResource],
        underutilized: Sequence[CloudResource],
    ) -> float:
        idle_waste = sum(r.monthly_cost for r in idle_resources)
        orphan_waste = sum(r.monthly_cost for r in orphaned_storage)
        underutil_waste = sum(
            r.monthly_cost * (1.0 - (r.utilization_pct / 100.0)) for r in underutilized
        )
        return round(idle_waste + orphan_waste + underutil_waste, 2)

    def scan(
        self,
        resources: Sequence[CloudResource],
        provider: CloudProviderType = CloudProviderType.MOCK,
    ) -> ScanResult:
        idle = self.find_idle_vms(resources)
        orphaned = self.find_orphaned_storage(resources)
        underutilized = self.find_underutilized_resources(resources)
        untagged = self.find_untagged_resources(resources)
        total_waste = self.calculate_total_waste(idle, orphaned, underutilized)

        return ScanResult(
            provider=provider,
            scanned_at=datetime.utcnow(),
            idle_resources=list(idle),
            orphaned_storage=list(orphaned),
            underutilized_vms=list(underutilized),
            untagged_resources=list(untagged),
            total_resources_scanned=len(resources),
            total_waste_monthly=total_waste,
            currency="USD",
        )

    def generate_waste_breakdown(self, scan_result: ScanResult) -> dict[str, Any]:
        idle_cost = sum(r.monthly_cost for r in scan_result.idle_resources)
        orphan_cost = sum(r.monthly_cost for r in scan_result.orphaned_storage)
        underutil_cost = sum(
            r.monthly_cost * (1.0 - (r.utilization_pct / 100.0))
            for r in scan_result.underutilized_vms
        )

        by_service: dict[str, float] = {}
        for r in (
            scan_result.idle_resources
            + scan_result.orphaned_storage
            + scan_result.underutilized_vms
        ):
            svc = r.type.value if hasattr(r.type, "value") else str(r.type)
            by_service[svc] = round(by_service.get(svc, 0.0) + r.monthly_cost, 2)

        return {
            "total_monthly_waste": scan_result.total_waste_monthly,
            "idle_vms_cost": round(idle_cost, 2),
            "idle_vms_count": len(scan_result.idle_resources),
            "orphaned_storage_cost": round(orphan_cost, 2),
            "orphaned_storage_count": len(scan_result.orphaned_storage),
            "underutilized_vms_cost": round(underutil_cost, 2),
            "underutilized_vms_count": len(scan_result.underutilized_vms),
            "untagged_resources_count": len(scan_result.untagged_resources),
            "waste_by_resource_type": by_service,
        }
