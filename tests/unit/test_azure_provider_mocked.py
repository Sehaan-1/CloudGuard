"""Unit tests for AzureProvider with mocked SDK clients."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from cloudguard.core.models import Granularity, ResourceStatus, ResourceType
from cloudguard.providers.azure_provider import AzureProvider


@pytest.fixture
def mocked_azure_provider():
    provider = AzureProvider(
        subscription_id="sub-test-12345",
        tenant_id="tenant-test-12345",
        client_id="client-test-12345",
        client_secret="secret-test-12345",
    )
    provider._credential = MagicMock()
    provider._cost_client = MagicMock()
    provider._compute_client = MagicMock()
    provider._storage_client = MagicMock()
    provider._monitor_client = MagicMock()
    return provider


class TestAzureProviderMocked:
    @pytest.mark.asyncio
    async def test_azure_test_connection_success(self, mocked_azure_provider):
        vm_mock = MagicMock()
        vm_mock.name = "test-vm-1"
        mocked_azure_provider._compute_client.virtual_machines.list_all.return_value = [vm_mock]

        connected = await mocked_azure_provider.test_connection()
        assert connected is True

    @pytest.mark.asyncio
    async def test_azure_get_cost_data(self, mocked_azure_provider):
        query_result_mock = MagicMock()
        query_result_mock.rows = [
            [125.50, 20260820, "Virtual Machines", "eastus", "/sub/123/vm1", "USD"],
            [45.00, "2026-08-20T00:00:00", "Storage", "eastus", "/sub/123/sa1", "USD"],
            [88.00, "2026-08-20", "SQL Database", "westeurope", "/sub/123/sql1", "EUR"],
        ]
        mocked_azure_provider._cost_client.query.usage.return_value = query_result_mock

        start = date(2026, 8, 1)
        end = date(2026, 8, 20)
        records = await mocked_azure_provider.get_cost_data(start, end, Granularity.DAILY)

        assert len(records) == 3
        assert records[0].service == "Virtual Machines"
        assert records[0].amount == 125.50
        assert records[0].currency == "USD"
        assert records[0].date == date(2026, 8, 20)
        assert records[1].service == "Storage"
        assert records[2].currency == "EUR"

    @pytest.mark.asyncio
    async def test_azure_list_resources(self, mocked_azure_provider):
        vm_mock = MagicMock()
        vm_mock.id = "/subscriptions/123/vms/vm-1"
        vm_mock.name = "vm-1"
        vm_mock.location = "eastus"
        vm_mock.tags = {"env": "prod"}
        vm_mock.hardware_profile.vm_size = "Standard_D4s_v5"
        mocked_azure_provider._compute_client.virtual_machines.list_all.return_value = [vm_mock]

        disk_attached = MagicMock()
        disk_attached.id = "/subscriptions/123/disks/disk-att"
        disk_attached.name = "disk-att"
        disk_attached.location = "eastus"
        disk_attached.tags = {}
        disk_attached.managed_by = "/subscriptions/123/vms/vm-1"
        disk_attached.disk_size_gb = 128

        disk_orphan = MagicMock()
        disk_orphan.id = "/subscriptions/123/disks/disk-orphan"
        disk_orphan.name = "disk-orphan"
        disk_orphan.location = "eastus"
        disk_orphan.tags = {}
        disk_orphan.managed_by = None
        disk_orphan.disk_size_gb = 512

        mocked_azure_provider._compute_client.disks.list.return_value = [disk_attached, disk_orphan]

        sa_mock = MagicMock()
        sa_mock.id = "/subscriptions/123/sa/sa1"
        sa_mock.name = "sa1"
        sa_mock.location = "eastus"
        sa_mock.tags = {}
        sa_mock.sku.name = "Standard_GRS"
        mocked_azure_provider._storage_client.storage_accounts.list.return_value = [sa_mock]

        resources = await mocked_azure_provider.list_resources()
        assert len(resources) == 4

        vm_res = [r for r in resources if r.type == ResourceType.VM]
        assert len(vm_res) == 1
        assert vm_res[0].name == "vm-1"

        orphaned = await mocked_azure_provider.get_orphaned_storage()
        assert len(orphaned) == 1
        assert orphaned[0].name == "disk-orphan"
        assert orphaned[0].status == ResourceStatus.ORPHANED

    @pytest.mark.asyncio
    async def test_azure_get_resource_utilization(self, mocked_azure_provider):
        metric_data = MagicMock()
        ts_mock = MagicMock()
        point1 = MagicMock()
        point1.average = 3.2
        point2 = MagicMock()
        point2.average = 4.8
        ts_mock.data = [point1, point2]
        item_mock = MagicMock()
        item_mock.timeseries = [ts_mock]
        metric_data.value = [item_mock]

        mocked_azure_provider._monitor_client.metrics.list.return_value = metric_data

        util = await mocked_azure_provider.get_resource_utilization(
            "/subscriptions/123/vms/vm-1", 7
        )
        assert util == 4.0

    @pytest.mark.asyncio
    async def test_azure_get_idle_resources(self, mocked_azure_provider):
        vm_mock = MagicMock()
        vm_mock.id = "/subscriptions/123/vms/idle-vm"
        vm_mock.name = "idle-vm"
        vm_mock.location = "eastus"
        vm_mock.tags = {}
        vm_mock.hardware_profile.vm_size = "Standard_B2s"
        mocked_azure_provider._compute_client.virtual_machines.list_all.return_value = [vm_mock]
        mocked_azure_provider._compute_client.disks.list.return_value = []
        mocked_azure_provider._storage_client.storage_accounts.list.return_value = []

        metric_data = MagicMock()
        ts_mock = MagicMock()
        point = MagicMock()
        point.average = 2.5
        ts_mock.data = [point]
        item_mock = MagicMock()
        item_mock.timeseries = [ts_mock]
        metric_data.value = [item_mock]
        mocked_azure_provider._monitor_client.metrics.list.return_value = metric_data

        idle_vms = await mocked_azure_provider.get_idle_resources(threshold_pct=5.0)
        assert len(idle_vms) == 1
        assert idle_vms[0].name == "idle-vm"
        assert idle_vms[0].status == ResourceStatus.IDLE
