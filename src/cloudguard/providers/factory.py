"""Factory Pattern for dynamic Cloud Provider registration and instantiation."""

from __future__ import annotations

from typing import Any, ClassVar

from cloudguard.core.config import get_settings
from cloudguard.core.exceptions import ConfigurationError
from cloudguard.core.logging import get_logger
from cloudguard.providers.aws_provider import AWSProvider
from cloudguard.providers.azure_provider import AzureProvider
from cloudguard.providers.base import CloudProvider
from cloudguard.providers.mock_provider import MockProvider

logger = get_logger("providers.factory")


class ProviderFactory:
    """Factory for creating and managing CloudProvider instances."""

    _registry: ClassVar[dict[str, type[CloudProvider]]] = {
        "azure": AzureProvider,
        "aws": AWSProvider,
        "mock": MockProvider,
    }

    @classmethod
    def register(cls, name: str, provider_cls: type[CloudProvider]) -> None:
        """Register a new cloud provider class."""
        key = name.strip().lower()
        if not issubclass(provider_cls, CloudProvider):
            raise TypeError(f"Provider class {provider_cls} must subclass CloudProvider.")
        cls._registry[key] = provider_cls
        logger.debug(f"Registered provider '{key}' -> {provider_cls.__name__}")

    @classmethod
    def list_available_providers(cls) -> list[str]:
        """Return list of all registered provider names."""
        return sorted(cls._registry.keys())

    @classmethod
    def is_supported(cls, name: str) -> bool:
        """Check if provider name is supported."""
        return name.strip().lower() in cls._registry

    @classmethod
    def create(cls, name: str | None = None, **kwargs: Any) -> CloudProvider:
        """Instantiate a CloudProvider by name or fallback to application default."""
        target_name = (name or get_settings().default_provider).strip().lower()

        provider_cls = cls._registry.get(target_name)
        if not provider_cls:
            available = ", ".join(cls.list_available_providers())
            raise ConfigurationError(
                f"Unknown cloud provider '{target_name}'. Available providers: [{available}]"
            )

        logger.info(f"Instantiating provider '{target_name}' via ProviderFactory")
        return provider_cls(**kwargs)
