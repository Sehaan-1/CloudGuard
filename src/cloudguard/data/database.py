from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from cloudguard.core.config import get_settings
from cloudguard.core.models import (
    AnomalyResult,
    CloudProviderType,
    CloudResource,
    CostRecord,
    Recommendation,
    RecommendationPriority,
    RecommendationStatus,
    ReportData,
    ResourceStatus,
    ResourceType,
    ScanResult,
    Severity,
)


class Base(DeclarativeBase):
    pass


class CostRecordDB(Base):
    __tablename__ = "cost_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    resource_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    service: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    record_date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    region: Mapped[str] = mapped_column(String(50), default="global", index=True)
    usage_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tags: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    anomalies: Mapped[list[AnomalyDB]] = relationship(
        "AnomalyDB", back_populates="cost_record", cascade="all, delete-orphan"
    )

    def to_model(self) -> CostRecord:
        prov = (
            CloudProviderType(self.provider)
            if self.provider in [p.value for p in CloudProviderType]
            else CloudProviderType.MOCK
        )
        return CostRecord(
            id=self.id or str(uuid.uuid4()),
            resource_id=self.resource_id,
            resource_name=self.resource_name,
            service=self.service,
            date=self.record_date,
            amount=self.amount if self.amount is not None else 0.0,
            currency=self.currency or "USD",
            provider=prov,
            region=self.region or "global",
            usage_type=self.usage_type,
            tags=self.tags or {},
        )

    @classmethod
    def from_model(cls, model: CostRecord) -> CostRecordDB:
        prov = (
            model.provider.value
            if isinstance(model.provider, CloudProviderType)
            else str(model.provider)
        )
        return cls(
            id=model.id,
            resource_id=model.resource_id,
            resource_name=model.resource_name,
            service=model.service,
            provider=prov,
            record_date=model.date,
            amount=model.amount,
            currency=model.currency,
            region=model.region,
            usage_type=model.usage_type,
            tags=model.tags or {},
        )


class ResourceDB(Base):
    __tablename__ = "resources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cloud_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(50), default="global")
    monthly_cost: Mapped[float] = mapped_column(Float, default=0.0)
    utilization_pct: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(50), default="running")
    tags: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    last_scanned: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    def to_model(self) -> CloudResource:
        res_type = (
            ResourceType(self.type)
            if self.type in [t.value for t in ResourceType]
            else ResourceType.OTHER
        )
        prov = (
            CloudProviderType(self.provider)
            if self.provider in [p.value for p in CloudProviderType]
            else CloudProviderType.MOCK
        )
        stat = (
            ResourceStatus(self.status)
            if self.status in [s.value for s in ResourceStatus]
            else ResourceStatus.RUNNING
        )
        return CloudResource(
            id=self.cloud_id,
            name=self.name,
            type=res_type,
            provider=prov,
            region=self.region or "global",
            monthly_cost=self.monthly_cost if self.monthly_cost is not None else 0.0,
            utilization_pct=self.utilization_pct if self.utilization_pct is not None else 0.0,
            status=stat,
            tags=self.tags or {},
            created_at=self.created_at,
            last_scanned=self.last_scanned or dt.datetime.utcnow(),
            metadata=self.metadata_json or {},
        )

    @classmethod
    def from_model(cls, model: CloudResource) -> ResourceDB:
        res_type = model.type.value if isinstance(model.type, ResourceType) else str(model.type)
        prov = (
            model.provider.value
            if isinstance(model.provider, CloudProviderType)
            else str(model.provider)
        )
        stat = model.status.value if isinstance(model.status, ResourceStatus) else str(model.status)
        return cls(
            cloud_id=model.id,
            name=model.name,
            type=res_type,
            provider=prov,
            region=model.region,
            monthly_cost=model.monthly_cost,
            utilization_pct=model.utilization_pct,
            status=stat,
            tags=model.tags or {},
            created_at=model.created_at,
            last_scanned=model.last_scanned,
            metadata_json=model.metadata or {},
        )


