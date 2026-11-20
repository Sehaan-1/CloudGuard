"""Microsoft Azure Cloud Provider implementation.

Integrates with Azure Cost Management, Compute, Storage, and Azure Monitor APIs.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from cloudguard.core.config import Settings, get_settings
from cloudguard.core.exceptions import (
    AuthenticationError,
    ProviderConnectionError,
    ProviderError,
    RateLimitError,
)
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

logger = get_logger("providers.azure")

try:
    from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
    from azure.identity import ClientSecretCredential, DefaultAzureCredential
    from azure.mgmt.compute import ComputeManagementClient
    from azure.mgmt.costmanagement import CostManagementClient
    from azure.mgmt.costmanagement.models import (
        ExportType,
        QueryAggregation,
        QueryDataset,
        QueryDefinition,
        QueryGrouping,
        QueryTimePeriod,
        TimeframeType,
    )
    from azure.mgmt.monitor import MonitorManagementClient
    from azure.mgmt.storage import StorageManagementClient

    AZURE_SDK_AVAILABLE = True
except ImportError:
    AZURE_SDK_AVAILABLE = False


class AzureProvider(CloudProvider):
    """Concrete CloudProvider for Microsoft Azure enterprise infrastructure."""

    def __init__(
        self,
        subscription_id: str | None = None,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        settings: Settings | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        cfg = settings or get_settings()
        self.subscription_id = subscription_id or cfg.azure_subscription_id
        self.tenant_id = tenant_id or cfg.azure_tenant_id
        self.client_id = client_id or cfg.azure_client_id
        self.client_secret = client_secret or cfg.azure_client_secret

        self._credential = None
        self._cost_client: CostManagementClient | None = None
        self._compute_client: ComputeManagementClient | None = None
        self._storage_client: StorageManagementClient | None = None
        self._monitor_client: MonitorManagementClient | None = None

    @property
    def provider_type(self) -> CloudProviderType:
        return CloudProviderType.AZURE

    def provider_name(self) -> str:
        return "Microsoft Azure"

    def _ensure_authenticated(self) -> None:
        """Initialize Azure identity credentials and management clients."""
        if not AZURE_SDK_AVAILABLE:
            raise ProviderError(
                "Azure SDK packages are not installed. Install azure-mgmt-* and azure-identity.",
                provider="azure",
            )

        if not self.subscription_id:
            raise AuthenticationError(
                "Azure Subscription ID is missing. Set AZURE_SUBSCRIPTION_ID in environment.",
                provider="azure",
            )

        if self._credential is not None:
            return

        try:
            if self.tenant_id and self.client_id and self.client_secret:
                self._credential = ClientSecretCredential(
                    tenant_id=self.tenant_id,
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                )
            else:
                self._credential = DefaultAzureCredential()

            self._cost_client = CostManagementClient(credential=self._credential)
            self._compute_client = ComputeManagementClient(
                credential=self._credential, subscription_id=self.subscription_id
            )
            self._storage_client = StorageManagementClient(
                credential=self._credential, subscription_id=self.subscription_id
            )
            self._monitor_client = MonitorManagementClient(
                credential=self._credential, subscription_id=self.subscription_id
            )
        except Exception as e:
            logger.error(f"Failed to authenticate with Azure: {e}")
            raise AuthenticationError(
                f"Failed to authenticate with Azure: {e}", provider="azure"
            ) from e

    async def test_connection(self) -> bool:
        """Validate Azure authentication by testing compute client connection."""
        try:
            self._ensure_authenticated()
            assert self._compute_client is not None
            next(iter(self._compute_client.virtual_machines.list_all()), None)
            return True
        except ClientAuthenticationError as e:
            raise AuthenticationError(f"Azure authentication failed: {e}", provider="azure") from e
        except HttpResponseError as e:
            if e.status_code == 429:
                raise RateLimitError("Azure API rate limit reached", provider="azure") from e
            raise ProviderConnectionError(f"Azure connection error: {e}", provider="azure") from e
        except Exception as e:
            logger.warning(f"Azure connection test failed: {e}")
            return False

    async def get_cost_data(
        self,
        start_date: date,
        end_date: date,
        granularity: Granularity = Granularity.DAILY,
    ) -> list[CostRecord]:
        """Query Azure Cost Management for aggregated daily cost by service and resource."""
        self._ensure_authenticated()
        assert self._cost_client is not None

        scope = f"/subscriptions/{self.subscription_id}"
        query_def = QueryDefinition(
            type=ExportType.ACTUAL_COST,
            timeframe=TimeframeType.CUSTOM,
            time_period=QueryTimePeriod(
                from_property=datetime.combine(start_date, datetime.min.time()),
                to=datetime.combine(end_date, datetime.max.time()),
            ),
            dataset=QueryDataset(
                granularity=granularity.value.capitalize(),
                aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
                grouping=[
                    QueryGrouping(type="Dimension", name="ServiceName"),
                    QueryGrouping(type="Dimension", name="ResourceLocation"),
                    QueryGrouping(type="Dimension", name="ResourceId"),
                ],
            ),
        )

        records: list[CostRecord] = []
        try:
            result = self._cost_client.query.usage(scope=scope, parameters=query_def)
            if result.rows:
                for row in result.rows:
                    cost_val = float(row[0]) if row[0] is not None else 0.0
                    date_val = self._parse_azure_date(row[1])
                    service_name = str(row[2]) if len(row) > 2 and row[2] else "General"
                    region = str(row[3]) if len(row) > 3 and row[3] else "global"
                    res_id = str(row[4]) if len(row) > 4 and row[4] else None
                    currency = str(row[5]) if len(row) > 5 and row[5] else "USD"

                    records.append(
                        CostRecord(
                            resource_id=res_id,
                            resource_name=res_id.split("/")[-1] if res_id else None,
                            service=service_name,
                            date=date_val,
                            amount=round(cost_val, 2),
                            currency=currency,
                            provider=CloudProviderType.AZURE,
                            region=region,
                        )
                    )
            return records
        except HttpResponseError as e:
            if e.status_code == 429:
                raise RateLimitError(
                    "Azure Cost Management rate limit exceeded", provider="azure"
                ) from e
            raise ProviderError(f"Azure Cost Management query failed: {e}", provider="azure") from e
        except Exception as e:
            raise ProviderError(f"Failed to fetch Azure cost records: {e}", provider="azure") from e

    def _parse_azure_date(self, val: Any) -> date:
        """Parse integer date (e.g. 20260830) or ISO string from Azure API."""
        if isinstance(val, int):
            s = str(val)
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        if isinstance(val, str):
            if "T" in val:
                return datetime.fromisoformat(val).date()
            if len(val) == 8 and val.isdigit():
                return date(int(val[:4]), int(val[4:6]), int(val[6:8]))
            return date.fromisoformat(val)
        return date.today()

    async def list_resources(
        self,
        resource_types: list[ResourceType | str] | None = None,
    ) -> list[CloudResource]:
        """List Azure Virtual Machines, Managed Disks, and Storage Accounts."""
        self._ensure_authenticated()
        assert self._compute_client is not None
        assert self._storage_client is not None

        resources: list[CloudResource] = []

        try:
            for vm in self._compute_client.virtual_machines.list_all():
                vm_id = vm.id or f"/subscriptions/{self.subscription_id}/vms/{vm.name}"
                resources.append(
                    CloudResource(
                        id=vm_id,
                        name=vm.name or "azure-vm",
                        type=ResourceType.VM,
                        region=vm.location or "global",
                        provider=CloudProviderType.AZURE,
                        tags=vm.tags or {},
                        monthly_cost=0.0,
                        utilization_pct=0.0,
                        status=ResourceStatus.RUNNING,
                        metadata={
                            "vm_size": vm.hardware_profile.vm_size
                            if vm.hardware_profile
                            else "unknown"
                        },
                    )
                )

            for disk in self._compute_client.disks.list():
                is_attached = bool(disk.managed_by)
                disk_id = disk.id or f"/subscriptions/{self.subscription_id}/disks/{disk.name}"
                resources.append(
                    CloudResource(
                        id=disk_id,
                        name=disk.name or "azure-disk",
                        type=ResourceType.STORAGE,
                        region=disk.location or "global",
                        provider=CloudProviderType.AZURE,
                        tags=disk.tags or {},
                        monthly_cost=0.0,
                        utilization_pct=0.0,
                        status=ResourceStatus.RUNNING if is_attached else ResourceStatus.ORPHANED,
                        metadata={"is_attached": is_attached, "disk_size_gb": disk.disk_size_gb},
                    )
                )

            for sa in self._storage_client.storage_accounts.list():
                sa_id = sa.id or f"/subscriptions/{self.subscription_id}/storageAccounts/{sa.name}"
                resources.append(
                    CloudResource(
                        id=sa_id,
                        name=sa.name or "azure-storage",
                        type=ResourceType.STORAGE,
                        region=sa.location or "global",
                        provider=CloudProviderType.AZURE,
                        tags=sa.tags or {},
                        monthly_cost=0.0,
                        utilization_pct=0.0,
                        status=ResourceStatus.RUNNING,
                        metadata={"sku": sa.sku.name if sa.sku else "Standard_LRS"},
                    )
                )
        except HttpResponseError as e:
            raise ProviderError(f"Azure list_resources failed: {e}", provider="azure") from e

        if resource_types:
            type_set = {
                t.value if isinstance(t, ResourceType) else str(t).lower() for t in resource_types
            }
            return [r for r in resources if r.type.value in type_set]

        return resources

    async def get_resource_utilization(
        self,
        resource_id: str,
        period_days: int = 7,
    ) -> float:
        """Query Azure Monitor metrics for average CPU utilization."""
        self._ensure_authenticated()
        assert self._monitor_client is not None

        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=period_days)
            timespan = f"{start_time.isoformat()}/{end_time.isoformat()}"

            metrics_data = self._monitor_client.metrics.list(
                resource_uri=resource_id,
                timespan=timespan,
                interval="P1D",
                metricnames="Percentage CPU",
                aggregation="Average",
            )

            values: list[float] = []
            for item in metrics_data.value:
                for ts in item.timeseries:
                    for d in ts.data:
                        if d.average is not None:
                            values.append(d.average)

            if values:
                return round(sum(values) / len(values), 2)
            return 0.0
        except Exception as e:
            logger.debug(f"Could not retrieve Azure metrics for {resource_id}: {e}")
            return 0.0

    async def get_idle_resources(
        self,
        threshold_pct: float = 5.0,
        period_days: int = 7,
    ) -> list[CloudResource]:
        """Detect Azure VMs running with average CPU < threshold_pct."""
        vms = await self.list_resources([ResourceType.VM])
        idle_vms: list[CloudResource] = []

        for vm in vms:
            util = await self.get_resource_utilization(vm.id, period_days)
            if util < threshold_pct:
                idle_vm = vm.model_copy(
                    update={"utilization_pct": util, "status": ResourceStatus.IDLE}
                )
                idle_vms.append(idle_vm)

        return idle_vms

    async def get_orphaned_storage(
        self,
        unused_days: int = 30,
    ) -> list[CloudResource]:
        """Detect unattached Azure managed disks."""
        storage_res = await self.list_resources([ResourceType.STORAGE])
        return [
            r
            for r in storage_res
            if r.metadata.get("is_attached") is False or r.status == ResourceStatus.ORPHANED
        ]
