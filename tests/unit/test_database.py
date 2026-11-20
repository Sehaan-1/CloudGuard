from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

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
    close_db,
    drop_db,
    get_async_session,
    get_engine,
    get_session_factory,
    init_db,
)


@pytest.fixture(autouse=True)
async def setup_test_db():
    test_db_url = "sqlite+aiosqlite:///:memory:"
    await init_db(test_db_url)
    yield
    await close_db()


@pytest.mark.asyncio
async def test_cost_record_db_model_mapping():
    cost_model = CostRecord(
        id="cr-test-01",
        resource_id="res-101",
        resource_name="vm-primary",
        service="Virtual Machines",
        date=dt.date(2026, 8, 15),
        amount=145.50,
        currency="USD",
        provider=CloudProviderType.AWS,
        region="us-east-1",
        usage_type="Compute",
        tags={"env": "prod"},
    )
    db_record = CostRecordDB.from_model(cost_model)
    assert db_record.id == "cr-test-01"
    assert db_record.resource_id == "res-101"
    assert db_record.service == "Virtual Machines"
    assert db_record.amount == 145.50
    assert db_record.provider == "aws"

    converted = db_record.to_model()
    assert converted.id == cost_model.id
    assert converted.amount == cost_model.amount
    assert converted.provider == CloudProviderType.AWS
    assert converted.tags == {"env": "prod"}

    db_record_unknown_prov = CostRecordDB(
        id="cr-unknown",
        service="Compute",
        provider="custom_cloud",
        record_date=dt.date(2026, 8, 1),
        amount=10.0,
    )
    assert db_record_unknown_prov.to_model().provider == CloudProviderType.MOCK


@pytest.mark.asyncio
async def test_resource_db_model_mapping():
    resource_model = CloudResource(
        id="vm-db-001",
        name="production-db",
        type=ResourceType.DATABASE,
        provider=CloudProviderType.AZURE,
        region="eastus",
        monthly_cost=420.0,
        utilization_pct=12.5,
        status=ResourceStatus.UNDERUTILIZED,
        tags={"owner": "devops"},
        metadata={"instance_size": "Standard_D4s_v5"},
    )
    db_res = ResourceDB.from_model(resource_model)
    assert db_res.cloud_id == "vm-db-001"
    assert db_res.type == "database"
    assert db_res.provider == "azure"

    converted = db_res.to_model()
    assert converted.id == resource_model.id
    assert converted.type == ResourceType.DATABASE
    assert converted.status == ResourceStatus.UNDERUTILIZED
    assert converted.metadata == {"instance_size": "Standard_D4s_v5"}

    db_res_unknown = ResourceDB(
        cloud_id="res-unk",
        name="unknown-thing",
        type="quantum_compute",
        provider="ali_cloud",
        status="rebooting",
    )
    conv_unk = db_res_unknown.to_model()
    assert conv_unk.type == ResourceType.OTHER
    assert conv_unk.provider == CloudProviderType.MOCK
    assert conv_unk.status == ResourceStatus.RUNNING


@pytest.mark.asyncio
async def test_anomaly_db_model_mapping():
    anomaly_model = AnomalyResult(
        id="anom-001",
        resource_id="res-storage-01",
        service="Storage",
        date=dt.date(2026, 8, 20),
        expected_cost=50.0,
        actual_cost=250.0,
        deviation_score=4.2,
        severity=Severity.HIGH,
        method="zscore",
        description="Abnormal spike in storage",
        resolved=False,
    )
    db_anom = AnomalyDB.from_model(anomaly_model)
    assert db_anom.id == "anom-001"
    assert db_anom.severity == "high"
    assert db_anom.actual_cost == 250.0

    converted = db_anom.to_model()
    assert converted.id == anomaly_model.id
    assert converted.severity == Severity.HIGH
    assert converted.deviation_score == 4.2

    db_anom_unk = AnomalyDB(
        id="anom-unk",
        service="Storage",
        date=dt.date(2026, 8, 20),
        severity="extreme_danger",
    )
    assert db_anom_unk.to_model().severity == Severity.MEDIUM


