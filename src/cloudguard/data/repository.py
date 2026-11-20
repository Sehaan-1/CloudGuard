from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudguard.core.models import (
    AnomalyResult,
    CloudProviderType,
    CloudResource,
    CostRecord,
    CostSummary,
    Recommendation,
    RecommendationPriority,
    RecommendationStatus,
    ReportData,
    ResourceStatus,
    ResourceType,
    ScanResult,
    Severity,
)
from cloudguard.data.database import (
    AnomalyDB,
    CostRecordDB,
    RecommendationDB,
    ReportDB,
    ResourceDB,
    ScanHistoryDB,
)


class BaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session


class CostRepository(BaseRepository):
    async def save_cost_records(self, records: list[CostRecord]) -> None:
        for record in records:
            stmt = select(CostRecordDB).where(CostRecordDB.id == record.id)
            res = await self.session.execute(stmt)
            existing = res.scalar_one_or_none()
            prov = (
                record.provider.value
                if isinstance(record.provider, CloudProviderType)
                else str(record.provider)
            )
            if existing:
                existing.resource_id = record.resource_id
                existing.resource_name = record.resource_name
                existing.service = record.service
                existing.provider = prov
                existing.record_date = record.date
                existing.amount = record.amount
                existing.currency = record.currency
                existing.region = record.region
                existing.usage_type = record.usage_type
                existing.tags = record.tags or {}
            else:
                db_item = CostRecordDB.from_model(record)
                self.session.add(db_item)
        await self.session.commit()

    async def get_costs_by_date_range(
        self,
        start: dt.date,
        end: dt.date,
        provider: str | CloudProviderType | None = None,
    ) -> list[CostRecord]:
        stmt = (
            select(CostRecordDB)
            .where(CostRecordDB.record_date >= start)
            .where(CostRecordDB.record_date <= end)
        )
        if provider:
            p_val = provider.value if isinstance(provider, CloudProviderType) else str(provider)
            stmt = stmt.where(CostRecordDB.provider == p_val)
        stmt = stmt.order_by(CostRecordDB.record_date.asc())
        res = await self.session.execute(stmt)
        return [row.to_model() for row in res.scalars().all()]

    async def get_costs_by_service(
        self,
        service: str,
        start: dt.date,
        end: dt.date,
        provider: str | CloudProviderType | None = None,
    ) -> list[CostRecord]:
        stmt = (
            select(CostRecordDB)
            .where(CostRecordDB.service == service)
            .where(CostRecordDB.record_date >= start)
            .where(CostRecordDB.record_date <= end)
        )
        if provider:
            p_val = provider.value if isinstance(provider, CloudProviderType) else str(provider)
            stmt = stmt.where(CostRecordDB.provider == p_val)
        stmt = stmt.order_by(CostRecordDB.record_date.asc())
        res = await self.session.execute(stmt)
        return [row.to_model() for row in res.scalars().all()]

    async def get_cost_summary(
        self,
        start: dt.date,
        end: dt.date,
        provider: str | CloudProviderType | None = None,
    ) -> CostSummary:
        records = await self.get_costs_by_date_range(start, end, provider)
        return CostSummary.from_records(records, start, end)

    async def get_all_records(self, limit: int | None = None, offset: int = 0) -> list[CostRecord]:
        stmt = select(CostRecordDB).order_by(CostRecordDB.record_date.desc()).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        res = await self.session.execute(stmt)
        return [row.to_model() for row in res.scalars().all()]

    async def get_records_by_resource_id(self, resource_id: str) -> list[CostRecord]:
        stmt = (
            select(CostRecordDB)
            .where(CostRecordDB.resource_id == resource_id)
            .order_by(CostRecordDB.record_date.asc())
        )
        res = await self.session.execute(stmt)
        return [row.to_model() for row in res.scalars().all()]

    async def delete_records_by_date_range(
        self,
        start: dt.date,
        end: dt.date,
        provider: str | CloudProviderType | None = None,
    ) -> int:
        stmt = (
            delete(CostRecordDB)
            .where(CostRecordDB.record_date >= start)
            .where(CostRecordDB.record_date <= end)
        )
        if provider:
            p_val = provider.value if isinstance(provider, CloudProviderType) else str(provider)
            stmt = stmt.where(CostRecordDB.provider == p_val)
        res = await self.session.execute(stmt)
        await self.session.commit()
        return res.rowcount or 0


