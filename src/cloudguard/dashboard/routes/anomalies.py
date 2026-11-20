from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from cloudguard.core.models import AnomalyResult
from cloudguard.dashboard.services import dashboard_service

router = APIRouter()


@router.get("", response_model=list[AnomalyResult])
async def get_anomalies(
    provider: str = Query(default="mock"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    method: str | None = Query(default=None),
    threshold: float | None = Query(default=None),
    severity: str | None = Query(default=None),
) -> list[AnomalyResult]:
    return await dashboard_service.get_anomalies(
        provider=provider,
        start_date=start_date,
        end_date=end_date,
        method=method,
        threshold=threshold,
        severity=severity,
    )


@router.get("/{anomaly_id}", response_model=AnomalyResult)
async def get_anomaly_by_id(
    anomaly_id: str,
    provider: str = Query(default="mock"),
) -> AnomalyResult:
    anomaly = await dashboard_service.get_anomaly_by_id(anomaly_id, provider=provider)
    if anomaly:
        return anomaly
    raise HTTPException(status_code=404, detail="Anomaly not found")
