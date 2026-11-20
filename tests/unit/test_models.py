"""Unit tests for domain models in cloudguard.core.models."""

from datetime import date

import pytest
from pydantic import ValidationError

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
    ResourceType,
    ScanResult,
    Severity,
)


class TestCloudResource:
    def test_create_valid_resource(self, sample_resource: CloudResource):
        assert sample_resource.id == "vm-prod-app-01"
        assert sample_resource.type == ResourceType.VM
        assert sample_resource.provider == CloudProviderType.AWS
        assert sample_resource.monthly_cost == 450.0
        assert sample_resource.is_idle is False
        assert sample_resource.is_orphaned is False
        assert sample_resource.is_untagged is False

    def test_idle_detection_property(self, sample_idle_resource: CloudResource):
        assert sample_idle_resource.is_idle is True
        assert sample_idle_resource.utilization_pct < 5.0

    def test_orphaned_detection_property(self, sample_orphaned_resource: CloudResource):
        assert sample_orphaned_resource.is_orphaned is True
        assert sample_orphaned_resource.is_untagged is True

    def test_type_validator_fuzzy_parsing(self):
        res1 = CloudResource(
            id="r1",
            name="n1",
            type="Microsoft.Compute/virtualMachines",
            provider="azure",
            monthly_cost=100.0,
        )
        assert res1.type == ResourceType.VM
        assert res1.provider == CloudProviderType.AZURE

        res2 = CloudResource(
            id="r2",
            name="n2",
            type="AWS::S3::Bucket",
            provider="aws",
            monthly_cost=50.0,
        )
        assert res2.type == ResourceType.STORAGE
        assert res2.provider == CloudProviderType.AWS

        res_db = CloudResource(id="r_db", name="db", type="Microsoft.Sql/servers", provider="azure")
        assert res_db.type == ResourceType.DATABASE

        res_net = CloudResource(id="r_net", name="vpc", type="AWS::EC2::VPC", provider="aws")
        assert res_net.type == ResourceType.NETWORK

        res_k8s = CloudResource(
            id="r_k8s",
            name="aks",
            type="Microsoft.ContainerService/managedClusters",
            provider="azure",
        )
        assert res_k8s.type == ResourceType.CONTAINER

        res_fn = CloudResource(
            id="r_fn", name="lambda", type="AWS::Lambda::Function", provider="aws"
        )
        assert res_fn.type == ResourceType.SERVERLESS

        res3 = CloudResource(
            id="r3",
            name="n3",
            type="custom_unknown_type",
            provider="unknown_prov",
            monthly_cost=10.0,
        )
        assert res3.type == ResourceType.OTHER
        assert res3.provider == CloudProviderType.MOCK


class TestCostRecord:
    def test_create_cost_record(self):
        rec = CostRecord(
            service="Virtual Machines",
            date=date(2026, 8, 15),
            amount=145.50,
            currency="USD",
            provider="azure",
            region="eastus",
        )
        assert rec.service == "Virtual Machines"
        assert rec.amount == 145.50
        assert rec.provider == CloudProviderType.AZURE
        assert rec.id is not None

    def test_provider_validator_on_cost_record(self):
        rec1 = CostRecord(
            service="S3", date=date.today(), amount=10.0, provider=CloudProviderType.AWS
        )
        assert rec1.provider == CloudProviderType.AWS

        rec2 = CostRecord(service="S3", date=date.today(), amount=10.0, provider="aws")
        assert rec2.provider == CloudProviderType.AWS

        rec3 = CostRecord(
            service="S3", date=date.today(), amount=10.0, provider="unregistered_cloud"
        )
        assert rec3.provider == CloudProviderType.MOCK

    def test_negative_cost_raises_validation_error(self):
        with pytest.raises(ValidationError):
            CostRecord(
                service="Virtual Machines",
                date=date(2026, 8, 15),
                amount=-10.0,
                provider="mock",
            )


class TestCostSummary:
    def test_from_records_aggregation(self, sample_cost_records: list[CostRecord]):
        start = date(2026, 8, 1)
        end = date(2026, 8, 7)
        summary = CostSummary.from_records(sample_cost_records, start, end)

        assert summary.record_count == len(sample_cost_records)
        assert summary.total_cost > 0
        assert "Virtual Machines" in summary.cost_by_service
        assert "Object Storage" in summary.cost_by_service
        assert "Relational Database" in summary.cost_by_service
        assert "mock" in summary.cost_by_provider
        assert summary.average_daily_cost > 0
        assert len(summary.top_services) == 3
        assert summary.top_services[0][1] >= summary.top_services[1][1]


class TestAnomalyResult:
    def test_create_anomaly(self):
        anomaly = AnomalyResult(
            service="Virtual Machines",
            date=date(2026, 8, 20),
            expected_cost=850.0,
            actual_cost=3200.0,
            deviation_score=4.2,
            severity=Severity.HIGH,
            method="zscore",
            description="380% cost surge detected in GPU instances",
        )
        assert anomaly.is_anomaly is True
        assert anomaly.severity == Severity.HIGH
        assert anomaly.deviation_score == 4.2


class TestRecommendation:
    def test_create_recommendation(self):
        rec = Recommendation(
            resource_id="vm-dev-01",
            action="terminate_idle",
            title="Terminate Idle Dev Instance",
            description="Instance has <1% CPU utilization for 14 days",
            estimated_savings=350.0,
            priority=RecommendationPriority.HIGH,
            status=RecommendationStatus.OPEN,
        )
        assert rec.action == "terminate_idle"
        assert rec.estimated_savings == 350.0
        assert rec.priority == RecommendationPriority.HIGH


class TestScanResultAndReportData:
    def test_scan_result_counts(
        self, sample_idle_resource: CloudResource, sample_orphaned_resource: CloudResource
    ):
        scan = ScanResult(
            provider=CloudProviderType.MOCK,
            idle_resources=[sample_idle_resource],
            orphaned_storage=[sample_orphaned_resource],
            underutilized_vms=[],
            untagged_resources=[sample_orphaned_resource],
            total_resources_scanned=10,
            total_waste_monthly=970.0,
        )
        assert scan.idle_count == 1
        assert scan.orphaned_count == 1
        assert scan.underutilized_count == 0
        assert scan.untagged_count == 1

    def test_report_data_assembly(
        self, sample_cost_records: list[CostRecord], sample_idle_resource: CloudResource
    ):
        start = date(2026, 8, 1)
        end = date(2026, 8, 7)
        summary = CostSummary.from_records(sample_cost_records, start, end)
        scan = ScanResult(
            provider=CloudProviderType.MOCK,
            idle_resources=[sample_idle_resource],
            total_resources_scanned=1,
            total_waste_monthly=820.0,
        )

        report = ReportData(
            provider=CloudProviderType.MOCK,
            summary=summary,
            scan_result=scan,
            anomalies=[],
            recommendations=[],
        )
        assert report.id is not None
        assert report.title == "CloudGuard FinOps Executive Report"
        assert report.summary.total_cost == summary.total_cost
