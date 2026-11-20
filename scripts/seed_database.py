from __future__ import annotations

import argparse
import asyncio

from cloudguard.analysis.anomaly_detector import CompositeDetector
from cloudguard.analysis.iqr_detector import IQRDetector
from cloudguard.analysis.rolling_detector import RollingWindowDetector
from cloudguard.analysis.zscore_detector import ZScoreDetector
from cloudguard.core.config import get_settings
from cloudguard.core.models import (
    CloudProviderType,
    ScanResult,
)
from cloudguard.data.database import close_db, get_engine, get_session_factory, init_db
from cloudguard.data.repository import (
    AnomalyRepository,
    CostRepository,
    RecommendationRepository,
    ResourceRepository,
    ScanHistoryRepository,
)
from cloudguard.recommendations.engine import RecommendationEngine

try:
    from scripts.generate_mock_data import generate_mock_cost_records, generate_mock_resources
except ImportError:
    from generate_mock_data import generate_mock_cost_records, generate_mock_resources


async def seed_data(
    database_url: str | None = None,
    provider_str: str = "mock",
    days: int = 30,
    cost_records_count: int = 500,
    resources_count: int = 100,
) -> None:
    settings = get_settings()
    db_url = database_url or settings.database_url

    if db_url.startswith("sqlite") and not db_url.startswith("sqlite+aiosqlite"):
        db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://")

    print(f"Connecting to database: {db_url}")
    await init_db(db_url)
    engine = get_engine(db_url)

    provider_enum = CloudProviderType(provider_str.lower())
    records = generate_mock_cost_records(
        count=cost_records_count, provider=provider_enum, days=days
    )
    resources = generate_mock_resources(count=resources_count, provider=provider_enum)

    detector = CompositeDetector(
        strategies=[
            ZScoreDetector(threshold=2.5),
            IQRDetector(multiplier=1.5),
            RollingWindowDetector(window=14, std_dev_multiplier=2.5),
        ],
        min_votes=1,
    )
    anomalies = detector.detect(records)

    idle = [r for r in resources if r.is_idle]
    orphaned = [r for r in resources if r.is_orphaned]
    underutilized = [r for r in resources if 0 < r.utilization_pct < 10.0 and not r.is_idle]
    untagged = [r for r in resources if not r.tags]

    scan_result = ScanResult(
        provider=provider_enum,
        idle_resources=idle,
        orphaned_storage=orphaned,
        underutilized_vms=underutilized,
        untagged_resources=untagged,
        total_resources_scanned=len(resources),
        total_waste_monthly=sum(r.monthly_cost for r in idle + orphaned),
    )

    rec_engine = RecommendationEngine()
    recommendations = rec_engine.analyze(scan_result, records)

    session_factory = get_session_factory(engine)
    async with session_factory() as session:
        cost_repo = CostRepository(session)
        await cost_repo.save_cost_records(records)

        res_repo = ResourceRepository(session)
        await res_repo.save_resources(resources)

        anomaly_repo = AnomalyRepository(session)
        await anomaly_repo.save_anomalies(anomalies)

        rec_repo = RecommendationRepository(session)
        await rec_repo.save_recommendations(recommendations)

        scan_repo = ScanHistoryRepository(session)
        await scan_repo.save_scan_result(scan_result)

    await close_db()

    print("Successfully seeded database with:")
    print(f"  - {len(records):,} Cost Records")
    print(f"  - {len(resources):,} Cloud Resources")
    print(f"  - {len(anomalies):,} Anomalies")
    print(f"  - {len(recommendations):,} Recommendations")
    print("  - 1 Infrastructure Scan Result")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed CloudGuard database with realistic records")
    parser.add_argument("--database-url", type=str, default=None, help="SQLAlchemy database URL")
    parser.add_argument(
        "--provider",
        type=str,
        default="mock",
        choices=["azure", "aws", "mock"],
        help="Cloud provider",
    )
    parser.add_argument("--days", type=int, default=30, help="Days of historical cost data")
    parser.add_argument("--records", type=int, default=500, help="Number of cost records")
    parser.add_argument("--resources", type=int, default=100, help="Number of cloud resources")

    args = parser.parse_args()
    asyncio.run(
        seed_data(
            database_url=args.database_url,
            provider_str=args.provider,
            days=args.days,
            cost_records_count=args.records,
            resources_count=args.resources,
        )
    )


if __name__ == "__main__":
    main()
