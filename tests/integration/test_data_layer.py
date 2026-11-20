from __future__ import annotations

import datetime as dt

import pytest

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
from cloudguard.data.cache import CacheManager
from cloudguard.data.database import (
    close_db,
    get_session_factory,
    init_db,
)
from cloudguard.data.repository import (
    AnomalyRepository,
    CostRepository,
    RecommendationRepository,
    ReportRepository,
    ResourceRepository,
    ScanHistoryRepository,
)


@pytest.fixture(autouse=True)
async def setup_integration_db():
    test_db_url = "sqlite+aiosqlite:///:memory:"
    await init_db(test_db_url)
    yield
    await close_db()


@pytest.mark.asyncio
async def test_full_finops_data_lifecycle_flow():
    factory = get_session_factory()
    cm = CacheManager(enable_redis=False)

    async with factory() as session:
        cost_repo = CostRepository(session)
        res_repo = ResourceRepository(session)
        anom_repo = AnomalyRepository(session)
        rec_repo = RecommendationRepository(session)
        scan_repo = ScanHistoryRepository(session)
        rep_repo = ReportRepository(session)

        resources = [
            CloudResource(
                id="i-0123456789abcdef0",
                name="prod-web-server-1",
                type=ResourceType.VM,
                provider=CloudProviderType.AWS,
                region="us-east-1",
                monthly_cost=240.0,
                utilization_pct=3.2,
                status=ResourceStatus.IDLE,
                tags={"env": "production", "app": "web"},
            ),
            CloudResource(
                id="vol-0987654321fedcba0",
                name="unused-backup-vol",
                type=ResourceType.STORAGE,
                provider=CloudProviderType.AWS,
                region="us-east-1",
                monthly_cost=65.0,
                utilization_pct=0.0,
                status=ResourceStatus.ORPHANED,
                tags={},
                metadata={"is_attached": False},
            ),
        ]
        await res_repo.save_resources(resources)

        costs = [
            CostRecord(
                id="cr-web-01",
                resource_id="i-0123456789abcdef0",
                resource_name="prod-web-server-1",
                service="Amazon Elastic Compute Cloud",
                date=dt.date(2026, 8, 20),
                amount=80.0,
                provider=CloudProviderType.AWS,
                region="us-east-1",
            ),
            CostRecord(
                id="cr-vol-01",
                resource_id="vol-0987654321fedcba0",
                resource_name="unused-backup-vol",
                service="Amazon Elastic Block Store",
                date=dt.date(2026, 8, 20),
                amount=25.0,
                provider=CloudProviderType.AWS,
                region="us-east-1",
            ),
        ]
        await cost_repo.save_cost_records(costs)

        anomalies = [
            AnomalyResult(
                id="anom-spike-1",
                resource_id="i-0123456789abcdef0",
                service="Amazon Elastic Compute Cloud",
                date=dt.date(2026, 8, 20),
                expected_cost=20.0,
                actual_cost=80.0,
                deviation_score=3.8,
                severity=Severity.HIGH,
                method="composite",
                description="4x spike detected on idle instance",
                resolved=False,
            )
        ]
        await anom_repo.save_anomalies(anomalies, cost_record_ids={"anom-spike-1": "cr-web-01"})

        recs = [
            Recommendation(
                id="rec-stop-web-1",
                resource_id="i-0123456789abcdef0",
                resource_name="prod-web-server-1",
                action="terminate_idle",
                title="Terminate Idle Instance",
                description="Stop instance to eliminate $240/mo spend",
                estimated_savings=240.0,
                priority=RecommendationPriority.HIGH,
                resource_type=ResourceType.VM,
                provider=CloudProviderType.AWS,
                status=RecommendationStatus.OPEN,
            )
        ]
        await rec_repo.save_recommendations(recs)

        scan_result = ScanResult(
            provider=CloudProviderType.AWS,
            idle_resources=[resources[0]],
            orphaned_storage=[resources[1]],
            total_resources_scanned=2,
            total_waste_monthly=305.0,
        )
        scan_id = await scan_repo.save_scan_result(scan_result)
        assert scan_id is not None

        cost_summary = await cost_repo.get_cost_summary(
            dt.date(2026, 8, 1), dt.date(2026, 8, 30), provider=CloudProviderType.AWS
        )
        assert cost_summary.total_cost == 105.0
        assert cost_summary.record_count == 2

        await cm.set_cost_summary("aws:2026-08:summary", cost_summary, ttl=300)
        cached_summary = await cm.get_cost_summary("aws:2026-08:summary")
        assert cached_summary is not None
        assert cached_summary.total_cost == 105.0

        report_data = ReportData(
            id="rep-finops-august",
            title="AWS FinOps Audit August 2026",
            provider=CloudProviderType.AWS,
            summary=cost_summary,
            scan_result=scan_result,
            anomalies=anomalies,
            recommendations=recs,
        )
        saved_rep_id = await rep_repo.save_report(
            report_data, report_path="reports/aws_august_2026.pdf"
        )
        assert saved_rep_id == "rep-finops-august"

        loaded_rep = await rep_repo.get_report_by_id("rep-finops-august")
        assert loaded_rep is not None
        assert loaded_rep.total_cost == 105.0
        assert loaded_rep.total_savings == 240.0
        assert loaded_rep.anomaly_count == 1

        unresolved_anoms = await anom_repo.get_anomalies(resolved=False)
        assert len(unresolved_anoms) == 1
        assert unresolved_anoms[0].id == "anom-spike-1"

        resolve_success = await anom_repo.resolve_anomaly("anom-spike-1", resolved=True)
        assert resolve_success is True

        open_recs = await rec_repo.get_recommendations(status=RecommendationStatus.OPEN)
        assert len(open_recs) == 1
        rec_update = await rec_repo.update_status("rec-stop-web-1", RecommendationStatus.APPLIED)
        assert rec_update is True

        applied_recs = await rec_repo.get_recommendations(status=RecommendationStatus.APPLIED)
        assert len(applied_recs) == 1

    await cm.close()
