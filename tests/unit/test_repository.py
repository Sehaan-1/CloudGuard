from __future__ import annotations

import datetime as dt

import pytest

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
async def setup_test_db():
    test_db_url = "sqlite+aiosqlite:///:memory:"
    await init_db(test_db_url)
    yield
    await close_db()


@pytest.mark.asyncio
async def test_cost_repository_crud():
    factory = get_session_factory()
    async with factory() as session:
        repo = CostRepository(session)
        records = [
            CostRecord(
                id=f"rec-{i}",
                resource_id=f"res-{i}",
                service="Virtual Machines" if i % 2 == 0 else "Storage",
                date=dt.date(2026, 8, 10 + i),
                amount=100.0 + (i * 10),
                provider=CloudProviderType.AWS if i % 2 == 0 else CloudProviderType.AZURE,
                region="us-east-1",
            )
            for i in range(5)
        ]
        await repo.save_cost_records(records)

        costs = await repo.get_costs_by_date_range(dt.date(2026, 8, 10), dt.date(2026, 8, 12))
        assert len(costs) == 3

        aws_costs = await repo.get_costs_by_date_range(
            dt.date(2026, 8, 10), dt.date(2026, 8, 14), provider=CloudProviderType.AWS
        )
        assert len(aws_costs) == 3

        svc_costs = await repo.get_costs_by_service(
            "Storage", dt.date(2026, 8, 10), dt.date(2026, 8, 14)
        )
        assert len(svc_costs) == 2

        svc_aws = await repo.get_costs_by_service(
            "Virtual Machines",
            dt.date(2026, 8, 10),
            dt.date(2026, 8, 14),
            provider=CloudProviderType.AWS,
        )
        assert len(svc_aws) == 3

        summary = await repo.get_cost_summary(dt.date(2026, 8, 10), dt.date(2026, 8, 14))
        assert summary.record_count == 5
        assert summary.total_cost == sum(r.amount for r in records)

        summary_azure = await repo.get_cost_summary(
            dt.date(2026, 8, 10), dt.date(2026, 8, 14), provider=CloudProviderType.AZURE
        )
        assert summary_azure.record_count == 2

        all_recs = await repo.get_all_records(limit=3)
        assert len(all_recs) == 3

        by_res = await repo.get_records_by_resource_id("res-0")
        assert len(by_res) == 1
        assert by_res[0].id == "rec-0"

        updated_records = [
            CostRecord(
                id="rec-0",
                resource_id="res-0",
                service="Virtual Machines",
                date=dt.date(2026, 8, 10),
                amount=999.0,
                provider=CloudProviderType.AWS,
                region="us-east-1",
            )
        ]
        await repo.save_cost_records(updated_records)
        updated_res = await repo.get_records_by_resource_id("res-0")
        assert updated_res[0].amount == 999.0

        deleted_prov = await repo.delete_records_by_date_range(
            dt.date(2026, 8, 10), dt.date(2026, 8, 11), provider=CloudProviderType.AWS
        )
        assert deleted_prov == 1

        deleted = await repo.delete_records_by_date_range(
            dt.date(2026, 8, 10), dt.date(2026, 8, 11)
        )
        assert deleted == 1

        remaining = await repo.get_all_records()
        assert len(remaining) == 3


