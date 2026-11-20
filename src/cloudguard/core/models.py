"""Domain models and data contracts for CloudGuard.

These Pydantic models represent the core entities used across providers,
anomaly detection, parallel processing, recommendation engine, reporting,
and the web dashboard.
"""

from __future__ import annotations

import datetime as dt
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CloudProviderType(StrEnum):
    """Supported cloud provider types."""

    AZURE = "azure"
    AWS = "aws"
    MOCK = "mock"
    GCP = "gcp"


class ResourceType(StrEnum):
    """Categorized cloud resource types."""

    VM = "vm"
    STORAGE = "storage"
    DATABASE = "database"
    NETWORK = "network"
    CONTAINER = "container"
    SERVERLESS = "serverless"
    OTHER = "other"


class ResourceStatus(StrEnum):
    """Operational status of a cloud resource."""

    RUNNING = "running"
    STOPPED = "stopped"
    IDLE = "idle"
    ORPHANED = "orphaned"
    UNDERUTILIZED = "underutilized"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    """Severity levels for anomalies, alerts, and waste."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Granularity(StrEnum):
    """Granularity for cost queries."""

    DAILY = "daily"
    MONTHLY = "monthly"
    HOURLY = "hourly"


class RecommendationPriority(StrEnum):
    """Priority for optimization recommendations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class RecommendationStatus(StrEnum):
    """Lifecycle status for a recommendation."""

    OPEN = "open"
    APPLIED = "applied"
    DISMISSED = "dismissed"


class CloudResource(BaseModel):
    """Unified representation of a cloud resource across providers."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str = Field(..., description="Unique provider resource ID or ARN/URI")
    name: str = Field(..., description="Human-readable resource name")
    type: ResourceType = Field(default=ResourceType.OTHER, description="Normalized resource type")
    region: str = Field(default="global", description="Deployment region")
    provider: CloudProviderType = Field(..., description="Cloud provider")
    tags: dict[str, str] = Field(default_factory=dict, description="Resource tags/labels")
    monthly_cost: float = Field(default=0.0, ge=0.0, description="Estimated monthly cost in USD")
    utilization_pct: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Average utilization percentage (0-100%)"
    )
    status: ResourceStatus = Field(
        default=ResourceStatus.RUNNING, description="Current operational status"
    )
    created_at: dt.datetime | None = Field(default=None, description="Resource creation timestamp")
    last_scanned: dt.datetime = Field(
        default_factory=dt.datetime.utcnow, description="Timestamp of last inspection"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Provider-specific attributes"
    )

    @field_validator("type", mode="before")
    @classmethod
    def parse_resource_type(cls, v: Any) -> ResourceType:
        if isinstance(v, ResourceType):
            return v
        if isinstance(v, str):
            v_lower = v.lower()
            for item in ResourceType:
                if item.value == v_lower:
                    return item
            if (
                "network" in v_lower
                or "vpc" in v_lower
                or "subnet" in v_lower
                or "loadbalancer" in v_lower
            ):
                return ResourceType.NETWORK
            if (
                "disk" in v_lower
                or "blob" in v_lower
                or "s3" in v_lower
                or "storage" in v_lower
                or "ebs" in v_lower
            ):
                return ResourceType.STORAGE
            if (
                "sql" in v_lower
                or "rds" in v_lower
                or "db" in v_lower
                or "database" in v_lower
                or "postgres" in v_lower
            ):
                return ResourceType.DATABASE
            if "container" in v_lower or "aks" in v_lower or "eks" in v_lower or "k8s" in v_lower:
                return ResourceType.CONTAINER
            if "lambda" in v_lower or "function" in v_lower or "serverless" in v_lower:
                return ResourceType.SERVERLESS
            if (
                "virtualmachine" in v_lower
                or "ec2" in v_lower
                or "compute" in v_lower
                or "vm" in v_lower
            ):
                return ResourceType.VM
        return ResourceType.OTHER

    @field_validator("provider", mode="before")
    @classmethod
    def parse_provider_type(cls, v: Any) -> CloudProviderType:
        if isinstance(v, CloudProviderType):
            return v
        if isinstance(v, str):
            v_lower = v.lower()
            for item in CloudProviderType:
                if item.value == v_lower:
                    return item
        return CloudProviderType.MOCK

    @property
    def is_idle(self) -> bool:
        """Returns True if resource utilization is under 5% or marked idle."""
        return self.status == ResourceStatus.IDLE or self.utilization_pct < 5.0

    @property
    def is_orphaned(self) -> bool:
        """Returns True if marked as orphaned storage or unattached disk."""
        return self.status == ResourceStatus.ORPHANED or self.metadata.get("is_attached") is False

    @property
    def is_untagged(self) -> bool:
        """Returns True if no tags or owner tags are missing."""
        return len(self.tags) == 0


class CostRecord(BaseModel):
    """Normalized line item of cost consumption."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    resource_id: str | None = Field(default=None, description="Associated resource ID if known")
    resource_name: str | None = Field(default=None, description="Associated resource name")
    service: str = Field(..., description="Service name e.g. Virtual Machines, S3, RDS")
    date: dt.date = Field(..., description="Date of the incurred cost")
    amount: float = Field(..., ge=0.0, description="Cost amount")
    currency: str = Field(default="USD", description="ISO currency code")
    provider: CloudProviderType = Field(..., description="Cloud provider")
    region: str = Field(default="global", description="Region of the service")
    usage_type: str | None = Field(default=None, description="Granular usage meter/type")
    tags: dict[str, str] = Field(default_factory=dict, description="Tags associated with line item")

    @field_validator("provider", mode="before")
    @classmethod
    def parse_provider_type(cls, v: Any) -> CloudProviderType:
        if isinstance(v, CloudProviderType):
            return v
        if isinstance(v, str):
            v_lower = v.lower()
            for item in CloudProviderType:
                if item.value == v_lower:
                    return item
        return CloudProviderType.MOCK


