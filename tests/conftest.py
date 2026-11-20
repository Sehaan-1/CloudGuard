"""Pytest fixtures and test configuration for CloudGuard test suite."""

from datetime import date, datetime, timedelta

import pytest

from cloudguard.core.config import Settings
from cloudguard.core.models import (
    CloudProviderType,
    CloudResource,
    CostRecord,
    ResourceStatus,
    ResourceType,
)
from cloudguard.providers.mock_provider import MockProvider


@pytest.fixture
def mock_settings() -> Settings:
    """Fixture providing isolated Settings instance for tests."""
    return Settings(
        app_env="testing",
        log_level="DEBUG",
        default_provider="mock",
        zscore_threshold=3.0,
        iqr_multiplier=1.5,
        idle_cpu_threshold_pct=5.0,
        idle_period_days=7,
        orphaned_storage_days=30,
        underutilized_vm_threshold_pct=20.0,
        azure_subscription_id="test-sub-12345",
        aws_access_key_id="test-akid",
        aws_secret_access_key="test-secret",
    )


@pytest.fixture
def mock_provider() -> MockProvider:
    """Fixture providing deterministic MockProvider."""
    return MockProvider(seed=42, resource_count=20, enable_anomalies=True)


@pytest.fixture
def sample_resource() -> CloudResource:
    """Fixture providing a sample cloud VM resource."""
    return CloudResource(
        id="vm-prod-app-01",
        name="production-app-server",
        type=ResourceType.VM,
        region="us-east-1",
        provider=CloudProviderType.AWS,
        tags={"Environment": "production", "Owner": "finops"},
        monthly_cost=450.00,
        utilization_pct=45.2,
        status=ResourceStatus.RUNNING,
        created_at=datetime.utcnow() - timedelta(days=90),
    )


@pytest.fixture
def sample_idle_resource() -> CloudResource:
    """Fixture providing a sample idle cloud VM resource."""
    return CloudResource(
        id="vm-dev-test-02",
        name="dev-sandbox-instance",
        type=ResourceType.VM,
        region="us-west-2",
        provider=CloudProviderType.AZURE,
        tags={"Environment": "dev"},
        monthly_cost=820.00,
        utilization_pct=2.1,
        status=ResourceStatus.IDLE,
        created_at=datetime.utcnow() - timedelta(days=45),
    )


@pytest.fixture
def sample_orphaned_resource() -> CloudResource:
    """Fixture providing a sample unattached/orphaned disk resource."""
    return CloudResource(
        id="disk-unattached-vol-99",
        name="unused-data-disk",
        type=ResourceType.STORAGE,
        region="eu-west-1",
        provider=CloudProviderType.MOCK,
        tags={},
        monthly_cost=150.00,
        utilization_pct=0.0,
        status=ResourceStatus.ORPHANED,
        metadata={"is_attached": False},
    )


@pytest.fixture
def sample_cost_records() -> list[CostRecord]:
    """Fixture providing a 7-day series of cost records across services."""
    records = []
    base_date = date(2026, 8, 1)
    services = ["Virtual Machines", "Object Storage", "Relational Database"]

    for day in range(7):
        cur_date = base_date + timedelta(days=day)
        for svc in services:
            cost = 100.0 + (day * 10.0) if svc == "Virtual Machines" else 50.0
            records.append(
                CostRecord(
                    service=svc,
                    date=cur_date,
                    amount=cost,
                    currency="USD",
                    provider=CloudProviderType.MOCK,
                    region="us-east-1",
                )
            )
    return records
