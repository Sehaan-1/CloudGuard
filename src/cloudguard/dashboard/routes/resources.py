from __future__ import annotations

from fastapi import APIRouter, Query

from cloudguard.core.models import CloudResource, ScanResult
from cloudguard.dashboard.services import dashboard_service

router = APIRouter()


@router.get("/scan", response_model=ScanResult)
async def get_scan_result(
    provider: str = Query(default="mock"),
    idle_threshold: float | None = Query(default=None),
    orphaned_days: int | None = Query(default=None),
    underutilized_threshold: float | None = Query(default=None),
) -> ScanResult:
    return await dashboard_service.get_scan_result(
        provider=provider,
        idle_threshold=idle_threshold,
        orphaned_days=orphaned_days,
        underutilized_threshold=underutilized_threshold,
    )


@router.get("/idle", response_model=list[CloudResource])
async def get_idle_resources(
    provider: str = Query(default="mock"),
    idle_threshold: float | None = Query(default=None),
) -> list[CloudResource]:
    res = await dashboard_service.get_scan_result(provider=provider, idle_threshold=idle_threshold)
    return res.idle_resources


@router.get("/orphaned", response_model=list[CloudResource])
async def get_orphaned_resources(
    provider: str = Query(default="mock"),
    orphaned_days: int | None = Query(default=None),
) -> list[CloudResource]:
    res = await dashboard_service.get_scan_result(provider=provider, orphaned_days=orphaned_days)
    return res.orphaned_storage


@router.get("/underutilized", response_model=list[CloudResource])
async def get_underutilized_resources(
    provider: str = Query(default="mock"),
    underutilized_threshold: float | None = Query(default=None),
) -> list[CloudResource]:
    res = await dashboard_service.get_scan_result(
        provider=provider, underutilized_threshold=underutilized_threshold
    )
    return res.underutilized_vms


@router.get("/untagged", response_model=list[CloudResource])
async def get_untagged_resources(
    provider: str = Query(default="mock"),
) -> list[CloudResource]:
    res = await dashboard_service.get_scan_result(provider=provider)
    return res.untagged_resources


@router.get("/utilization", response_model=list[CloudResource])
async def get_resource_utilization(
    provider: str = Query(default="mock"),
) -> list[CloudResource]:
    res = await dashboard_service.get_scan_result(provider=provider)
    combined: list[CloudResource] = []
    combined.extend(res.idle_resources)
    combined.extend(res.orphaned_storage)
    combined.extend(res.underutilized_vms)
    combined.extend(res.untagged_resources)
    return combined
