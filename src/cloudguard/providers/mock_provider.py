"""Mock Cloud Provider for local development, demos, testing, and benchmarks.

Generates realistic synthetic cloud resources, telemetry, cost records, and waste patterns
with deterministic pseudo-random distribution.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from typing import Any

from cloudguard.core.logging import get_logger
from cloudguard.core.models import (
    CloudProviderType,
    CloudResource,
    CostRecord,
    Granularity,
    ResourceStatus,
    ResourceType,
)
from cloudguard.providers.base import CloudProvider

logger = get_logger("providers.mock")

SERVICES = [
    ("Virtual Machines", ResourceType.VM, 150.0, 1200.0),
    ("Managed Disks", ResourceType.STORAGE, 20.0, 180.0),
    ("Object Storage", ResourceType.STORAGE, 15.0, 350.0),
    ("Relational Database", ResourceType.DATABASE, 80.0, 950.0),
    ("Container Service", ResourceType.CONTAINER, 120.0, 800.0),
    ("Load Balancers", ResourceType.NETWORK, 25.0, 150.0),
    ("Serverless Functions", ResourceType.SERVERLESS, 5.0, 95.0),
]

REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1", "eastus", "westeurope"]


class MockProvider(CloudProvider):
    """Synthetic cloud provider generating deterministic enterprise infrastructure data."""

    def __init__(
        self,
        seed: int = 42,
        resource_count: int = 50,
        enable_anomalies: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.seed = seed
        self.resource_count = resource_count
        self.enable_anomalies = enable_anomalies
        self._rng = random.Random(self.seed)
        self._resources_cache: list[CloudResource] | None = None

    @property
    def provider_type(self) -> CloudProviderType:
        return CloudProviderType.MOCK

    def provider_name(self) -> str:
        return "Mock Enterprise Cloud (Azure/AWS Hybrid)"

    async def test_connection(self) -> bool:
        """Mock connection is always successful."""
        return True

    def _generate_resources(self) -> list[CloudResource]:
        """Generate static inventory of cloud resources."""
        if self._resources_cache is not None:
            return self._resources_cache

        rng = random.Random(self.seed)
        resources: list[CloudResource] = []

        for i in range(self.resource_count):
            svc_name, res_type, min_c, max_c = rng.choice(SERVICES)
            region = rng.choice(REGIONS)
            monthly_cost = round(rng.uniform(min_c, max_c), 2)
            utilization = round(rng.uniform(15.0, 88.0), 1)

            tags: dict[str, str] = {}
            if rng.random() > 0.2:
                tags = {
                    "Environment": rng.choice(["production", "staging", "dev", "qa"]),
                    "Owner": rng.choice(["finops", "core-infra", "platform-ai", "backend-team"]),
                    "CostCenter": rng.choice(["CC-101", "CC-204", "CC-508"]),
                }

            res = CloudResource(
                id=f"mock-res-{i:04d}",
                name=f"{svc_name.lower().replace(' ', '-')}-{i:03d}",
                type=res_type,
                region=region,
                provider=CloudProviderType.MOCK,
                tags=tags,
                monthly_cost=monthly_cost,
                utilization_pct=utilization,
                status=ResourceStatus.RUNNING,
                created_at=datetime.utcnow() - timedelta(days=rng.randint(30, 365)),
                metadata={"service_name": svc_name, "is_attached": True},
            )
            resources.append(res)

        for i in range(3):
            res_id = f"mock-idle-vm-{i + 1}"
            resources.append(
                CloudResource(
                    id=res_id,
                    name=f"dev-gpu-instance-idle-{i + 1}",
                    type=ResourceType.VM,
                    region="us-east-1",
                    provider=CloudProviderType.MOCK,
                    tags={"Environment": "dev", "Owner": "ai-sandbox"},
                    monthly_cost=850.0 + (i * 120.0),
                    utilization_pct=rng.uniform(0.5, 3.2),
                    status=ResourceStatus.IDLE,
                    created_at=datetime.utcnow() - timedelta(days=60),
                    metadata={
                        "service_name": "Virtual Machines",
                        "is_attached": True,
                        "idle_days": 18,
                    },
                )
            )

        for i in range(3):
            res_id = f"mock-orphan-disk-{i + 1}"
            resources.append(
                CloudResource(
                    id=res_id,
                    name=f"unattached-ebs-volume-{i + 1}",
                    type=ResourceType.STORAGE,
                    region="eu-west-1",
                    provider=CloudProviderType.MOCK,
                    tags={},
                    monthly_cost=140.0 + (i * 45.0),
                    utilization_pct=0.0,
                    status=ResourceStatus.ORPHANED,
                    created_at=datetime.utcnow() - timedelta(days=90),
                    metadata={
                        "service_name": "Managed Disks",
                        "is_attached": False,
                        "detached_days": 45,
                    },
                )
            )

        resources.append(
            CloudResource(
                id="mock-underutilized-vm-1",
                name="prod-analytics-worker-overprovisioned",
                type=ResourceType.VM,
                region="us-west-2",
                provider=CloudProviderType.MOCK,
                tags={"Environment": "production", "Owner": "analytics"},
                monthly_cost=1100.0,
                utilization_pct=11.5,
                status=ResourceStatus.UNDERUTILIZED,
                created_at=datetime.utcnow() - timedelta(days=120),
                metadata={"service_name": "Virtual Machines", "is_attached": True},
            )
        )

        self._resources_cache = resources
        return resources

    async def list_resources(
        self,
        resource_types: list[ResourceType | str] | None = None,
    ) -> list[CloudResource]:
        """Return list of mock resources, filtered by type if specified."""
        resources = self._generate_resources()
        if not resource_types:
            return resources

        type_set = {
            t.value if isinstance(t, ResourceType) else str(t).lower() for t in resource_types
        }
        return [r for r in resources if r.type.value in type_set]

    async def get_resource_utilization(
        self,
        resource_id: str,
        period_days: int = 7,
    ) -> float:
        """Lookup utilization for a specific resource."""
        resources = self._generate_resources()
        for r in resources:
            if r.id == resource_id:
                return r.utilization_pct
        return 50.0

    async def get_idle_resources(
        self,
        threshold_pct: float = 5.0,
        period_days: int = 7,
    ) -> list[CloudResource]:
        """Filter resources below idle utilization threshold."""
        resources = self._generate_resources()
        return [
            r
            for r in resources
            if r.type in (ResourceType.VM, ResourceType.DATABASE)
            and r.utilization_pct < threshold_pct
        ]

    async def get_orphaned_storage(
        self,
        unused_days: int = 30,
    ) -> list[CloudResource]:
        """Filter unattached storage volumes or disks."""
        resources = self._generate_resources()
        return [
            r
            for r in resources
            if r.type == ResourceType.STORAGE
            and (r.status == ResourceStatus.ORPHANED or r.metadata.get("is_attached") is False)
        ]

    async def get_cost_data(
        self,
        start_date: date,
        end_date: date,
        granularity: Granularity = Granularity.DAILY,
    ) -> list[CostRecord]:
        """Generate daily cost records across all services with seasonal trend and optional anomalies."""
        resources = self._generate_resources()
        records: list[CostRecord] = []
        rng = random.Random(self.seed + 101)

        cur_date = start_date
        days = (end_date - start_date).days + 1

        service_baselines: dict[str, float] = {
            "Virtual Machines": 850.0,
            "Managed Disks": 180.0,
            "Object Storage": 220.0,
            "Relational Database": 490.0,
            "Container Service": 310.0,
            "Load Balancers": 95.0,
            "Serverless Functions": 45.0,
        }

        anomaly_dates = set()
        if self.enable_anomalies and days >= 7:
            anomaly_dates.add(end_date - timedelta(days=3))
            anomaly_dates.add(end_date - timedelta(days=12))

        while cur_date <= end_date:
            weekday = cur_date.weekday()
            seasonality = 0.85 if weekday in (5, 6) else 1.05

            for svc, base_cost in service_baselines.items():
                noise = rng.uniform(-0.08, 0.08)
                daily_cost = base_cost * seasonality * (1.0 + noise)

                if cur_date in anomaly_dates:
                    if svc == "Virtual Machines":
                        daily_cost *= 3.8
                    elif svc == "Object Storage":
                        daily_cost *= 2.9

                region = rng.choice(REGIONS)
                matching_res = next(
                    (r for r in resources if r.metadata.get("service_name") == svc), None
                )

                record = CostRecord(
                    resource_id=matching_res.id if matching_res else None,
                    resource_name=matching_res.name if matching_res else None,
                    service=svc,
                    date=cur_date,
                    amount=round(daily_cost, 2),
                    currency="USD",
                    provider=CloudProviderType.MOCK,
                    region=region,
                    usage_type=f"{svc} Consumption",
                    tags=matching_res.tags if matching_res else {},
                )
                records.append(record)

            cur_date += timedelta(days=1)

        return records

    def generate_benchmark_records(self, count: int = 100_000) -> list[CostRecord]:
        """Generate N synthetic records for performance testing and benchmarking."""
        rng = random.Random(self.seed)
        records: list[CostRecord] = []
        base_date = date(2026, 1, 1)

        services_list = [s[0] for s in SERVICES]

        for i in range(count):
            svc = services_list[i % len(services_list)]
            d = base_date + timedelta(days=(i % 90))
            amount = round(rng.uniform(5.0, 500.0), 2)
            region = REGIONS[i % len(REGIONS)]

            records.append(
                CostRecord(
                    id=f"bench-{i:07d}",
                    resource_id=f"res-{i % 1000:04d}",
                    service=svc,
                    date=d,
                    amount=amount,
                    currency="USD",
                    provider=CloudProviderType.MOCK,
                    region=region,
                )
            )
        return records