class AnomalyDB(Base):
    __tablename__ = "anomalies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    cost_record_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cost_records.id", ondelete="CASCADE"), nullable=True, index=True
    )
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    service: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    expected_cost: Mapped[float] = mapped_column(Float, default=0.0)
    actual_cost: Mapped[float] = mapped_column(Float, default=0.0)
    deviation_score: Mapped[float] = mapped_column(Float, default=0.0)
    severity: Mapped[str] = mapped_column(String(50), default="medium")
    method: Mapped[str] = mapped_column(String(50), default="composite")
    description: Mapped[str] = mapped_column(Text, default="")
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    detected_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    cost_record: Mapped[CostRecordDB | None] = relationship(
        "CostRecordDB", back_populates="anomalies"
    )

    def to_model(self) -> AnomalyResult:
        sev = (
            Severity(self.severity)
            if self.severity in [s.value for s in Severity]
            else Severity.MEDIUM
        )
        return AnomalyResult(
            id=self.id or str(uuid.uuid4()),
            resource_id=self.resource_id,
            service=self.service,
            date=self.date,
            expected_cost=self.expected_cost if self.expected_cost is not None else 0.0,
            actual_cost=self.actual_cost if self.actual_cost is not None else 0.0,
            deviation_score=self.deviation_score if self.deviation_score is not None else 0.0,
            severity=sev,
            method=self.method or "composite",
            description=self.description or "",
            is_anomaly=self.is_anomaly if self.is_anomaly is not None else True,
            resolved=self.resolved if self.resolved is not None else False,
            detected_at=self.detected_at or dt.datetime.utcnow(),
            metadata=self.metadata_json or {},
        )

    @classmethod
    def from_model(cls, model: AnomalyResult, cost_record_id: str | None = None) -> AnomalyDB:
        sev = model.severity.value if isinstance(model.severity, Severity) else str(model.severity)
        return cls(
            id=model.id,
            cost_record_id=cost_record_id,
            resource_id=model.resource_id,
            service=model.service,
            date=model.date,
            expected_cost=model.expected_cost,
            actual_cost=model.actual_cost,
            deviation_score=model.deviation_score,
            severity=sev,
            method=model.method,
            description=model.description,
            is_anomaly=model.is_anomaly,
            resolved=model.resolved,
            detected_at=model.detected_at,
            metadata_json=model.metadata or {},
        )


