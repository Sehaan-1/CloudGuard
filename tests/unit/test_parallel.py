from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from cloudguard.core.models import (
    CloudProviderType,
    CloudResource,
    CostRecord,
    ResourceStatus,
    ResourceType,
)
from cloudguard.engine import CostAnalysisEngine
from cloudguard.processing.chunker import Chunker
from cloudguard.processing.parallel import AnalysisResult, ParallelProcessor
from cloudguard.processing.pipeline import (
    AggregateStage,
    AnalyzeStage,
    EnrichStage,
    IngestStage,
    NormalizeStage,
    OutputStage,
    PipelineContext,
    ProcessingPipeline,
    ValidateStage,
    create_default_pipeline,
)


def test_chunker_split_list_basic() -> None:
    data = [1, 2, 3, 4, 5, 6, 7]
    chunks = Chunker.split_list(data, 3)
    assert len(chunks) == 3
    assert chunks[0] == [1, 2, 3]
    assert chunks[1] == [4, 5, 6]
    assert chunks[2] == [7]


def test_chunker_split_list_empty() -> None:
    chunks = Chunker.split_list([], 5)
    assert chunks == []


def test_chunker_split_list_invalid() -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        Chunker.split_list([1, 2], 0)


def test_chunker_stream_chunks() -> None:
    data = range(10)
    streamed = list(Chunker.stream_chunks(data, 4))
    assert len(streamed) == 3
    assert streamed[0] == [0, 1, 2, 3]
    assert streamed[1] == [4, 5, 6, 7]
    assert streamed[2] == [8, 9]


def test_chunker_split_dataframe() -> None:
    df = pd.DataFrame({"a": range(10), "b": range(10, 20)})
    chunks_by_size = Chunker.split_dataframe(df, chunk_size=3)
    assert len(chunks_by_size) == 4
    assert len(chunks_by_size[0]) == 3
    assert len(chunks_by_size[-1]) == 1

    chunks_by_num = Chunker.split_dataframe(df, num_chunks=2)
    assert len(chunks_by_num) == 2
    assert sum(len(c) for c in chunks_by_num) == 10

    empty_df = pd.DataFrame()
    assert Chunker.split_dataframe(empty_df) == []


def test_chunker_stream_dataframe_chunks() -> None:
    df = pd.DataFrame({"x": range(15)})
    streamed = list(Chunker.stream_dataframe_chunks(df, chunk_size=5))
    assert len(streamed) == 3
    for s in streamed:
        assert len(s) == 5


def test_chunker_calculate_optimal_chunks() -> None:
    num_chunks, chunk_size = Chunker.calculate_optimal_chunks(
        100_000, 8, min_chunk_size=100, max_chunk_size=5000
    )
    assert num_chunks > 0
    assert chunk_size <= 5000
    assert chunk_size >= 100

    n, s = Chunker.calculate_optimal_chunks(0, 4)
    assert n == 0
    assert s == 0


def test_parallel_processor_cost_records() -> None:
    base_d = date(2026, 1, 1)
    records = [
        CostRecord(
            id=f"rec-{i}",
            service="Virtual Machines" if i % 2 == 0 else "Object Storage",
            date=base_d + timedelta(days=i % 30),
            amount=50.0 + (i * 2.0) if i != 25 else 5000.0,
            currency="USD",
            provider=CloudProviderType.MOCK,
        )
        for i in range(50)
    ]

    processor = ParallelProcessor(max_workers=2, chunk_size=10)
    result = processor.process_records(records)

    assert isinstance(result, AnalysisResult)
    assert result.total_records == 50
    assert result.processed_records == 50
    assert result.execution_time_seconds >= 0.0
    assert "total_cost" in result.metrics
    assert len(result.anomalies) > 0


def test_parallel_processor_resource_records() -> None:
    resources = [
        CloudResource(
            id=f"vm-{i}",
            name=f"vm-inst-{i}",
            type=ResourceType.VM,
            region="us-east-1",
            provider=CloudProviderType.MOCK,
            tags={"Env": "test"} if i % 2 == 0 else {},
            monthly_cost=100.0,
            utilization_pct=1.0 if i == 0 else 50.0,
            status=ResourceStatus.IDLE if i == 0 else ResourceStatus.RUNNING,
            created_at=datetime.utcnow(),
        )
        for i in range(10)
    ]

    processor = ParallelProcessor(max_workers=2, chunk_size=5)
    result = processor.process_records(resources)

    assert result.total_records == 10
    assert "idle_count" in result.waste_summary
    assert result.waste_summary["idle_count"] >= 1
    assert result.waste_summary["untagged_count"] == 5