class CostSummary(BaseModel):
    """Aggregated financial summary across dates, services, and regions."""

    model_config = ConfigDict(extra="ignore")

    total_cost: float = Field(default=0.0, ge=0.0, description="Total cost in USD")
    currency: str = Field(default="USD", description="Currency code")
    period_start: dt.date = Field(..., description="Start of calculation period")
    period_end: dt.date = Field(..., description="End of calculation period")
    record_count: int = Field(default=0, ge=0, description="Number of underlying records")
    cost_by_service: dict[str, float] = Field(
        default_factory=dict, description="Sum of cost grouped by service"
    )
    cost_by_region: dict[str, float] = Field(
        default_factory=dict, description="Sum of cost grouped by region"
    )
    cost_by_provider: dict[str, float] = Field(
        default_factory=dict, description="Sum of cost grouped by provider"
    )
    daily_totals: dict[str, float] = Field(
        default_factory=dict, description="Date string to total cost map"
    )
    average_daily_cost: float = Field(default=0.0, ge=0.0)
    top_services: list[tuple[str, float]] = Field(
        default_factory=list, description="Top spending services sorted descending"
    )

    @classmethod
    def from_records(
        cls, records: list[CostRecord], start_date: dt.date, end_date: dt.date
    ) -> CostSummary:
        """Construct a CostSummary from a list of CostRecord objects."""
        total = sum(r.amount for r in records)
        by_service: dict[str, float] = {}
        by_region: dict[str, float] = {}
        by_provider: dict[str, float] = {}
        by_date: dict[str, float] = {}

        for r in records:
            by_service[r.service] = round(by_service.get(r.service, 0.0) + r.amount, 2)
            by_region[r.region] = round(by_region.get(r.region, 0.0) + r.amount, 2)
            p_name = (
                r.provider.value if isinstance(r.provider, CloudProviderType) else str(r.provider)
            )
            by_provider[p_name] = round(by_provider.get(p_name, 0.0) + r.amount, 2)
            d_str = r.date.isoformat()
            by_date[d_str] = round(by_date.get(d_str, 0.0) + r.amount, 2)

        day_count = max(1, (end_date - start_date).days + 1)
        avg_daily = round(total / day_count, 2) if day_count > 0 else 0.0

        top_svc = sorted(by_service.items(), key=lambda x: x[1], reverse=True)[:10]

        return cls(
            total_cost=round(total, 2),
            currency="USD",
            period_start=start_date,
            period_end=end_date,
            record_count=len(records),
            cost_by_service=by_service,
            cost_by_region=by_region,
            cost_by_provider=by_provider,
            daily_totals=by_date,
            average_daily_cost=avg_daily,
            top_services=top_svc,
        )