@pytest.mark.asyncio
async def test_resource_repository_crud():
    factory = get_session_factory()
    async with factory() as session:
        repo = ResourceRepository(session)
        resources = [
            CloudResource(
                id="vm-idle-1",
                name="dev-vm",
                type=ResourceType.VM,
                provider=CloudProviderType.AWS,
                monthly_cost=150.0,
                utilization_pct=2.0,
                status=ResourceStatus.IDLE,
                tags={"env": "dev"},
            ),
            CloudResource(
                id="disk-orphan-1",
                name="unused-vol",
                type=ResourceType.STORAGE,
                provider=CloudProviderType.AZURE,
                monthly_cost=50.0,
                utilization_pct=0.0,
                status=ResourceStatus.ORPHANED,
                tags={},
                metadata={"is_attached": False},
            ),
            CloudResource(
                id="vm-under-1",
                name="staging-vm",
                type=ResourceType.VM,
                provider=CloudProviderType.AWS,
                monthly_cost=300.0,
                utilization_pct=15.0,
                status=ResourceStatus.UNDERUTILIZED,
                tags={},
            ),
        ]
        await repo.save_resources(resources)

        all_res = await repo.get_resources()
        assert len(all_res) == 3

        by_type = await repo.get_resources(resource_type=ResourceType.STORAGE)
        assert len(by_type) == 1
        assert by_type[0].id == "disk-orphan-1"

        by_status = await repo.get_resources(status=ResourceStatus.IDLE)
        assert len(by_status) == 1
        assert by_status[0].id == "vm-idle-1"

        res_by_id = await repo.get_resource_by_cloud_id("vm-idle-1")
        assert res_by_id is not None
        assert res_by_id.name == "dev-vm"

        aws_res = await repo.get_resources(provider=CloudProviderType.AWS)
        assert len(aws_res) == 2

        idle = await repo.get_idle_resources()
        assert len(idle) == 1
        assert idle[0].id == "vm-idle-1"

        orphaned = await repo.get_orphaned_resources()
        assert len(orphaned) == 1
        assert orphaned[0].id == "disk-orphan-1"

        under = await repo.get_underutilized_resources()
        assert len(under) == 1
        assert under[0].id == "vm-under-1"

        untagged = await repo.get_untagged_resources()
        assert len(untagged) == 2

        updated_resources = [
            CloudResource(
                id="vm-idle-1",
                name="dev-vm-renamed",
                type=ResourceType.VM,
                provider=CloudProviderType.AWS,
                monthly_cost=180.0,
                utilization_pct=3.0,
                status=ResourceStatus.IDLE,
                tags={"env": "qa"},
            )
        ]
        await repo.save_resources(updated_resources)
        updated_res = await repo.get_resource_by_cloud_id("vm-idle-1")
        assert updated_res is not None
        assert updated_res.name == "dev-vm-renamed"
        assert updated_res.monthly_cost == 180.0

        del_ok = await repo.delete_resource("vm-idle-1")
        assert del_ok is True
        assert await repo.get_resource_by_cloud_id("vm-idle-1") is None
        assert await repo.delete_resource("non-existent-id") is False


@pytest.mark.asyncio
async def test_anomaly_repository_crud():
    factory = get_session_factory()
    async with factory() as session:
        repo = AnomalyRepository(session)
        anomalies = [
            AnomalyResult(
                id="anom-1",
                service="Virtual Machines",
                date=dt.date(2026, 8, 15),
                expected_cost=100.0,
                actual_cost=400.0,
                deviation_score=3.5,
                severity=Severity.HIGH,
                resolved=False,
            ),
            AnomalyResult(
                id="anom-2",
                service="Storage",
                date=dt.date(2026, 8, 16),
                expected_cost=50.0,
                actual_cost=120.0,
                deviation_score=2.1,
                severity=Severity.MEDIUM,
                resolved=True,
            ),
        ]
        await repo.save_anomalies(anomalies)

        all_anoms = await repo.get_anomalies()
        assert len(all_anoms) == 2

        by_dates = await repo.get_anomalies(
            start_date=dt.date(2026, 8, 16), end_date=dt.date(2026, 8, 17)
        )
        assert len(by_dates) == 1
        assert by_dates[0].id == "anom-2"

        by_svc = await repo.get_anomalies(service="Storage")
        assert len(by_svc) == 1

        high_anoms = await repo.get_anomalies(severity=Severity.HIGH)
        assert len(high_anoms) == 1
        assert high_anoms[0].id == "anom-1"

        unresolved = await repo.get_anomalies(resolved=False)
        assert len(unresolved) == 1
        assert unresolved[0].id == "anom-1"

        by_id = await repo.get_anomaly_by_id("anom-1")
        assert by_id is not None
        assert by_id.actual_cost == 400.0

        resolved_ok = await repo.resolve_anomaly("anom-1", resolved=True)
        assert resolved_ok is True
        by_id_after = await repo.get_anomaly_by_id("anom-1")
        assert by_id_after.resolved is True

        assert await repo.resolve_anomaly("missing-anom", resolved=True) is False

        updated_anoms = [
            AnomalyResult(
                id="anom-1",
                service="Virtual Machines",
                date=dt.date(2026, 8, 15),
                expected_cost=100.0,
                actual_cost=450.0,
                deviation_score=4.0,
                severity=Severity.CRITICAL,
                resolved=True,
            )
        ]
        await repo.save_anomalies(updated_anoms)
        updated_anom_res = await repo.get_anomaly_by_id("anom-1")
        assert updated_anom_res.actual_cost == 450.0
        assert updated_anom_res.severity == Severity.CRITICAL

        del_ok = await repo.delete_anomaly("anom-2")
        assert del_ok is True
        assert len(await repo.get_anomalies()) == 1
        assert await repo.delete_anomaly("missing-anom") is False


