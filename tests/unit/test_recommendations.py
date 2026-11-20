from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from cloudguard.core.models import (
    CloudProviderType,
    CloudResource,
    Recommendation,
    RecommendationPriority,
    RecommendationStatus,
    ResourceStatus,
    ResourceType,
    ScanResult,
)
from cloudguard.engine import CostAnalysisEngine
from cloudguard.recommendations.engine import RecommendationEngine
from cloudguard.recommendations.estimator import SavingsEstimator
from cloudguard.recommendations.rules import (
    IdleVMRule,
    OldSnapshotRule,
    OptimizationRule,
    OrphanedDiskRule,
    OrphanedIPRule,
    OversizedVMRule,
    ReservedInstanceRule,
    StorageClassRule,
    UntaggedResourceRule,
)


def test_idle_vm_rule() -> None:
    rule = IdleVMRule()

    idle_vm = CloudResource(
        id="vm-idle-1",
        name="test-idle-worker",
        type=ResourceType.VM,
        provider=CloudProviderType.MOCK,
        monthly_cost=600.0,
        utilization_pct=2.5,
        status=ResourceStatus.IDLE,
        created_at=datetime.utcnow(),
    )
    rec = rule.evaluate(idle_vm)
    assert rec is not None
    assert rec.action == "terminate_idle"
    assert rec.estimated_savings == 600.0
    assert rec.priority == RecommendationPriority.URGENT
    assert rec.confidence >= 0.9

    active_vm = CloudResource(
        id="vm-active-1",
        name="test-active-worker",
        type=ResourceType.VM,
        provider=CloudProviderType.MOCK,
        monthly_cost=400.0,
        utilization_pct=65.0,
        status=ResourceStatus.RUNNING,
        created_at=datetime.utcnow(),
    )
    assert rule.evaluate(active_vm) is None

    storage_res = CloudResource(
        id="disk-1",
        name="test-disk",
        type=ResourceType.STORAGE,
        provider=CloudProviderType.MOCK,
        monthly_cost=50.0,
        utilization_pct=0.0,
        status=ResourceStatus.IDLE,
        created_at=datetime.utcnow(),
    )
    assert rule.evaluate(storage_res) is None


def test_oversized_vm_rule() -> None:
    rule = OversizedVMRule(target_downsize_pct=0.4)

    underutilized_vm = CloudResource(
        id="vm-under-1",
        name="test-oversized-db-worker",
        type=ResourceType.VM,
        provider=CloudProviderType.MOCK,
        monthly_cost=1000.0,
        utilization_pct=14.0,
        status=ResourceStatus.UNDERUTILIZED,
        created_at=datetime.utcnow(),
    )
    rec = rule.evaluate(underutilized_vm)
    assert rec is not None
    assert rec.action == "rightsize_vm"
    assert rec.estimated_savings == 400.0
    assert rec.priority == RecommendationPriority.HIGH

    idle_vm = CloudResource(
        id="vm-idle-2",
        name="idle-vm",
        type=ResourceType.VM,
        provider=CloudProviderType.MOCK,
        monthly_cost=200.0,
        utilization_pct=1.0,
        status=ResourceStatus.IDLE,
        created_at=datetime.utcnow(),
    )
    assert rule.evaluate(idle_vm) is None


def test_orphaned_disk_rule() -> None:
    rule = OrphanedDiskRule()

    orphaned_disk = CloudResource(
        id="disk-orphaned-1",
        name="unattached-ebs-volume-01",
        type=ResourceType.STORAGE,
        provider=CloudProviderType.MOCK,
        monthly_cost=120.0,
        utilization_pct=0.0,
        status=ResourceStatus.ORPHANED,
        created_at=datetime.utcnow(),
        metadata={"is_attached": False},
    )
    rec = rule.evaluate(orphaned_disk)
    assert rec is not None
    assert rec.action == "delete_orphaned_disk"
    assert rec.estimated_savings == 120.0
    assert rec.priority == RecommendationPriority.HIGH


