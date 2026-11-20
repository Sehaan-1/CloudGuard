"""Abstract CloudProvider interface (Strategy Pattern).

Defines the contract that all concrete cloud providers (Azure, AWS, Mock, GCP)
must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any

from cloudguard.core.logging import get_logger
from cloudguard.core.models import (
    CloudProviderType,
    CloudResource,
    CostRecord,
    CostSummary,
    Granularity,
    ResourceStatus,
    ResourceType,
    ScanResult,
)

logger = get_logger("providers.base")


class CloudProvider(ABC):
    """Abstract Base Class for all Cloud Providers.

    Enforces uniform data access and monitoring contracts across diverse cloud APIs.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._extra_args = kwargs

    @property
    @abstractmethod
    def provider_type(self) -> CloudProviderType:
        """Returns the enum type of the provider."""
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """Returns the human-readable display name of the provider."""
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        """Validates credentials and API connectivity."""
        ...

    @abstractmethod
    async def get_cost_data(
        self,
        start_date: date,
        end_date: date,
        granularity: Granularity = Granularity.DAILY,
    ) -> list[CostRecord]:
        """Fetch normalized cost consumption records within the date window."""
        ...

    @abstractmethod
    async def list_resources(
        self,
        resource_types: list[ResourceType | str] | None = None,
    ) -> list[CloudResource]:
        """Discover active infrastructure resources."""
        ...

    @abstractmethod
    async def get_resource_utilization(
        self,
        resource_id: str,
        period_days: int = 7,
    ) -> float:
        """Retrieve aggregated percentage utilization for a resource (e.g. CPU/Memory)."""
        ...

    @abstractmethod
    async def get_idle_resources(
        self,
        threshold_pct: float = 5.0,
        period_days: int = 7,
    ) -> list[CloudResource]:
        """Identify compute or database instances running below the idle threshold."""
        ...

    @abstractmethod
    async def get_orphaned_storage(
        self,
        unused_days: int = 30,
    ) -> list[CloudResource]:
        """Identify unattached disks, snapshot relics, or abandoned buckets/volumes."""
        ...

    async def get_cost_summary(
        self,
        start_date: date,
        end_date: date,
    ) -> CostSummary:
        """Template method: computes summary metrics from normalized cost records."""
        records = await self.get_cost_data(start_date, end_date, Granularity.DAILY)
        return CostSummary.from_records(records, start_date, end_date)

    async def scan(
        self,
        idle_threshold_pct: float = 5.0,
        period_days: int = 7,
        orphaned_days: int = 30,
        underutilized_threshold_pct: float = 20.0,
    ) -> ScanResult:
        """Perform comprehensive infrastructure scan for waste and governance gaps."""
        logger.info(f"Starting audit scan on {self.provider_name()}...")

        all_resources = await self.list_resources()
        idle_res = await self.get_idle_resources(
            threshold_pct=idle_threshold_pct, period_days=period_days
        )
        orphaned_res = await self.get_orphaned_storage(unused_days=orphaned_days)

        underutilized_vms: list[CloudResource] = []
        untagged_res: list[CloudResource] = []

        idle_ids = {r.id for r in idle_res}

        for res in all_resources:
            if res.is_untagged:
                untagged_res.append(res)

            if (
                res.type == ResourceType.VM
                and res.id not in idle_ids
                and res.utilization_pct <= underutilized_threshold_pct
            ):
                underutilized_res = res.model_copy(update={"status": ResourceStatus.UNDERUTILIZED})
                underutilized_vms.append(underutilized_res)

        idle_waste = sum(r.monthly_cost for r in idle_res)
        orphan_waste = sum(r.monthly_cost for r in orphaned_res)
        downsizing_waste = sum(r.monthly_cost * 0.5 for r in underutilized_vms)
        total_waste = round(idle_waste + orphan_waste + downsizing_waste, 2)

        return ScanResult(
            provider=self.provider_type,
            scanned_at=datetime.utcnow(),
            idle_resources=idle_res,
            orphaned_storage=orphaned_res,
            underutilized_vms=underutilized_vms,
            untagged_resources=untagged_res,
            total_resources_scanned=len(all_resources),
            total_waste_monthly=total_waste,
            currency="USD",
        )
