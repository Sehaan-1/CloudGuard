from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from cloudguard.core.models import CostRecord, CostSummary, Granularity
from cloudguard.dashboard.services import dashboard_service

router = APIRouter()


@router.get("/summary", response_model=CostSummary)
async def get_cost_summary(
    provider: str = Query(default="mock"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> CostSummary:
    return await dashboard_service.get_cost_summary(
        provider=provider, start_date=start_date, end_date=end_date
    )


@router.get("/by-service", response_model=dict[str, float])
async def get_cost_by_service(
    provider: str = Query(default="mock"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> dict[str, float]:
    return await dashboard_service.get_cost_by_service(
        provider=provider, start_date=start_date, end_date=end_date
    )


@router.get("/trend", response_model=dict[str, float])
async def get_cost_trend(
    provider: str = Query(default="mock"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    granularity: str = Query(default="daily"),
) -> dict[str, float]:
    try:
        gran_enum = Granularity(granularity.lower())
    except ValueError:
        gran_enum = Granularity.DAILY

    return await dashboard_service.get_cost_trend(
        provider=provider, start_date=start_date, end_date=end_date, granularity=gran_enum
    )


@router.get("/records", response_model=list[CostRecord])
@router.get("", response_model=list[CostRecord])
async def get_cost_records(
    provider: str = Query(default="mock"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    granularity: str = Query(default="daily"),
) -> list[CostRecord]:
    try:
        gran_enum = Granularity(granularity.lower())
    except ValueError:
        gran_enum = Granularity.DAILY

    return await dashboard_service.get_cost_records(
        provider=provider, start_date=start_date, end_date=end_date, granularity=gran_enum
    )
