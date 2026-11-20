from __future__ import annotations

import argparse
import os
import time
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from cloudguard.core.models import CloudProviderType, CostRecord
from cloudguard.processing.parallel import ParallelProcessor
from cloudguard.processing.pipeline import create_default_pipeline

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


def generate_synthetic_dataframe(count: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
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


def generate_synthetic_records(count: int, seed: int = 42) -> list[CostRecord]:
    df = generate_synthetic_dataframe(count, seed)
    records: list[CostRecord] = []
    for row in df.itertuples(index=False):
        records.append(
            CostRecord(
                id=row.id,
                resource_id=row.resource_id,
                service=row.service,
                date=row.date,
                amount=row.amount,
                currency=row.currency,
                provider=CloudProviderType(row.provider),
                region=row.region,
            )
        )
    return records


def run_benchmark(counts: list[int], max_workers: int | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for count in counts:
        print(f"\n[BENCHMARK] Generating {count:,} synthetic records...")
        gen_start = time.perf_counter()
        df = generate_synthetic_dataframe(count)
        gen_time = time.perf_counter() - gen_start
        print(f"[BENCHMARK] Generation completed in {gen_time:.3f}s")

        processor = ParallelProcessor(max_workers=max_workers)
        pipeline = create_default_pipeline(processor=processor)

        print(f"[BENCHMARK] Running full analysis pipeline on {count:,} records...")
        t0 = time.perf_counter()
        context = pipeline.run(df)
        elapsed = time.perf_counter() - t0

        records_per_sec = count / elapsed if elapsed > 0 else 0.0

        res_dict = {
            "record_count": count,
            "wall_clock_seconds": round(elapsed, 4),
            "throughput_rec_sec": round(records_per_sec, 2),
            "target_met": elapsed < (5.0 if count <= 100_000 else 25.0),
            "stage_timings": {k: round(v, 4) for k, v in context.stage_timings.items()},
            "anomalies_found": len(context.anomalies),
            "total_cost": context.metrics.get("total_cost", 0.0),
        }
        results.append(res_dict)

        print(
            f"[BENCHMARK] Completed {count:,} records in {elapsed:.3f}s ({records_per_sec:,.0f} records/sec)"
        )
        print(f"            Target <5s: {'PASS' if res_dict['target_met'] else 'FAIL'}")

    return results


def print_markdown_table(results: list[dict[str, Any]]) -> None:
    print("\n\n### Benchmark Results Summary\n")
    print(
        "| Record Count | Wall-Clock Time (s) | Throughput (rec/s) | Target (<5s for 100k) | Anomalies Detected | Total Cost ($) |"
    )
    print(
        "|-------------:|--------------------:|-------------------:|:---------------------:|-------------------:|---------------:|"
    )
    for r in results:
        target_str = "PASSED" if r["target_met"] else "FAILED"
        print(
            f"| {r['record_count']:,} | {r['wall_clock_seconds']:.4f}s | {r['throughput_rec_sec']:,.0f} | {target_str} | {r['anomalies_found']} | ${r['total_cost']:,.2f} |"
        )

    print("\n#### Per-Stage Timing Breakdown\n")
    for r in results:
        print(f"**Dataset: {r['record_count']:,} records ({r['wall_clock_seconds']:.4f}s total)**")
        print("| Pipeline Stage | Time (s) | % of Total |")
        print("|----------------|---------:|-----------:|")
        total_t = r["wall_clock_seconds"]
        for stage, duration in r["stage_timings"].items():
            pct = (duration / total_t * 100) if total_t > 0 else 0.0
            print(f"| {stage} | {duration:.4f}s | {pct:.1f}% |")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="CloudGuard Parallel Processing Benchmark")
    parser.add_argument(
        "--counts",
        nargs="+",
        type=int,
        default=[10_000, 50_000, 100_000, 500_000],
        help="Record counts to benchmark",
    )
    parser.add_argument(
        "--records",
        type=int,
        default=None,
        help="Single record count to benchmark (alias for --counts)",
    )
    parser.add_argument(
        "--workers", type=int, default=None, help="Worker count for ParallelProcessor"
    )
    args = parser.parse_args()

    counts = [args.records] if args.records is not None else args.counts

    print("=" * 60)
    print("CloudGuard FinOps Parallel Processing Performance Benchmark")
    print("=" * 60)
    print(f"CPU Cores: {os.cpu_count()}")
    print(f"Test Sizes: {counts}")

    results = run_benchmark(counts, max_workers=args.workers)
    print_markdown_table(results)


if __name__ == "__main__":
    main()