class ResourceRepository(BaseRepository):
    async def save_resources(self, resources: list[CloudResource]) -> None:
        for resource in resources:
            stmt = select(ResourceDB).where(ResourceDB.cloud_id == resource.id)
            res = await self.session.execute(stmt)
            existing = res.scalar_one_or_none()
            res_type = (
                resource.type.value
                if isinstance(resource.type, ResourceType)
                else str(resource.type)
            )
            prov = (
                resource.provider.value
                if isinstance(resource.provider, CloudProviderType)
                else str(resource.provider)
            )
            stat = (
                resource.status.value
                if isinstance(resource.status, ResourceStatus)
                else str(resource.status)
            )
            if existing:
                existing.name = resource.name
                existing.type = res_type
                existing.provider = prov
                existing.region = resource.region
                existing.monthly_cost = resource.monthly_cost
                existing.utilization_pct = resource.utilization_pct
                existing.status = stat
                existing.tags = resource.tags or {}
                existing.created_at = resource.created_at
                existing.last_scanned = resource.last_scanned
                existing.metadata_json = resource.metadata or {}
            else:
                db_item = ResourceDB.from_model(resource)
                self.session.add(db_item)
        await self.session.commit()

    async def get_resources(
        self,
        provider: str | CloudProviderType | None = None,
        resource_type: ResourceType | str | None = None,
        status: ResourceStatus | str | None = None,
    ) -> list[CloudResource]:
        stmt = select(ResourceDB)
        if provider:
            p_val = provider.value if isinstance(provider, CloudProviderType) else str(provider)
            stmt = stmt.where(ResourceDB.provider == p_val)
        if resource_type:
            t_val = (
                resource_type.value
                if isinstance(resource_type, ResourceType)
                else str(resource_type)
            )
            stmt = stmt.where(ResourceDB.type == t_val)
        if status:
            s_val = status.value if isinstance(status, ResourceStatus) else str(status)
            stmt = stmt.where(ResourceDB.status == s_val)
        stmt = stmt.order_by(ResourceDB.name.asc())
        res = await self.session.execute(stmt)
        return [row.to_model() for row in res.scalars().all()]

    async def get_resource_by_cloud_id(self, cloud_id: str) -> CloudResource | None:
        stmt = select(ResourceDB).where(ResourceDB.cloud_id == cloud_id)
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        return row.to_model() if row else None

    async def get_idle_resources(
        self, provider: str | CloudProviderType | None = None
    ) -> list[CloudResource]:
        return await self.get_resources(provider=provider, status=ResourceStatus.IDLE)

    async def get_orphaned_resources(
        self, provider: str | CloudProviderType | None = None
    ) -> list[CloudResource]:
        return await self.get_resources(provider=provider, status=ResourceStatus.ORPHANED)

    async def get_underutilized_resources(
        self, provider: str | CloudProviderType | None = None
    ) -> list[CloudResource]:
        return await self.get_resources(provider=provider, status=ResourceStatus.UNDERUTILIZED)

    async def get_untagged_resources(
        self, provider: str | CloudProviderType | None = None
    ) -> list[CloudResource]:
        all_res = await self.get_resources(provider=provider)
        return [r for r in all_res if r.is_untagged]

    async def delete_resource(self, cloud_id: str) -> bool:
        stmt = delete(ResourceDB).where(ResourceDB.cloud_id == cloud_id)
        res = await self.session.execute(stmt)
        await self.session.commit()
        return bool(res.rowcount and res.rowcount > 0)