@pytest.mark.asyncio
async def test_recommendation_repository_crud():
    factory = get_session_factory()
    async with factory() as session:
        repo = RecommendationRepository(session)
        recs = [
            Recommendation(
                id="rec-1",
                resource_id="vm-1",
                action="terminate_idle",
                title="Terminate Idle Instance",
                description="Save costs",
                estimated_savings=200.0,
                priority=RecommendationPriority.URGENT,
                provider=CloudProviderType.AWS,
                status=RecommendationStatus.OPEN,
            ),
            Recommendation(
                id="rec-2",
                resource_id="disk-1",
                action="delete_orphaned",
                title="Delete Orphaned Disk",
                description="Save storage costs",
                estimated_savings=50.0,
                priority=RecommendationPriority.LOW,
                provider=CloudProviderType.AZURE,
                status=RecommendationStatus.APPLIED,
            ),
        ]
        await repo.save_recommendations(recs)

        open_recs = await repo.get_recommendations(status=RecommendationStatus.OPEN)
        assert len(open_recs) == 1
        assert open_recs[0].id == "rec-1"

        urgent_recs = await repo.get_recommendations(priority=RecommendationPriority.URGENT)
        assert len(urgent_recs) == 1
        assert urgent_recs[0].id == "rec-1"

        aws_recs = await repo.get_recommendations(provider=CloudProviderType.AWS)
        assert len(aws_recs) == 1

        by_res = await repo.get_recommendations(resource_id="disk-1")
        assert len(by_res) == 1

        by_id = await repo.get_recommendation_by_id("rec-1")
        assert by_id is not None
        assert by_id.estimated_savings == 200.0

        updated = await repo.update_status("rec-1", RecommendationStatus.APPLIED)
        assert updated is True
        by_id_after = await repo.get_recommendation_by_id("rec-1")
        assert by_id_after.status == RecommendationStatus.APPLIED
        assert await repo.update_status("missing-rec", RecommendationStatus.OPEN) is False

        updated_recs = [
            Recommendation(
                id="rec-1",
                resource_id="vm-1",
                action="terminate_idle",
                title="Terminate Idle Instance Immediately",
                description="Updated description",
                estimated_savings=250.0,
                priority=RecommendationPriority.URGENT,
                provider=CloudProviderType.AWS,
                status=RecommendationStatus.APPLIED,
            )
        ]
        await repo.save_recommendations(updated_recs)
        updated_rec_res = await repo.get_recommendation_by_id("rec-1")
        assert updated_rec_res.estimated_savings == 250.0

        deleted = await repo.delete_recommendation("rec-2")
        assert deleted is True
        assert len(await repo.get_recommendations()) == 1
        assert await repo.delete_recommendation("missing-rec") is False


@pytest.mark.asyncio
async def test_scan_and_report_repositories():
    factory = get_session_factory()
    async with factory() as session:
        scan_repo = ScanHistoryRepository(session)
        scan = ScanResult(
            provider=CloudProviderType.MOCK,
            total_resources_scanned=25,
            total_waste_monthly=350.0,
        )
        scan_id = await scan_repo.save_scan_result(scan)
        assert scan_id is not None

        history = await scan_repo.get_scan_history()
        assert len(history) == 1
        assert history[0].total_resources_scanned == 25

        hist_mock = await scan_repo.get_scan_history(provider=CloudProviderType.MOCK)
        assert len(hist_mock) == 1

        latest = await scan_repo.get_latest_scan()
        assert latest is not None
        assert latest.total_waste_monthly == 350.0

        latest_aws = await scan_repo.get_latest_scan(provider=CloudProviderType.AWS)
        assert latest_aws is None

        rep_repo = ReportRepository(session)
        report = ReportData(
            id="rep-xyz",
            title="Q3 FinOps Review",
            provider=CloudProviderType.MOCK,
            summary=CostSummary(
                total_cost=1200.0,
                period_start=dt.date(2026, 7, 1),
                period_end=dt.date(2026, 7, 31),
                record_count=100,
            ),
            scan_result=scan,
            anomalies=[],
            recommendations=[],
        )
        rep_id = await rep_repo.save_report(report, report_path="/tmp/q3_report.pdf")
        assert rep_id == "rep-xyz"

        reports = await rep_repo.get_reports()
        assert len(reports) == 1
        assert reports[0].id == "rep-xyz"

        reports_mock = await rep_repo.get_reports(provider=CloudProviderType.MOCK)
        assert len(reports_mock) == 1

        rep_by_id = await rep_repo.get_report_by_id("rep-xyz")
        assert rep_by_id is not None
        assert rep_by_id.total_cost == 1200.0

        latest_rep = await rep_repo.get_latest_report()
        assert latest_rep is not None
        assert latest_rep.title == "Q3 FinOps Review"

        latest_rep_aws = await rep_repo.get_latest_report(provider=CloudProviderType.AWS)
        assert latest_rep_aws is None
