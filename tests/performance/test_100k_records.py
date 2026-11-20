from __future__ import annotations

import time

import pandas as pd

from cloudguard.processing.parallel import ParallelProcessor
from cloudguard.processing.pipeline import create_default_pipeline


def test_analyze_100k_records_under_5_seconds(sample_100k_dataframe: pd.DataFrame) -> None:
    df = sample_100k_dataframe
    assert len(df) == 100_000

    processor = ParallelProcessor()
    pipeline = create_default_pipeline(processor=processor)

    start_time = time.perf_counter()
    context = pipeline.run(df)
    elapsed = time.perf_counter() - start_time

    assert elapsed < 5.0, f"Processing 100k records took {elapsed:.3f}s, exceeding 5.0s limit"
    assert context.output is not None
    assert context.output.total_records == 100_000
    assert context.output.processed_records == 100_000
    assert context.summary is not None
    assert context.summary.total_cost > 0.0
    assert len(context.metrics.get("top_services", [])) > 0


def test_parallel_processor_100k_records_direct(sample_100k_dataframe: pd.DataFrame) -> None:
    df = sample_100k_dataframe
    processor = ParallelProcessor()

    start_time = time.perf_counter()
    result = processor.process_records(df)
    elapsed = time.perf_counter() - start_time

    assert elapsed < 5.0, f"Parallel processor direct run took {elapsed:.3f}s, exceeding 5.0s limit"
    assert result.total_records == 100_000
    assert result.processed_records == 100_000
    assert "total_cost" in result.metrics
