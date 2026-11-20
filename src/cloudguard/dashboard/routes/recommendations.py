from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from cloudguard.core.models import Recommendation
from cloudguard.dashboard.services import dashboard_service

router = APIRouter()


@router.get("", response_model=list[Recommendation])
async def get_recommendations(
    provider: str = Query(default="mock"),
) -> list[Recommendation]:
    return await dashboard_service.get_recommendations(provider=provider)


@router.get("/{recommendation_id}", response_model=Recommendation)
async def get_recommendation_by_id(
    recommendation_id: str,
    provider: str = Query(default="mock"),
) -> Recommendation:
    rec = await dashboard_service.get_recommendation_by_id(recommendation_id, provider=provider)
    if rec:
        return rec
    raise HTTPException(status_code=404, detail="Recommendation not found")