@pytest.mark.asyncio
async def test_recommendation_db_model_mapping():
    rec_model = Recommendation(
        id="rec-001",
        resource_id="vm-idle-99",
        resource_name="qa-test-vm",
        action="terminate_idle",
        title="Terminate Idle VM",
        description="VM has <1% CPU for 14 days",
        estimated_savings=180.0,
        priority=RecommendationPriority.HIGH,
        resource_type=ResourceType.VM,
        provider=CloudProviderType.AWS,
        status=RecommendationStatus.OPEN,
    )
    db_rec = RecommendationDB.from_model(rec_model)
    assert db_rec.id == "rec-001"
    assert db_rec.action == "terminate_idle"
    assert db_rec.priority == "high"

    converted = db_rec.to_model()
    assert converted.id == rec_model.id
    assert converted.priority == RecommendationPriority.HIGH
    assert converted.estimated_savings == 180.0

    db_rec_unk = RecommendationDB(
        id="rec-unk",
        resource_id="r-1",
        action="act",
        title="title",
        priority="super_urgent",
        resource_type="quantum",
        provider="custom",
        status="pending_review",
    )
    conv_rec_unk = db_rec_unk.to_model()
    assert conv_rec_unk.priority == RecommendationPriority.MEDIUM
    assert conv_rec_unk.resource_type == ResourceType.OTHER
    assert conv_rec_unk.provider == CloudProviderType.MOCK
    assert conv_rec_unk.status == RecommendationStatus.OPEN


@pytest.mark.asyncio
async def test_scan_history_db_model_mapping():
    scan_model = ScanResult(
        provider=CloudProviderType.MOCK,
        idle_resources=[
            CloudResource(
                id="idle-1",
                name="idle-vm",
                type=ResourceType.VM,
                provider=CloudProviderType.MOCK,
                monthly_cost=100.0,
                status=ResourceStatus.IDLE,
            )
        ],
        orphaned_storage=[],
        underutilized_vms=[],
        untagged_resources=[],
        total_resources_scanned=10,
        total_waste_monthly=100.0,
    )
    db_scan = ScanHistoryDB.from_model(scan_model)
    assert db_scan.provider == "mock"
    assert db_scan.idle_count == 1
    assert db_scan.total_waste_monthly == 100.0

    converted = db_scan.to_model()
    assert converted.provider == CloudProviderType.MOCK
    assert len(converted.idle_resources) == 1
    assert converted.idle_resources[0].id == "idle-1"

    db_scan_unk = ScanHistoryDB(id="s-unk", provider="cloud_xyz", raw_data={})
    assert db_scan_unk.to_model().provider == CloudProviderType.MOCK


@pytest.mark.asyncio
async def test_report_db_model_mapping():
    summary = CostSummary(
        total_cost=500.0,
        period_start=dt.date(2026, 8, 1),
        period_end=dt.date(2026, 8, 30),
        record_count=10,
    )
    scan_result = ScanResult(provider=CloudProviderType.MOCK)
    report_model = ReportData(
        id="rep-001",
        title="Monthly FinOps Report",
        provider=CloudProviderType.MOCK,
        summary=summary,
        scan_result=scan_result,
        anomalies=[],
        recommendations=[],
    )
    db_rep = ReportDB.from_model(report_model, report_path="/tmp/report.pdf")
    assert db_rep.id == "rep-001"
    assert db_rep.total_cost == 500.0
    assert db_rep.report_path == "/tmp/report.pdf"

    converted = db_rep.to_model()
    assert converted.id == report_model.id
    assert converted.summary.total_cost == 500.0


@pytest.mark.asyncio
async def test_database_engine_and_session_factory():
    eng = get_engine("sqlite+aiosqlite:///:memory:")
    assert eng is not None
    factory = get_session_factory(eng)
    assert factory is not None

    async with factory() as session:
        result = await session.execute(select(1))
        assert result.scalar() == 1

    async for session in get_async_session():
        result = await session.execute(select(1))
        assert result.scalar() == 1

    await drop_db("sqlite+aiosqlite:///:memory:")
