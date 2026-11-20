from cloudguard.analysis.resource_scanner import ResourceScanner
from cloudguard.core.models import (
    CloudProviderType,
    CloudResource,
    ResourceStatus,
    ResourceType,
    ScanResult,
)


def _create_sample_resources() -> list[CloudResource]:
    return [
        CloudResource(
            id="vm-idle-1",
            name="dev-vm-idle",
            type=ResourceType.VM,
            region="eastus",
            provider=CloudProviderType.AZURE,
            tags={"Environment": "Dev", "Owner": "FinOps"},
            monthly_cost=120.0,
            utilization_pct=2.1,
            status=ResourceStatus.IDLE,
        ),
        CloudResource(
            id="vm-underutilized-1",
            name="prod-vm-low",
            type=ResourceType.VM,
            region="eastus",
            provider=CloudProviderType.AZURE,
            tags={"Environment": "Prod", "Owner": "DevOps", "Project": "Apollo"},
            monthly_cost=250.0,
            utilization_pct=12.5,
            status=ResourceStatus.RUNNING,
        ),
        CloudResource(
            id="disk-orphan-1",
            name="unattached-disk-1",
            type=ResourceType.STORAGE,
            region="eastus",
            provider=CloudProviderType.AZURE,
            tags={},
            monthly_cost=45.0,
            utilization_pct=0.0,
            status=ResourceStatus.ORPHANED,
            metadata={"is_attached": False},
        ),
        CloudResource(
            id="bucket-orphan-1",
            name="unused-s3-bucket",
            type=ResourceType.STORAGE,
            region="us-east-1",
            provider=CloudProviderType.AWS,
            tags={"Owner": "Admin"},
            monthly_cost=60.0,
            utilization_pct=0.0,
            status=ResourceStatus.RUNNING,
            metadata={"days_since_last_access": 45},
        ),
        CloudResource(
            id="vm-healthy-1",
            name="prod-web-server",
            type=ResourceType.VM,
            region="us-east-1",
            provider=CloudProviderType.AWS,
            tags={"Environment": "Prod", "Owner": "Engineering", "Project": "Core"},
            monthly_cost=300.0,
            utilization_pct=65.0,
            status=ResourceStatus.RUNNING,
        ),
    ]


def test_resource_scanner_find_idle_vms():
    resources = _create_sample_resources()
    scanner = ResourceScanner(idle_cpu_threshold_pct=5.0)
    idle = scanner.find_idle_vms(resources)

    assert len(idle) == 1
    assert idle[0].id == "vm-idle-1"
    assert idle[0].is_idle is True


def test_resource_scanner_find_orphaned_disks():
    resources = _create_sample_resources()
    scanner = ResourceScanner()
    disks = scanner.find_orphaned_disks(resources)

    assert len(disks) == 1
    assert disks[0].id == "disk-orphan-1"
    assert disks[0].is_orphaned is True


def test_resource_scanner_find_orphaned_storage():
    resources = _create_sample_resources()
    scanner = ResourceScanner(orphaned_days=30)
    orphaned = scanner.find_orphaned_storage(resources)

    assert len(orphaned) == 2
    ids = {r.id for r in orphaned}
    assert "disk-orphan-1" in ids
    assert "bucket-orphan-1" in ids


def test_resource_scanner_find_underutilized():
    resources = _create_sample_resources()
    scanner = ResourceScanner(idle_cpu_threshold_pct=5.0, underutilized_threshold_pct=20.0)
    underutilized = scanner.find_underutilized_resources(resources)

    assert len(underutilized) == 1
    assert underutilized[0].id == "vm-underutilized-1"


def test_resource_scanner_find_untagged():
    resources = _create_sample_resources()
    scanner = ResourceScanner(required_tags=["Environment", "Owner", "Project"])
    untagged = scanner.find_untagged_resources(resources)

    assert len(untagged) >= 3
    untagged_ids = {r.id for r in untagged}
    assert "disk-orphan-1" in untagged_ids
    assert "bucket-orphan-1" in untagged_ids


def test_resource_scanner_calculate_waste():
    resources = _create_sample_resources()
    scanner = ResourceScanner()
    idle = scanner.find_idle_vms(resources)
    orphaned = scanner.find_orphaned_storage(resources)
    underutilized = scanner.find_underutilized_resources(resources)

    waste = scanner.calculate_total_waste(idle, orphaned, underutilized)
    assert waste > 0.0


def test_resource_scanner_full_scan():
    resources = _create_sample_resources()
    scanner = ResourceScanner()
    scan_res = scanner.scan(resources, provider=CloudProviderType.AZURE)

    assert isinstance(scan_res, ScanResult)
    assert scan_res.idle_count == 1
    assert scan_res.orphaned_count == 2
    assert scan_res.underutilized_count == 1
    assert scan_res.untagged_count >= 3
    assert scan_res.total_resources_scanned == 5
    assert scan_res.total_waste_monthly > 0.0

    breakdown = scanner.generate_waste_breakdown(scan_res)
    assert "total_monthly_waste" in breakdown
    assert breakdown["idle_vms_count"] == 1
    assert breakdown["orphaned_storage_count"] == 2