class AnomalyRepository(BaseRepository):
    async def save_anomalies(
        self,
        anomalies: list[AnomalyResult],
        cost_record_ids: dict[str, str] | None = None,
    ) -> None:
        for anom in anomalies:
            stmt = select(AnomalyDB).where(AnomalyDB.id == anom.id)
            res = await self.session.execute(stmt)
            existing = res.scalar_one_or_none()
            sev = anom.severity.value if isinstance(anom.severity, Severity) else str(anom.severity)
            if existing:
                existing.resource_id = anom.resource_id
                existing.service = anom.service
                existing.date = anom.date
                existing.expected_cost = anom.expected_cost
                existing.actual_cost = anom.actual_cost
                existing.deviation_score = anom.deviation_score
                existing.severity = sev
                existing.method = anom.method
                existing.description = anom.description
                existing.is_anomaly = anom.is_anomaly
                existing.resolved = anom.resolved
                existing.detected_at = anom.detected_at
                existing.metadata_json = anom.metadata or {}
            else:
                c_id = cost_record_ids.get(anom.id) if cost_record_ids else None
                db_item = AnomalyDB.from_model(anom, cost_record_id=c_id)
                self.session.add(db_item)
        await self.session.commit()

    async def get_anomalies(
        self,
        start_date: dt.date | None = None,
        end_date: dt.date | None = None,
        severity: Severity | str | None = None,
        resolved: bool | None = None,
        service: str | None = None,
    ) -> list[AnomalyResult]:
        stmt = select(AnomalyDB)
        if start_date:
            stmt = stmt.where(AnomalyDB.date >= start_date)
        if end_date:
            stmt = stmt.where(AnomalyDB.date <= end_date)
        if severity:
            sev_val = severity.value if isinstance(severity, Severity) else str(severity)
            stmt = stmt.where(AnomalyDB.severity == sev_val)
        if resolved is not None:
            stmt = stmt.where(AnomalyDB.resolved == resolved)
        if service:
            stmt = stmt.where(AnomalyDB.service == service)
        stmt = stmt.order_by(AnomalyDB.date.desc())
        res = await self.session.execute(stmt)
        return [row.to_model() for row in res.scalars().all()]

    async def get_anomaly_by_id(self, anomaly_id: str) -> AnomalyResult | None:
        stmt = select(AnomalyDB).where(AnomalyDB.id == anomaly_id)
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        return row.to_model() if row else None

    async def resolve_anomaly(self, anomaly_id: str, resolved: bool = True) -> bool:
        stmt = select(AnomalyDB).where(AnomalyDB.id == anomaly_id)
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        if row:
            row.resolved = resolved
            await self.session.commit()
            return True
        return False

    async def delete_anomaly(self, anomaly_id: str) -> bool:
        stmt = delete(AnomalyDB).where(AnomalyDB.id == anomaly_id)
        res = await self.session.execute(stmt)
        await self.session.commit()
        return bool(res.rowcount and res.rowcount > 0)


