from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cloudguard.core.models import (
    CloudProviderType,
    CloudResource,
    CostRecord,
    ResourceStatus,
    ResourceType,
)

SERVICES_BY_PROVIDER = {
    CloudProviderType.AZURE: [
        "Virtual Machines",
        "Managed Disks",
        "Blob Storage",
        "Azure SQL Database",
        "Azure Kubernetes Service",
        "Application Gateway",
        "Azure Functions",
    ],
    CloudProviderType.AWS: [
        "Amazon Elastic Compute Cloud - Compute",
        "Amazon Elastic Block Store",
        "Amazon Simple Storage Service",
        "Amazon Relational Database Service",
        "Amazon Elastic Kubernetes Service",
        "Elastic Load Balancing",
        "AWS Lambda",
    ],
    CloudProviderType.MOCK: [
        "Virtual Machines",
        "Managed Disks",
        "Object Storage",
        "Relational Database",
        "Container Service",
        "Load Balancers",
        "Serverless Functions",
    ],
}

REGIONS_BY_PROVIDER = {
    CloudProviderType.AZURE: ["eastus", "westeurope", "southeastasia", "centralus", "northeurope"],
    CloudProviderType.AWS: ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1", "sa-east-1"],
    CloudProviderType.MOCK: ["us-east-1", "us-west-2", "eu-west-1", "eastus", "westeurope"],
}


def generate_mock_resources(
    count: int, provider: CloudProviderType, seed: int = 42
) -> list[CloudResource]:
    rng = np.random.default_rng(seed)
    resources: list[CloudResource] = []
    types = list(ResourceType)
    regions = REGIONS_BY_PROVIDER.get(provider, REGIONS_BY_PROVIDER[CloudProviderType.MOCK])

    for i in range(count):
        rtype = types[int(rng.integers(0, len(types)))]
        reg = regions[int(rng.integers(0, len(regions)))]
        is_idle = bool(rng.random() < 0.15)
        is_orphaned = bool(rtype == ResourceType.STORAGE and rng.random() < 0.2)
        utilization = float(rng.uniform(0.5, 4.0)) if is_idle else float(rng.uniform(15.0, 95.0))
        cost = float(np.round(rng.uniform(15.0, 600.0), 2))
        created_dt = datetime.utcnow() - timedelta(days=int(rng.integers(30, 365)))

        tags = {}
        if rng.random() > 0.15:
            tags = {
                "Environment": "production" if rng.random() > 0.4 else "staging",
                "Owner": f"team-{int(rng.integers(1, 6))}",
            }

        resources.append(
            CloudResource(
                id=f"res-{provider.value}-{i:05d}",
                cloud_id=f"cloud-id-{provider.value}-{i:05d}",
                name=f"{provider.value}-{rtype.value}-{i:04d}",
                type=rtype,
                region=reg,
                provider=provider,
                status=ResourceStatus.STOPPED if is_idle else ResourceStatus.RUNNING,
                tags=tags,
                monthly_cost=cost,
                utilization_pct=utilization,
                is_idle=is_idle,
                is_orphaned=is_orphaned,
                created_at=created_dt,
            )
        )
    return resources


def generate_mock_cost_records(
    count: int,
    provider: CloudProviderType,
    days: int = 30,
    seed: int = 42,
) -> list[CostRecord]:
    rng = np.random.default_rng(seed)
    services = SERVICES_BY_PROVIDER.get(provider, SERVICES_BY_PROVIDER[CloudProviderType.MOCK])
    regions = REGIONS_BY_PROVIDER.get(provider, REGIONS_BY_PROVIDER[CloudProviderType.MOCK])
    base_date = date.today() - timedelta(days=days)

    records: list[CostRecord] = []
    for i in range(count):
        svc = services[int(rng.integers(0, len(services)))]
        reg = regions[int(rng.integers(0, len(regions)))]
        day_offset = int(rng.integers(0, max(1, days)))
        rec_date = base_date + timedelta(days=day_offset)
        amount = float(np.round(rng.uniform(2.0, 450.0), 2))

        records.append(
            CostRecord(
                id=f"cost-{provider.value}-{i:07d}",
                resource_id=f"res-{provider.value}-{i % 1000:05d}",
                service=svc,
                date=rec_date,
                amount=amount,
                currency="USD",
                provider=provider,
                region=reg,
                tags={},
            )
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic multi-cloud dataset")
    parser.add_argument("--records", type=int, default=10000, help="Number of cost records")
    parser.add_argument("--resources", type=int, default=500, help="Number of cloud resources")
    parser.add_argument("--days", type=int, default=30, help="History timeframe in days")
    parser.add_argument(
        "--provider",
        type=str,
        default="mock",
        choices=["azure", "aws", "mock"],
        help="Cloud provider",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output", type=str, default=None, help="Output file path (.json or .csv)")

    args = parser.parse_args()
    provider_enum = CloudProviderType(args.provider.lower())

    records = generate_mock_cost_records(
        count=args.records,
        provider=provider_enum,
        days=args.days,
        seed=args.seed,
    )
    resources = generate_mock_resources(
        count=args.resources,
        provider=provider_enum,
        seed=args.seed,
    )

    total_cost = sum(r.amount for r in records)
    print(f"Generated {len(records):,} cost records across {args.days} days.")
    print(f"Generated {len(resources):,} cloud resources.")
    print(f"Total simulated spend: ${total_cost:,.2f}")

    if args.output:
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        if out_p.suffix.lower() == ".csv":
            df = pd.DataFrame([r.model_dump(mode="json") for r in records])
            df.to_csv(out_p, index=False)
            print(f"Saved records to CSV: {out_p}")
        else:
            payload: dict[str, Any] = {
                "provider": provider_enum.value,
                "generated_at": date.today().isoformat(),
                "cost_records_count": len(records),
                "resources_count": len(resources),
                "total_spend": round(total_cost, 2),
                "records": [r.model_dump(mode="json") for r in records],
                "resources": [r.model_dump(mode="json") for r in resources],
            }
            out_p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"Saved dataset to JSON: {out_p}")


if __name__ == "__main__":
    main()
