"""Custom exception hierarchy for CloudGuard."""

from typing import Any


class CloudGuardError(Exception):
    """Base exception for all CloudGuard errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class ConfigurationError(CloudGuardError):
    """Raised when application configuration or environment variables are invalid."""

    pass


class ProviderError(CloudGuardError):
    """Base exception for cloud provider errors."""

    def __init__(
        self,
        message: str,
        provider: str = "unknown",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.provider = provider

    def __str__(self) -> str:
        return f"[{self.provider.upper()}] {super().__str__()}"


class AuthenticationError(ProviderError):
    """Raised when cloud credentials fail or are absent."""

    pass


class ProviderConnectionError(ProviderError):
    """Raised when unable to reach cloud provider API endpoints."""

    pass


class RateLimitError(ProviderError):
    """Raised when cloud API rate limit / throttling is encountered."""

    def __init__(
        self,
        message: str,
        provider: str = "unknown",
        retry_after_seconds: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, provider, details)
        self.retry_after_seconds = retry_after_seconds


class ResourceNotFoundError(ProviderError):
    """Raised when a specific cloud resource ID is not found."""

    def __init__(
        self,
        resource_id: str,
        provider: str = "unknown",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"Resource not found: {resource_id}", provider, details)
        self.resource_id = resource_id


class AnalysisEngineError(CloudGuardError):
    """Raised when the analysis engine encounters a processing failure."""

    pass


class AnomalyDetectionError(CloudGuardError):
    """Raised when statistical anomaly algorithms fail or encounter invalid input."""

    pass


class ParallelProcessingError(CloudGuardError):
    """Raised when parallel executor workers fail."""

    pass


class RecommendationError(CloudGuardError):
    """Raised when recommendation rules fail to evaluate."""

    pass


class ReportGenerationError(CloudGuardError):
    """Raised when PDF or export report generation fails."""

    pass


class DatabaseError(CloudGuardError):
    """Raised when persistence operations fail."""

    pass
