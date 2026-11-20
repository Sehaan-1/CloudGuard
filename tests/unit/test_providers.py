"""Unit tests for CloudProvider implementations (Mock, Azure, AWS)."""

from datetime import date, timedelta

import pytest

from cloudguard.core.exceptions import AuthenticationError
from cloudguard.core.models import (
    CloudProviderType,
    Granularity,
    ResourceStatus,
    ResourceType,
    ScanResult,
)
from cloudguard.providers.aws_provider import AWSProvider
from cloudguard.providers.azure_provider import AzureProvider
from cloudguard.providers.mock_provider import MockProvider


class TestMockProvider:
    @pytest.mark.asyncio
    async def test_mock_provider_properties(self, mock_provider: MockProvider):
        assert mock_provider.provider_type == CloudProviderType.MOCK
        assert "Mock Enterprise Cloud" in mock_provider.provider_name()
        assert await mock_provider.test_connection() is True

    @pytest.mark.asyncio
    async def test_mock_list_resources(self, mock_provider: MockProvider):
        resources = await mock_provider.list_resources()
        assert len(resources) >= 20

        vm_resources = await mock_provider.list_resources([ResourceType.VM])
        assert len(vm_resources) > 0
        assert all(r.type == ResourceType.VM for r in vm_resources)

    @pytest.mark.asyncio
    async def test_mock_get_idle_and_orphaned_resources(self, mock_provider: MockProvider):
        idle = await mock_provider.get_idle_resources(threshold_pct=5.0)
        assert len(idle) > 0
        for r in idle:
            assert r.utilization_pct < 5.0

        orphans = await mock_provider.get_orphaned_storage()
        assert len(orphans) > 0
        for r in orphans:
            assert r.type == ResourceType.STORAGE
            assert r.status == ResourceStatus.ORPHANED or r.metadata.get("is_attached") is False

    @pytest.mark.asyncio
    async def test_mock_get_cost_data(self, mock_provider: MockProvider):
        start = date(2026, 8, 1)
        end = date(2026, 8, 10)
        records = await mock_provider.get_cost_data(start, end, Granularity.DAILY)

        assert len(records) > 0
        assert len(records) == 70
        assert all(r.amount > 0 for r in records)
        assert all(r.provider == CloudProviderType.MOCK for r in records)

    @pytest.mark.asyncio
    async def test_mock_scan(self, mock_provider: MockProvider):
        scan_res = await mock_provider.scan(
            idle_threshold_pct=5.0,
            orphaned_days=30,
            underutilized_threshold_pct=20.0,
        )

        assert isinstance(scan_res, ScanResult)
        assert scan_res.idle_count > 0
        assert scan_res.orphaned_count > 0
        assert scan_res.total_waste_monthly > 0.0
        assert scan_res.total_resources_scanned > 0

    def test_benchmark_generation(self, mock_provider: MockProvider):
        records = mock_provider.generate_benchmark_records(1000)
        assert len(records) == 1000
        assert records[0].id == "bench-0000000"


class TestAzureProvider:
    def test_azure_provider_properties(self):
        provider = AzureProvider(subscription_id="sub-123")
        assert provider.provider_type == CloudProviderType.AZURE
        assert provider.provider_name() == "Microsoft Azure"

    @pytest.mark.asyncio
    async def test_azure_missing_subscription_raises_auth_error(self):
        provider = AzureProvider(subscription_id=None)
        with pytest.raises(AuthenticationError):
            await provider.get_cost_data(date.today() - timedelta(days=7), date.today())


class TestAWSProvider:
    def test_aws_provider_properties(self):
        provider = AWSProvider(aws_access_key_id="test-key", aws_secret_access_key="test-secret")
        assert provider.provider_type == CloudProviderType.AWS
        assert provider.provider_name() == "Amazon Web Services"


def test_azure_provider_implements_interface():
    from cloudguard.providers.base import CloudProvider

    provider = AzureProvider(subscription_id="sub-test-12345")
    assert isinstance(provider, CloudProvider)
    assert provider.provider_type == CloudProviderType.AZURE
    assert hasattr(provider, "test_connection")
    assert hasattr(provider, "get_cost_data")
    assert hasattr(provider, "list_resources")
    assert hasattr(provider, "get_resource_utilization")
    assert hasattr(provider, "get_idle_resources")
    assert hasattr(provider, "get_orphaned_storage")
    assert hasattr(provider, "scan")


@pytest.mark.asyncio
async def test_aws_provider_handles_pagination():
    from unittest.mock import MagicMock

    provider = AWSProvider(
        aws_access_key_id="test-key",
        aws_secret_access_key="test-secret",
        region_name="us-east-1",
    )
    provider._session = MagicMock()
    mock_ce = MagicMock()
    mock_ce.get_cost_and_usage.side_effect = [
        {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2026-08-01", "End": "2026-08-02"},
                    "Groups": [
                        {
                            "Keys": ["Amazon EC2", "us-east-1"],
                            "Metrics": {"UnblendedCost": {"Amount": "100.00", "Unit": "USD"}},
                        }
                    ],
                }
            ],
            "NextPageToken": "token-page-2",
        },
        {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2026-08-01", "End": "2026-08-02"},
                    "Groups": [
                        {
                            "Keys": ["Amazon S3", "us-east-1"],
                            "Metrics": {"UnblendedCost": {"Amount": "50.00", "Unit": "USD"}},
                        }
                    ],
                }
            ],
            "NextPageToken": None,
        },
    ]
    provider._ce_client = mock_ce
    records = await provider.get_cost_data(date(2026, 8, 1), date(2026, 8, 2), Granularity.DAILY)
    assert len(records) == 2
    assert records[0].service == "Amazon EC2"
    assert records[1].service == "Amazon S3"
    assert mock_ce.get_cost_and_usage.call_count == 2


def test_mock_provider_generates_deterministic_data():
    p1 = MockProvider(seed=42, resource_count=20)
    p2 = MockProvider(seed=42, resource_count=20)
    r1 = p1.generate_benchmark_records(50)
    r2 = p2.generate_benchmark_records(50)
    assert len(r1) == len(r2) == 50
    assert [r.amount for r in r1] == [r.amount for r in r2]
    assert [r.service for r in r1] == [r.service for r in r2]


def test_provider_factory_creates_correct_type():
    from cloudguard.providers.factory import ProviderFactory

    mock_p = ProviderFactory.create("mock")
    assert isinstance(mock_p, MockProvider)
    assert mock_p.provider_type == CloudProviderType.MOCK

    azure_p = ProviderFactory.create("azure", subscription_id="sub-123")
    assert isinstance(azure_p, AzureProvider)
    assert azure_p.provider_type == CloudProviderType.AZURE

    aws_p = ProviderFactory.create("aws", aws_access_key_id="k", aws_secret_access_key="s")
    assert isinstance(aws_p, AWSProvider)
    assert aws_p.provider_type == CloudProviderType.AWS
