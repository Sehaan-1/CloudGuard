from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import TypeVar

import numpy as np
import pandas as pd

T = TypeVar("T")


class Chunker:
    @staticmethod
    def split_list(data: Sequence[T], chunk_size: int) -> list[list[T]]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        if not data:
            return []
        return [list(data[i : i + chunk_size]) for i in range(0, len(data), chunk_size)]

    @staticmethod
    def stream_chunks(data: Iterable[T], chunk_size: int) -> Iterator[list[T]]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        chunk: list[T] = []
        for item in data:
            chunk.append(item)
            if len(chunk) == chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk

    @staticmethod
    def split_dataframe(
        df: pd.DataFrame,
        num_chunks: int | None = None,
        chunk_size: int | None = None,
    ) -> list[pd.DataFrame]:
        if df.empty:
            return []

        total_rows = len(df)

        if chunk_size is not None and chunk_size > 0:
            return [df.iloc[i : i + chunk_size].copy() for i in range(0, total_rows, chunk_size)]

        if num_chunks is not None and num_chunks > 0:
            actual_chunks = min(num_chunks, total_rows)
            split_indices = np.array_split(np.arange(total_rows), actual_chunks)
            return [df.iloc[idx].copy() for idx in split_indices if len(idx) > 0]

        default_size = max(1, total_rows // 4)
        return [df.iloc[i : i + default_size].copy() for i in range(0, total_rows, default_size)]

    @staticmethod
    def stream_dataframe_chunks(
        df: pd.DataFrame,
        chunk_size: int = 1000,
    ) -> Iterator[pd.DataFrame]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")
        total_rows = len(df)
        for i in range(0, total_rows, chunk_size):
            yield df.iloc[i : i + chunk_size].copy()

    @staticmethod
    def calculate_optimal_chunks(
        total_records: int,
        num_workers: int,
        min_chunk_size: int = 100,
        max_chunk_size: int = 5000,
    ) -> tuple[int, int]:
        if total_records <= 0:
            return 0, 0
        if num_workers <= 0:
            num_workers = 1

        target_chunk_size = max(min_chunk_size, total_records // (num_workers * 2))
        target_chunk_size = min(target_chunk_size, max_chunk_size)
        target_chunk_size = max(1, min(target_chunk_size, total_records))

        num_chunks = (total_records + target_chunk_size - 1) // target_chunk_size
        return num_chunks, target_chunk_size
