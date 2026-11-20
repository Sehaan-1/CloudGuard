"""Unit tests for ProviderFactory in cloudguard.providers.factory."""

import pytest

from cloudguard.core.exceptions import ConfigurationError
from cloudguard.core.models import CloudProviderType
from cloudguard.providers.aws_provider import AWSProvider
from cloudguard.providers.azure_provider import AzureProvider
from cloudguard.providers.base import CloudProvider
from cloudguard.providers.factory import ProviderFactory
from cloudguard.providers.mock_provider import MockProvider


class CustomProvider(CloudProvider):
    @property
    def provider_type(self) -> CloudProviderType:
        return CloudProviderType.GCP

    def provider_name(self) -> str:
        return "Google Cloud Platform"

    async def test_connection(self) -> bool:
        return True

    async def get_cost_data(self, start_date, end_date, granularity):
        return []

    async def list_resources(self, resource_types=None):
        return []

    async def get_resource_utilization(self, resource_id, period_days=7):
        return 0.0

    async def get_idle_resources(self, threshold_pct=5.0, period_days=7):
        return []

    async def get_orphaned_storage(self, unused_days=30):
        return []


class TestProviderFactory:
    def test_list_available_providers(self):
        providers = ProviderFactory.list_available_providers()
        assert "azure" in providers
        assert "aws" in providers
        assert "mock" in providers

    def test_create_registered_providers(self):
        mock_p = ProviderFactory.create("mock")
        assert isinstance(mock_p, MockProvider)

        azure_p = ProviderFactory.create("azure", subscription_id="sub-123")
        assert isinstance(azure_p, AzureProvider)

        aws_p = ProviderFactory.create("aws")
        assert isinstance(aws_p, AWSProvider)

    def test_create_unknown_provider_raises_error(self):
        with pytest.raises(ConfigurationError) as excinfo:
            ProviderFactory.create("unknown-cloud")
        assert "Unknown cloud provider 'unknown-cloud'" in str(excinfo.value)

    def test_register_custom_provider(self):
        ProviderFactory.register("gcp", CustomProvider)
        assert ProviderFactory.is_supported("gcp") is True
        gcp_p = ProviderFactory.create("gcp")
        assert isinstance(gcp_p, CustomProvider)

    def test_register_invalid_class_raises_type_error(self):
        class NotAProvider:
            pass

        with pytest.raises(TypeError):
            ProviderFactory.register("invalid", NotAProvider)