def test_orphaned_ip_rule() -> None:
    rule = OrphanedIPRule(default_ip_cost=3.65)

    unused_ip = CloudResource(
        id="ip-1",
        name="unused-elastic-public-ip-01",
        type=ResourceType.NETWORK,
        provider=CloudProviderType.MOCK,
        monthly_cost=0.0,
        status=ResourceStatus.ORPHANED,
        created_at=datetime.utcnow(),
    )
    rec = rule.evaluate(unused_ip)
    assert rec is not None
    assert rec.action == "release_orphaned_ip"
    assert rec.estimated_savings == 3.65
    assert rec.priority == RecommendationPriority.LOW


def test_old_snapshot_rule() -> None:
    rule = OldSnapshotRule(age_days_threshold=90)

    old_snapshot = CloudResource(
        id="snap-1",
        name="database-backup-snapshot-2025",
        type=ResourceType.STORAGE,
        provider=CloudProviderType.MOCK,
        monthly_cost=50.0,
        status=ResourceStatus.RUNNING,
        created_at=datetime.utcnow() - timedelta(days=120),
        metadata={"is_snapshot": True, "age_days": 120},
    )
    rec = rule.evaluate(old_snapshot)
    assert rec is not None
    assert rec.action == "delete_old_snapshot"
    assert rec.estimated_savings == 40.0


def test_reserved_instance_rule() -> None:
    rule = ReservedInstanceRule(discount_pct=0.38)

    steady_vm = CloudResource(
        id="vm-steady-1",
        name="prod-core-api-server",
        type=ResourceType.VM,
        provider=CloudProviderType.MOCK,
        monthly_cost=800.0,
        utilization_pct=72.0,
        status=ResourceStatus.RUNNING,
        created_at=datetime.utcnow() - timedelta(days=100),
        tags={"Env": "prod"},
    )
    rec = rule.evaluate(steady_vm)
    assert rec is not None
    assert rec.action == "purchase_reserved_instance"
    assert rec.estimated_savings == 304.0
    assert rec.priority == RecommendationPriority.HIGH


def test_storage_class_rule() -> None:
    rule = StorageClassRule(tier_discount_pct=0.65)

    cold_bucket = CloudResource(
        id="bucket-1",
        name="cold-logs-archive-bucket",
        type=ResourceType.STORAGE,
        provider=CloudProviderType.MOCK,
        monthly_cost=200.0,
        utilization_pct=5.0,
        status=ResourceStatus.RUNNING,
        created_at=datetime.utcnow(),
        metadata={"service_name": "Object Storage", "cold_data": True},
    )
    rec = rule.evaluate(cold_bucket)
    assert rec is not None
    assert rec.action == "tier_to_cold_storage"
    assert rec.estimated_savings == 130.0


def test_untagged_resource_rule() -> None:
    rule = UntaggedResourceRule()

    untagged_res = CloudResource(
        id="res-untagged-1",
        name="mystery-workload",
        type=ResourceType.DATABASE,
        provider=CloudProviderType.MOCK,
        monthly_cost=350.0,
        status=ResourceStatus.RUNNING,
        created_at=datetime.utcnow(),
        tags={},
    )
    rec = rule.evaluate(untagged_res)
    assert rec is not None
    assert rec.action == "enforce_cost_allocation_tags"
    assert rec.estimated_savings == 0.0
    assert rec.confidence == 1.0