class RecommendationDB(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    estimated_savings: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    confidence: Mapped[float] = mapped_column(Float, default=0.9)
    priority: Mapped[str] = mapped_column(String(50), default="medium")
    resource_type: Mapped[str] = mapped_column(String(50), default="other")
    provider: Mapped[str] = mapped_column(String(50), default="mock")
    status: Mapped[str] = mapped_column(String(50), default="open", index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    def to_model(self) -> Recommendation:
        prio = (
            RecommendationPriority(self.priority)
            if self.priority in [p.value for p in RecommendationPriority]
            else RecommendationPriority.MEDIUM
        )
        res_type = (
            ResourceType(self.resource_type)
            if self.resource_type in [r.value for r in ResourceType]
            else ResourceType.OTHER
        )
        prov = (
            CloudProviderType(self.provider)
            if self.provider in [p.value for p in CloudProviderType]
            else CloudProviderType.MOCK
        )
        stat = (
            RecommendationStatus(self.status)
            if self.status in [s.value for s in RecommendationStatus]
            else RecommendationStatus.OPEN
        )
        return Recommendation(
            id=self.id or str(uuid.uuid4()),
            resource_id=self.resource_id,
            resource_name=self.resource_name,
            action=self.action,
            title=self.title,
            description=self.description or "",
            estimated_savings=self.estimated_savings if self.estimated_savings is not None else 0.0,
            currency=self.currency or "USD",
            confidence=self.confidence if self.confidence is not None else 0.9,
            priority=prio,
            resource_type=res_type,
            provider=prov,
            status=stat,
            created_at=self.created_at or dt.datetime.utcnow(),
        )

    @classmethod
    def from_model(cls, model: Recommendation) -> RecommendationDB:
        prio = (
            model.priority.value
            if isinstance(model.priority, RecommendationPriority)
            else str(model.priority)
        )
        res_type = (
            model.resource_type.value
            if isinstance(model.resource_type, ResourceType)
            else str(model.resource_type)
        )
        prov = (
            model.provider.value
            if isinstance(model.provider, CloudProviderType)
            else str(model.provider)
        )
        stat = (
            model.status.value
            if isinstance(model.status, RecommendationStatus)
            else str(model.status)
        )
        return cls(
            id=model.id,
            resource_id=model.resource_id,
            resource_name=model.resource_name,
            action=model.action,
            title=model.title,
            description=model.description,
            estimated_savings=model.estimated_savings,
            currency=model.currency,
            confidence=model.confidence,
            priority=prio,
            resource_type=res_type,
            provider=prov,
            status=stat,
            created_at=model.created_at,
        )


class ScanHistoryDB(Base):
    __tablename__ = "scan_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    scanned_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    total_resources_scanned: Mapped[int] = mapped_column(Integer, default=0)
    idle_count: Mapped[int] = mapped_column(Integer, default=0)
    orphaned_count: Mapped[int] = mapped_column(Integer, default=0)
    underutilized_count: Mapped[int] = mapped_column(Integer, default=0)
    untagged_count: Mapped[int] = mapped_column(Integer, default=0)
    total_waste_monthly: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    def to_model(self) -> ScanResult:
        prov = (
            CloudProviderType(self.provider)
            if self.provider in [p.value for p in CloudProviderType]
            else CloudProviderType.MOCK
        )
        raw = self.raw_data or {}
        idle = [CloudResource.model_validate(r) for r in raw.get("idle_resources", [])]
        orphaned = [CloudResource.model_validate(r) for r in raw.get("orphaned_storage", [])]
        underutilized = [CloudResource.model_validate(r) for r in raw.get("underutilized_vms", [])]
        untagged = [CloudResource.model_validate(r) for r in raw.get("untagged_resources", [])]
        return ScanResult(
            provider=prov,
            scanned_at=self.scanned_at or dt.datetime.utcnow(),
            idle_resources=idle,
            orphaned_storage=orphaned,
            underutilized_vms=underutilized,
            untagged_resources=untagged,
            total_resources_scanned=self.total_resources_scanned or 0,
            total_waste_monthly=self.total_waste_monthly or 0.0,
            currency=self.currency or "USD",
        )

    @classmethod
    def from_model(cls, model: ScanResult) -> ScanHistoryDB:
        prov = (
            model.provider.value
            if isinstance(model.provider, CloudProviderType)
            else str(model.provider)
        )
        raw = {
            "idle_resources": [r.model_dump(mode="json") for r in model.idle_resources],
            "orphaned_storage": [r.model_dump(mode="json") for r in model.orphaned_storage],
            "underutilized_vms": [r.model_dump(mode="json") for r in model.underutilized_vms],
            "untagged_resources": [r.model_dump(mode="json") for r in model.untagged_resources],
        }
        return cls(
            provider=prov,
            scanned_at=model.scanned_at,
            total_resources_scanned=model.total_resources_scanned,
            idle_count=model.idle_count,
            orphaned_count=model.orphaned_count,
            underutilized_count=model.underutilized_count,
            untagged_count=model.untagged_count,
            total_waste_monthly=model.total_waste_monthly,
            currency=model.currency,
            raw_data=raw,
        )


class ReportDB(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    generated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    period_start: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    total_savings: Mapped[float] = mapped_column(Float, default=0.0)
    anomaly_count: Mapped[int] = mapped_column(Integer, default=0)
    report_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    def to_model(self) -> ReportData:
        return ReportData.model_validate(self.metadata_json)

    @classmethod
    def from_model(cls, model: ReportData, report_path: str | None = None) -> ReportDB:
        prov = (
            model.provider.value
            if isinstance(model.provider, CloudProviderType)
            else str(model.provider)
        )
        savings = sum(r.estimated_savings for r in model.recommendations)
        return cls(
            id=model.id,
            title=model.title,
            provider=prov,
            generated_at=model.generated_at,
            period_start=model.summary.period_start,
            period_end=model.summary.period_end,
            total_cost=model.summary.total_cost,
            total_savings=savings,
            anomaly_count=len(model.anomalies),
            report_path=report_path,
            metadata_json=model.model_dump(mode="json"),
        )


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(database_url: str | None = None) -> AsyncEngine:
    global _engine
    if _engine is None or database_url is not None:
        url = database_url or get_settings().database_url
        if url.startswith("sqlite+aiosqlite:///"):
            db_file = url.replace("sqlite+aiosqlite:///", "")
            if db_file not in (":memory:", ""):
                Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_async_engine(url, echo=False, future=True)
    return _engine


def get_session_factory(
    engine: AsyncEngine | None = None,
) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    eng = engine or get_engine()
    if _session_factory is None or engine is not None:
        _session_factory = async_sessionmaker(
            bind=eng,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db(database_url: str | None = None) -> None:
    eng = get_engine(database_url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db(database_url: str | None = None) -> None:
    eng = get_engine(database_url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