class RecommendationRepository(BaseRepository):
    async def save_recommendations(self, recommendations: list[Recommendation]) -> None:
        for rec in recommendations:
            stmt = select(RecommendationDB).where(RecommendationDB.id == rec.id)
            res = await self.session.execute(stmt)
            existing = res.scalar_one_or_none()
            prio = (
                rec.priority.value
                if isinstance(rec.priority, RecommendationPriority)
                else str(rec.priority)
            )
            res_type = (
                rec.resource_type.value
                if isinstance(rec.resource_type, ResourceType)
                else str(rec.resource_type)
            )
            prov = (
                rec.provider.value
                if isinstance(rec.provider, CloudProviderType)
                else str(rec.provider)
            )
            stat = (
                rec.status.value
                if isinstance(rec.status, RecommendationStatus)
                else str(rec.status)
            )
            if existing:
                existing.resource_id = rec.resource_id
                existing.resource_name = rec.resource_name
                existing.action = rec.action
                existing.title = rec.title
                existing.description = rec.description
                existing.estimated_savings = rec.estimated_savings
                existing.currency = rec.currency
                existing.confidence = rec.confidence
                existing.priority = prio
                existing.resource_type = res_type
                existing.provider = prov
                existing.status = stat
                existing.created_at = rec.created_at
            else:
                db_item = RecommendationDB.from_model(rec)
                self.session.add(db_item)
        await self.session.commit()

    async def get_recommendations(
        self,
        status: RecommendationStatus | str | None = None,
        priority: RecommendationPriority | str | None = None,
        provider: str | CloudProviderType | None = None,
        resource_id: str | None = None,
    ) -> list[Recommendation]:
        stmt = select(RecommendationDB)
        if status:
            s_val = status.value if isinstance(status, RecommendationStatus) else str(status)
            stmt = stmt.where(RecommendationDB.status == s_val)
        if priority:
            p_val = (
                priority.value if isinstance(priority, RecommendationPriority) else str(priority)
            )
            stmt = stmt.where(RecommendationDB.priority == p_val)
        if provider:
            pr_val = provider.value if isinstance(provider, CloudProviderType) else str(provider)
            stmt = stmt.where(RecommendationDB.provider == pr_val)
        if resource_id:
            stmt = stmt.where(RecommendationDB.resource_id == resource_id)
        stmt = stmt.order_by(RecommendationDB.estimated_savings.desc())
        res = await self.session.execute(stmt)
        return [row.to_model() for row in res.scalars().all()]

    async def get_recommendation_by_id(self, rec_id: str) -> Recommendation | None:
        stmt = select(RecommendationDB).where(RecommendationDB.id == rec_id)
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        return row.to_model() if row else None

    async def update_status(self, rec_id: str, status: RecommendationStatus | str) -> bool:
        stmt = select(RecommendationDB).where(RecommendationDB.id == rec_id)
        res = await self.session.execute(stmt)
        row = res.scalar_one_or_none()
        if row:
            s_val = status.value if isinstance(status, RecommendationStatus) else str(status)
            row.status = s_val
            await self.session.commit()
            return True
        return False

    async def delete_recommendation(self, rec_id: str) -> bool:
        stmt = delete(RecommendationDB).where(RecommendationDB.id == rec_id)
        res = await self.session.execute(stmt)
        await self.session.commit()
        return bool(res.rowcount and res.rowcount > 0)


class ScanHistoryRepository(BaseRepository):
    async def save_scan_result(self, scan_result: ScanResult) -> str:
        db_item = ScanHistoryDB.from_model(scan_result)
        self.session.add(db_item)
        await self.session.commit()
        return db_item.id

    async def get_scan_history(
        self,
        provider: str | CloudProviderType | None = None,
        limit: int = 10,
    ) -> list[ScanResult]:
        stmt = select(ScanHistoryDB)
        if provider:
            p_val = provider.value if isinstance(provider, CloudProviderType) else str(provider)
            stmt = stmt.where(ScanHistoryDB.provider == p_val)
        stmt = stmt.order_by(ScanHistoryDB.scanned_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return [row.to_model() for row in res.scalars().all()]

    async def get_latest_scan(
        self, provider: str | CloudProviderType | None = None
    ) -> ScanResult | None:
        items = await self.get_scan_history(provider=provider, limit=1)
        return items[0] if items else None


class ReportRepository(BaseRepository):
    async def save_report(self, report: ReportData, report_path: str | None = None) -> str:
        db_item = ReportDB.from_model(report, report_path=report_path)
        self.session.add(db_item)
        await self.session.commit()
        return db_item.id

    async def get_reports(
        self,
        provider: str | CloudProviderType | None = None,
        limit: int = 10,
    ) -> list[ReportDB]:
        stmt = select(ReportDB)
        if provider:
            p_val = provider.value if isinstance(provider, CloudProviderType) else str(provider)
            stmt = stmt.where(ReportDB.provider == p_val)
        stmt = stmt.order_by(ReportDB.generated_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_report_by_id(self, report_id: str) -> ReportDB | None:
        stmt = select(ReportDB).where(ReportDB.id == report_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_latest_report(
        self, provider: str | CloudProviderType | None = None
    ) -> ReportData | None:
        reports = await self.get_reports(provider=provider, limit=1)
        if reports:
            return reports[0].to_model()
        return None
