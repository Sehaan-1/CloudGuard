"""Unit tests for exception hierarchy in cloudguard.core.exceptions."""

from cloudguard.core.exceptions import (
    CloudGuardError,
    ProviderError,
    RateLimitError,
    ResourceNotFoundError,
)


class TestExceptions:
    def test_base_error_with_details(self):
        err = CloudGuardError("System error", details={"code": 500})
        assert "System error" in str(err)
        assert err.details["code"] == 500

    def test_provider_error_formatting(self):
        err = ProviderError("Failed to query API", provider="azure")
        assert "[AZURE]" in str(err)
        assert err.provider == "azure"

    def test_rate_limit_error(self):
        err = RateLimitError("Throttled", provider="aws", retry_after_seconds=30.0)
        assert err.retry_after_seconds == 30.0
        assert "[AWS]" in str(err)

    def test_resource_not_found_error(self):
        err = ResourceNotFoundError(resource_id="vm-missing-123", provider="azure")
        assert err.resource_id == "vm-missing-123"
        assert "Resource not found: vm-missing-123" in str(err)
