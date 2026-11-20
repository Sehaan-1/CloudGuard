"""Unit tests for AWSProvider with mocked Boto3 clients."""

from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from cloudguard.core.models import CloudProviderType, Granularity, ResourceStatus, ResourceType
from cloudguard.providers.aws_provider import AWSProvider


@pytest.fixture
def mocked_aws_provider():
    provider = AWSProvider(
        aws_access_key_id="test-access-key",
        aws_secret_access_key="test-secret-key",
        region_name="us-east-1",
    )
    provider._session = MagicMock()
    provider._ce_client = MagicMock()
    provider._ec2_client = MagicMock()
    provider._s3_client = MagicMock()
    provider._cw_client = MagicMock()
    return provider


class TestAWSProviderMocked:
    @pytest.mark.asyncio
    async def test_aws_test_connection_success(self, mocked_aws_provider):
        sts_mock = MagicMock()
        mocked_aws_provider._session.client.return_value = sts_mock
        sts_mock.get_caller_identity.return_value = {
            "UserId": "AIDA12345",
            "Account": "123456789012",
        }

        connected = await mocked_aws_provider.test_connection()
        assert connected is True

    @pytest.mark.asyncio
    async def test_aws_get_cost_data(self, mocked_aws_provider):
        mocked_aws_provider._ce_client.get_cost_and_usage.return_value = {
            "ResultsByTime": [
                {
                    "TimePeriod": {"Start": "2026-08-10", "End": "2026-08-11"},
                    "Groups": [
                        {
                            "Keys": ["Amazon Elastic Compute Cloud - Compute", "us-east-1"],
                            "Metrics": {"UnblendedCost": {"Amount": "210.50", "Unit": "USD"}},
                        },
                        {
                            "Keys": ["Amazon Simple Storage Service", "us-east-1"],
                            "Metrics": {"UnblendedCost": {"Amount": "42.00", "Unit": "USD"}},
                        },
                    ],
                }
            ],
            "NextPageToken": None,
        }

        start = date(2026, 8, 10)
        end = date(2026, 8, 11)
        records = await mocked_aws_provider.get_cost_data(start, end, Granularity.DAILY)

        assert len(records) == 2
        assert records[0].service == "Amazon Elastic Compute Cloud - Compute"
        assert records[0].amount == 210.50
        assert records[0].provider == CloudProviderType.AWS
        assert records[0].currency == "USD"
        assert records[0].date == date(2026, 8, 10)

    @pytest.mark.asyncio
    async def test_aws_list_resources(self, mocked_aws_provider):
        mocked_aws_provider._ec2_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-0123456789abcdef0",
                            "InstanceType": "c5.2xlarge",
                            "State": {"Name": "running"},
                            "Tags": [
                                {"Key": "Name", "Value": "prod-app-server"},
                                {"Key": "Owner", "Value": "infra"},
                            ],
                        }
                    ]
                }
            ]
        }

        mocked_aws_provider._ec2_client.describe_volumes.return_value = {
            "Volumes": [
                {
                    "VolumeId": "vol-attached-1",
                    "Size": 100,
                    "AvailabilityZone": "us-east-1a",
                    "State": "in-use",
                    "Attachments": [{"InstanceId": "i-0123456789abcdef0"}],
                    "Tags": [{"Key": "Name", "Value": "root-vol"}],
                },
                {
                    "VolumeId": "vol-orphan-1",
                    "Size": 500,
                    "AvailabilityZone": "us-east-1b",
                    "State": "available",
                    "Attachments": [],
                    "Tags": [],
                },
            ]
        }

        mocked_aws_provider._s3_client.list_buckets.return_value = {
            "Buckets": [{"Name": "my-company-backup-bucket", "CreationDate": datetime(2025, 1, 1)}]
        }

        resources = await mocked_aws_provider.list_resources()
        assert len(resources) == 4

        vm_res = [r for r in resources if r.type == ResourceType.VM]
        assert len(vm_res) == 1
        assert vm_res[0].id == "i-0123456789abcdef0"
        assert vm_res[0].tags.get("Owner") == "infra"

        orphaned = await mocked_aws_provider.get_orphaned_storage()
        assert len(orphaned) == 1
        assert orphaned[0].id == "vol-orphan-1"
        assert orphaned[0].is_orphaned is True

    @pytest.mark.asyncio
    async def test_aws_get_resource_utilization(self, mocked_aws_provider):
        mocked_aws_provider._cw_client.get_metric_statistics.return_value = {
            "Datapoints": [
                {"Average": 12.4},
                {"Average": 18.6},
            ]
        }

        util = await mocked_aws_provider.get_resource_utilization("i-0123456789abcdef0", 7)
        assert util == 15.5

    @pytest.mark.asyncio
    async def test_aws_get_idle_resources(self, mocked_aws_provider):
        mocked_aws_provider._ec2_client.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-idle-instance",
                            "InstanceType": "t3.medium",
                            "State": {"Name": "running"},
                            "Tags": [],
                        }
                    ]
                }
            ]
        }
        mocked_aws_provider._ec2_client.describe_volumes.return_value = {"Volumes": []}
        mocked_aws_provider._s3_client.list_buckets.return_value = {"Buckets": []}

        mocked_aws_provider._cw_client.get_metric_statistics.return_value = {
            "Datapoints": [{"Average": 1.8}]
        }

        idle = await mocked_aws_provider.get_idle_resources(threshold_pct=5.0)
        assert len(idle) == 1
        assert idle[0].id == "i-idle-instance"
        assert idle[0].status == ResourceStatus.IDLE