def test_savings_estimator() -> None:
    recs = [
        Recommendation(
            id="r1",
            resource_id="res-1",
            action="terminate_idle",
            title="Stop VM",
            description="Idle VM",
            estimated_savings=500.0,
            priority=RecommendationPriority.HIGH,
            resource_type=ResourceType.VM,
            confidence=0.95,
        ),
        Recommendation(
            id="r2",
            resource_id="res-2",
            action="delete_orphaned_disk",
            title="Delete Disk",
            description="Orphaned disk",
            estimated_savings=100.0,
            priority=RecommendationPriority.MEDIUM,
            resource_type=ResourceType.STORAGE,
            confidence=0.9,
        ),
        Recommendation(
            id="r3",
            resource_id="res-3",
            action="enforce_cost_allocation_tags",
            title="Tag Resource",
            description="Missing tags",
            estimated_savings=0.0,
            priority=RecommendationPriority.LOW,
            resource_type=ResourceType.DATABASE,
            confidence=1.0,
        ),
    ]

    estimator = SavingsEstimator()
    summary = estimator.summarize(recs)

    assert summary["total_monthly_savings"] == 600.0
    assert summary["total_annual_savings"] == 7200.0
    assert summary["recommendation_count"] == 3
    assert summary["quick_wins_monthly_savings"] == 500.0
    assert summary["savings_by_priority"]["high"] == 500.0
    assert summary["savings_by_priority"]["medium"] == 100.0
    assert summary["savings_by_resource_type"]["vm"] == 500.0
    assert summary["savings_by_resource_type"]["storage"] == 100.0


def test_recommendation_engine_analyze() -> None:
    idle_vm = CloudResource(
        id="vm-1",
        name="idle-vm-1",
        type=ResourceType.VM,
        provider=CloudProviderType.MOCK,
        monthly_cost=450.0,
        utilization_pct=1.5,
        status=ResourceStatus.IDLE,
        created_at=datetime.utcnow(),
    )
    orphan_disk = CloudResource(
        id="disk-1",
        name="orphaned-ebs-1",
        type=ResourceType.STORAGE,
        provider=CloudProviderType.MOCK,
        monthly_cost=80.0,
        utilization_pct=0.0,
        status=ResourceStatus.ORPHANED,
        created_at=datetime.utcnow(),
        metadata={"is_attached": False},
    )

    scan_result = ScanResult(
        idle_resources=[idle_vm],
        orphaned_storage=[orphan_disk],
        underutilized_vms=[],
        untagged_resources=[idle_vm, orphan_disk],
        total_resources_scanned=2,
        total_waste_monthly=530.0,
    )

    engine = RecommendationEngine()
    recommendations = engine.analyze(scan_result)

    assert len(recommendations) >= 2
    top = engine.get_top_recommendations(recommendations, limit=2)
    assert len(top) == 2
    assert top[0].estimated_savings >= top[1].estimated_savings

    savings = engine.estimate_savings(recommendations)
    assert savings["total_monthly_savings"] > 0.0


def test_recommendation_engine_custom_rule() -> None:
    class AlwaysSaveTenDollarsRule(OptimizationRule):
        def __init__(self) -> None:
            super().__init__(
                rule_id="CUSTOM-1",
                name="Custom 10 Dollar Rule",
                description="Custom test rule",
            )

        def evaluate(
            self,
            resource: CloudResource,
            context: dict | None = None,
        ) -> Recommendation | None:
            return Recommendation(
                id="custom-rec-1",
                resource_id=resource.id,
                action="custom_action",
                title="Custom Savings",
                description="Custom desc",
                estimated_savings=10.0,
                priority=RecommendationPriority.LOW,
                status=RecommendationStatus.OPEN,
            )

    engine = RecommendationEngine(rules=[AlwaysSaveTenDollarsRule()])
    res = CloudResource(
        id="dummy-1",
        name="dummy-res",
        type=ResourceType.OTHER,
        provider=CloudProviderType.MOCK,
        monthly_cost=100.0,
        status=ResourceStatus.RUNNING,
        created_at=datetime.utcnow(),
    )

    recs = engine.analyze([res])
    assert len(recs) == 1
    assert recs[0].action == "custom_action"
    assert recs[0].estimated_savings == 10.0

    engine.remove_rule("CUSTOM-1")
    assert len(engine.rules) == 0


@pytest.mark.asyncio
async def test_cost_analysis_engine_recommendations() -> None:
    engine = CostAnalysisEngine(provider="mock")
    recommendations = await engine.get_recommendations()
    assert isinstance(recommendations, list)
    assert len(recommendations) > 0
    for r in recommendations:
        assert isinstance(r, Recommendation)
        assert r.estimated_savings >= 0.0