class AnomalyResult(BaseModel):
    """Statistical anomaly detected in spending."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    resource_id: str | None = Field(default=None, description="Resource ID if applicable")
    service: str = Field(..., description="Service where anomaly occurred")
    date: dt.date = Field(..., description="Date of anomaly occurrence")
    expected_cost: float = Field(default=0.0, ge=0.0, description="Expected baseline cost")
    actual_cost: float = Field(default=0.0, ge=0.0, description="Actual observed cost")
    deviation_score: float = Field(
        default=0.0, description="Standard deviations (Z-Score) or IQR multiplier"
    )
    severity: Severity = Field(default=Severity.MEDIUM, description="Severity assessment")
    method: str = Field(default="composite", description="Detection algorithm used")
    description: str = Field(default="", description="Human-readable explanation")
    is_anomaly: bool = Field(default=True, description="Flag indicating anomaly status")
    resolved: bool = Field(default=False, description="Flag for user resolution")
    detected_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Recommendation(BaseModel):
    """Actionable FinOps optimization recommendation."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    resource_id: str = Field(..., description="Target resource ID")
    resource_name: str | None = Field(default=None, description="Target resource name")
    action: str = Field(..., description="Action tag: terminate_idle, rightsize, delete_orphan")
    title: str = Field(..., description="Clear action title")
    description: str = Field(..., description="Detailed rationale and impact")
    estimated_savings: float = Field(
        ..., ge=0.0, description="Estimated monthly cost reduction in USD"
    )
    currency: str = Field(default="USD", description="Currency code")
    confidence: float = Field(
        default=0.9, ge=0.0, le=1.0, description="Confidence score of recommendation"
    )
    priority: RecommendationPriority = Field(
        default=RecommendationPriority.MEDIUM, description="Recommended priority"
    )
    resource_type: ResourceType = Field(
        default=ResourceType.OTHER, description="Type of target resource"
    )
    provider: CloudProviderType = Field(
        default=CloudProviderType.MOCK, description="Cloud provider"
    )
    status: RecommendationStatus = Field(
        default=RecommendationStatus.OPEN, description="Current status"
    )
    created_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)


class ScanResult(BaseModel):
    """Summary of infrastructure audit for waste and governance gaps."""

    model_config = ConfigDict(extra="ignore")

    provider: CloudProviderType = Field(default=CloudProviderType.MOCK)
    scanned_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    idle_resources: list[CloudResource] = Field(default_factory=list)
    orphaned_storage: list[CloudResource] = Field(default_factory=list)
    underutilized_vms: list[CloudResource] = Field(default_factory=list)
    untagged_resources: list[CloudResource] = Field(default_factory=list)
    total_resources_scanned: int = Field(default=0, ge=0)
    total_waste_monthly: float = Field(default=0.0, ge=0.0)
    currency: str = Field(default="USD")

    @property
    def idle_count(self) -> int:
        return len(self.idle_resources)

    @property
    def orphaned_count(self) -> int:
        return len(self.orphaned_storage)

    @property
    def underutilized_count(self) -> int:
        return len(self.underutilized_vms)

    @property
    def untagged_count(self) -> int:
        return len(self.untagged_resources)


class ReportData(BaseModel):
    """Aggregate payload containing all data required for PDF and Executive Dashboards."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = Field(default="CloudGuard FinOps Executive Report")
    generated_at: dt.datetime = Field(default_factory=dt.datetime.utcnow)
    provider: CloudProviderType = Field(default=CloudProviderType.MOCK)
    summary: CostSummary
    scan_result: ScanResult
    anomalies: list[AnomalyResult] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
