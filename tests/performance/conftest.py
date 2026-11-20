from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from cloudguard.core.models import CloudProviderType

SERVICES = [
    "Virtual Machines",
    "Managed Disks",
    "Object Storage",
    "Relational Database",
    "Container Service",
    "Load Balancers",
    "Serverless Functions",
]

REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1", "eastus", "westeurope"]


@pytest.fixture
def sample_100k_dataframe() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    count = 100_000
    base_date = date(2026, 1, 1)

    service_indices = rng.integers(0, len(SERVICES), size=count)
    region_indices = rng.integers(0, len(REGIONS), size=count)
    day_offsets = rng.integers(0, 90, size=count)
    amounts = np.round(rng.uniform(5.0, 500.0, size=count), 2)

    services = [SERVICES[i] for i in service_indices]
    regions = [REGIONS[i] for i in region_indices]
    dates = [base_date + timedelta(days=int(d)) for d in day_offsets]
    ids = [f"bench-{i:08d}" for i in range(count)]
    res_ids = [f"res-{i % 1000:04d}" for i in range(count)]

    return pd.DataFrame(
        {
            "id": ids,
            "resource_id": res_ids,
            "service": services,
            "date": dates,
            "amount": amounts,
            "currency": ["USD"] * count,
            "provider": [CloudProviderType.MOCK.value] * count,
            "region": regions,
            "usage_type": ["Compute/Storage Consumption"] * count,
            "tags": [{}] * count,
        }
    )