def test_parallel_processor_dataframe() -> None:
    df = pd.DataFrame({"val": range(20)})

    def double_val(chunk: pd.DataFrame) -> pd.DataFrame:
        c = chunk.copy()
        c["val"] = c["val"] * 2
        return c

    processor = ParallelProcessor(max_workers=2, chunk_size=5)
    processed_df = processor.process_dataframe(df, double_val)

    assert len(processed_df) == 20
    assert set(processed_df["val"]) == set(range(0, 40, 2))


def test_parallel_processor_map_reduce() -> None:
    data = list(range(1, 21))

    def mapper(chunk: list[int]) -> int:
        return sum(chunk)

    def reducer(mapped_chunks: list[int]) -> int:
        return sum(mapped_chunks)

    processor = ParallelProcessor(max_workers=2, chunk_size=5)
    total = processor.map_reduce(data, mapper, reducer)
    assert total == sum(range(1, 21))


def test_parallel_processor_empty() -> None:
    processor = ParallelProcessor()
    res = processor.process_records([])
    assert res.total_records == 0
    assert res.processed_records == 0


def test_processing_pipeline_stages() -> None:
    raw = [
        {"service": "VM", "date": "2026-01-01", "amount": 100.0, "provider": "mock"},
        {"service": "Storage", "date": "2026-01-02", "amount": 50.0, "provider": "mock"},
        {"service": "VM", "date": "2026-01-03", "amount": -10.0, "provider": "mock"},
    ]

    pipeline = ProcessingPipeline()
    pipeline.add_stage(IngestStage())
    pipeline.add_stage(NormalizeStage())
    pipeline.add_stage(ValidateStage())
    pipeline.add_stage(EnrichStage())
    pipeline.add_stage(AnalyzeStage())
    pipeline.add_stage(AggregateStage())
    pipeline.add_stage(OutputStage())

    ctx = pipeline.run(raw)

    assert ctx.metrics["validated_record_count"] == 2
    assert ctx.metrics["dropped_record_count"] == 1
    assert "day_name" in ctx.df.columns
    assert "cost_tier" in ctx.df.columns
    assert ctx.summary is not None
    assert ctx.summary.total_cost == 150.0
    assert ctx.output is not None
    assert ctx.output.total_records == 2


def test_custom_functional_stage() -> None:
    pipeline = ProcessingPipeline()
    pipeline.add_stage(IngestStage())

    def custom_tagger(ctx: PipelineContext) -> PipelineContext:
        ctx.metrics["custom_metric"] = 42
        return ctx

    pipeline.add_stage(custom_tagger)
    ctx = pipeline.run([{"service": "Test", "amount": 10.0}])
    assert ctx.metrics.get("custom_metric") == 42


def test_create_default_pipeline() -> None:
    pipeline = create_default_pipeline()
    records = [
        CostRecord(
            service="Database",
            date=date(2026, 1, 1),
            amount=200.0,
            currency="USD",
            provider=CloudProviderType.MOCK,
        ),
        CostRecord(
            service="Database",
            date=date(2026, 1, 2),
            amount=210.0,
            currency="USD",
            provider=CloudProviderType.MOCK,
        ),
    ]

    ctx = pipeline.run(records)
    assert ctx.output is not None
    assert ctx.output.total_records == 2
    assert ctx.summary is not None
    assert ctx.summary.total_cost == 410.0


@pytest.mark.asyncio
async def test_engine_analyze_parallel_and_pipeline() -> None:
    engine = CostAnalysisEngine(provider="mock")
    parallel_res = await engine.analyze_parallel()
    assert isinstance(parallel_res, AnalysisResult)
    assert parallel_res.total_records > 0

    ctx = await engine.run_pipeline()
    assert isinstance(ctx, PipelineContext)
    assert ctx.output is not None
    assert ctx.summary is not None
