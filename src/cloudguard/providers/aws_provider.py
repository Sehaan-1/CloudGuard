"""Amazon Web Services (AWS) Cloud Provider implementation.

Integrates with AWS Cost Explorer, EC2, S3, and CloudWatch APIs using boto3.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from cloudguard.core.config import Settings, get_settings
from cloudguard.core.exceptions import (
    AuthenticationError,
    ProviderConnectionError,
    ProviderError,
    RateLimitError,
)
from cloudguard.core.logging import get_logger
from cloudguard.core.models import (
    CloudProviderType,
    CloudResource,
    CostRecord,
    Granularity,
    ResourceStatus,
    ResourceType,
)
from cloudguard.providers.base import CloudProvider

logger = get_logger("providers.aws")

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


class AWSProvider(CloudProvider):
    """Concrete CloudProvider for Amazon Web Services infrastructure."""

    def __init__(
        self,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        region_name: str | None = None,
        aws_session_token: str | None = None,
        settings: Settings | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        cfg = settings or get_settings()
        self.access_key = aws_access_key_id or cfg.aws_access_key_id
        self.secret_key = aws_secret_access_key or cfg.aws_secret_access_key
        self.region_name = region_name or cfg.aws_default_region
        self.session_token = aws_session_token or cfg.aws_session_token

        self._session = None
        self._ce_client = None
        self._ec2_client = None
        self._s3_client = None
        self._cw_client = None

    @property
    def provider_type(self) -> CloudProviderType:
        return CloudProviderType.AWS

    def provider_name(self) -> str:
        return "Amazon Web Services"

    def _ensure_authenticated(self) -> None:
        """Initialize Boto3 session and AWS service clients."""
        if not BOTO3_AVAILABLE:
            raise ProviderError(
                "boto3 package is not installed. Install boto3 to use AWSProvider.",
                provider="aws",
            )

        if self._session is not None:
            return

        try:
            if self.access_key and self.secret_key:
                self._session = boto3.Session(
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    aws_session_token=self.session_token,
                    region_name=self.region_name,
                )
            else:
                self._session = boto3.Session(region_name=self.region_name)

            self._ce_client = self._session.client("ce", region_name="us-east-1")
            self._ec2_client = self._session.client("ec2", region_name=self.region_name)
            self._s3_client = self._session.client("s3", region_name=self.region_name)
            self._cw_client = self._session.client("cloudwatch", region_name=self.region_name)
        except Exception as e:
            logger.error(f"Failed to create AWS session: {e}")
            raise AuthenticationError(f"AWS session creation failed: {e}", provider="aws") from e

    async def test_connection(self) -> bool:
        """Verify AWS credentials using STS get-caller-identity or EC2 describe-regions."""
        try:
            self._ensure_authenticated()
            assert self._session is not None
            sts = self._session.client("sts")
            sts.get_caller_identity()
            return True
        except NoCredentialsError as e:
            raise AuthenticationError("AWS credentials not found.", provider="aws") from e
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("AuthFailure", "InvalidClientTokenId", "SignatureDoesNotMatch"):
                raise AuthenticationError(f"AWS auth failed: {e}", provider="aws") from e
            if code == "RequestLimitExceeded":
                raise RateLimitError("AWS API rate limit exceeded", provider="aws") from e
            raise ProviderConnectionError(f"AWS connection test error: {e}", provider="aws") from e
        except Exception as e:
            logger.warning(f"AWS connection test failed: {e}")
            return False

    async def get_cost_data(
        self,
        start_date: date,
        end_date: date,
        granularity: Granularity = Granularity.DAILY,
    ) -> list[CostRecord]:
        """Fetch cost and usage from AWS Cost Explorer API."""
        self._ensure_authenticated()
        assert self._ce_client is not None

        time_period = {
            "Start": start_date.strftime("%Y-%m-%d"),
            "End": end_date.strftime("%Y-%m-%d"),
        }

        group_by = [
            {"Type": "DIMENSION", "Key": "SERVICE"},
            {"Type": "DIMENSION", "Key": "REGION"},
        ]

        records: list[CostRecord] = []
        next_token: str | None = None

        try:
            while True:
                kwargs: dict[str, Any] = {
                    "TimePeriod": time_period,
                    "Granularity": granularity.value.upper(),
                    "Metrics": ["UnblendedCost"],
                    "GroupBy": group_by,
                }
                if next_token:
                    kwargs["NextPageToken"] = next_token

                response = self._ce_client.get_cost_and_usage(**kwargs)

                for result_by_time in response.get("ResultsByTime", []):
                    time_str = result_by_time.get("TimePeriod", {}).get("Start", "")
                    rec_date = date.fromisoformat(time_str) if time_str else start_date

                    for group in result_by_time.get("Groups", []):
                        keys = group.get("Keys", [])
                        service_name = keys[0] if len(keys) > 0 else "Unknown"
                        region_name = keys[1] if len(keys) > 1 else self.region_name

                        metrics = group.get("Metrics", {})
                        cost_info = metrics.get("UnblendedCost", {})
                        amount = float(cost_info.get("Amount", 0.0))
                        currency = cost_info.get("Unit", "USD")

                        records.append(
                            CostRecord(
                                service=service_name,
                                date=rec_date,
                                amount=round(amount, 2),
                                currency=currency,
                                provider=CloudProviderType.AWS,
                                region=region_name,
                                usage_type=f"{service_name} Usage",
                            )
                        )

                next_token = response.get("NextPageToken")
                if not next_token:
                    break

            return records
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code == "RequestLimitExceeded":
                raise RateLimitError("AWS Cost Explorer throttled request", provider="aws") from e
            raise ProviderError(f"AWS Cost Explorer query failed: {e}", provider="aws") from e
        except Exception as e:
            raise ProviderError(f"Error fetching AWS cost data: {e}", provider="aws") from e

    async def list_resources(
        self,
        resource_types: list[ResourceType | str] | None = None,
    ) -> list[CloudResource]:
        """List active AWS EC2 instances, EBS volumes, and S3 buckets."""
        self._ensure_authenticated()
        assert self._ec2_client is not None
        assert self._s3_client is not None

        resources: list[CloudResource] = []

        try:
            ec2_res = self._ec2_client.describe_instances()
            for reservation in ec2_res.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    inst_id = inst.get("InstanceId", "")
                    tags_list = inst.get("Tags", [])
                    tags_dict = {t.get("Key", ""): t.get("Value", "") for t in tags_list}
                    name = tags_dict.get("Name", inst_id)
                    state = inst.get("State", {}).get("Name", "running")

                    resources.append(
                        CloudResource(
                            id=inst_id,
                            name=name,
                            type=ResourceType.VM,
                            region=self.region_name,
                            provider=CloudProviderType.AWS,
                            tags=tags_dict,
                            monthly_cost=0.0,
                            utilization_pct=0.0,
                            status=ResourceStatus.RUNNING
                            if state == "running"
                            else ResourceStatus.STOPPED,
                            metadata={
                                "instance_type": inst.get("InstanceType", "unknown"),
                                "state": state,
                            },
                        )
                    )

            vols_res = self._ec2_client.describe_volumes()
            for vol in vols_res.get("Volumes", []):
                vol_id = vol.get("VolumeId", "")
                attachments = vol.get("Attachments", [])
                is_attached = len(attachments) > 0
                state = vol.get("State", "available")
                tags_list = vol.get("Tags", [])
                tags_dict = {t.get("Key", ""): t.get("Value", "") for t in tags_list}

                resources.append(
                    CloudResource(
                        id=vol_id,
                        name=tags_dict.get("Name", vol_id),
                        type=ResourceType.STORAGE,
                        region=vol.get("AvailabilityZone", self.region_name),
                        provider=CloudProviderType.AWS,
                        tags=tags_dict,
                        monthly_cost=0.0,
                        utilization_pct=0.0,
                        status=ResourceStatus.RUNNING if is_attached else ResourceStatus.ORPHANED,
                        metadata={
                            "is_attached": is_attached,
                            "size_gb": vol.get("Size", 0),
                            "volume_state": state,
                        },
                    )
                )

            s3_res = self._s3_client.list_buckets()
            for bucket in s3_res.get("Buckets", []):
                b_name = bucket.get("Name", "")
                resources.append(
                    CloudResource(
                        id=f"arn:aws:s3:::{b_name}",
                        name=b_name,
                        type=ResourceType.STORAGE,
                        region="global",
                        provider=CloudProviderType.AWS,
                        tags={},
                        monthly_cost=0.0,
                        utilization_pct=0.0,
                        status=ResourceStatus.RUNNING,
                        created_at=bucket.get("CreationDate"),
                        metadata={"service": "S3"},
                    )
                )
        except ClientError as e:
            raise ProviderError(f"AWS list_resources failed: {e}", provider="aws") from e

        if resource_types:
            type_set = {
                t.value if isinstance(t, ResourceType) else str(t).lower() for t in resource_types
            }
            return [r for r in resources if r.type.value in type_set]

        return resources

    async def get_resource_utilization(
        self,
        resource_id: str,
        period_days: int = 7,
    ) -> float:
        """Query AWS CloudWatch for average EC2 CPUUtilization."""
        self._ensure_authenticated()
        assert self._cw_client is not None

        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=period_days)

            response = self._cw_client.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[{"Name": "InstanceId", "Value": resource_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=86400,
                Statistics=["Average"],
            )

            datapoints = response.get("Datapoints", [])
            if datapoints:
                avg_val = sum(dp.get("Average", 0.0) for dp in datapoints) / len(datapoints)
                return round(avg_val, 2)
            return 0.0
        except Exception as e:
            logger.debug(f"Could not retrieve CloudWatch metrics for {resource_id}: {e}")
            return 0.0

    async def get_idle_resources(
        self,
        threshold_pct: float = 5.0,
        period_days: int = 7,
    ) -> list[CloudResource]:
        """Detect AWS EC2 instances with CPUUtilization < threshold_pct."""
        vms = await self.list_resources([ResourceType.VM])
        idle_vms: list[CloudResource] = []

        for vm in vms:
            util = await self.get_resource_utilization(vm.id, period_days)
            if util < threshold_pct:
                idle_vm = vm.model_copy(
                    update={"utilization_pct": util, "status": ResourceStatus.IDLE}
                )
                idle_vms.append(idle_vm)

        return idle_vms

    async def get_orphaned_storage(
        self,
        unused_days: int = 30,
    ) -> list[CloudResource]:
        """Detect unattached AWS EBS volumes."""
        storage_res = await self.list_resources([ResourceType.STORAGE])
        return [
            r
            for r in storage_res
            if r.metadata.get("is_attached") is False or r.status == ResourceStatus.ORPHANED
        ]
