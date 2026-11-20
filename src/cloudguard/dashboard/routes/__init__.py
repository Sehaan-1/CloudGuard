from __future__ import annotations

from fastapi import APIRouter

from cloudguard.dashboard.routes.anomalies import router as anomalies_router
from cloudguard.dashboard.routes.costs import router as costs_router
from cloudguard.dashboard.routes.recommendations import router as recommendations_router
from cloudguard.dashboard.routes.reports import router as reports_router
from cloudguard.dashboard.routes.resources import router as resources_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(costs_router, prefix="/costs", tags=["Costs"])
api_router.include_router(anomalies_router, prefix="/anomalies", tags=["Anomalies"])
api_router.include_router(resources_router, prefix="/resources", tags=["Resources"])
api_router.include_router(
    recommendations_router, prefix="/recommendations", tags=["Recommendations"]
)
api_router.include_router(reports_router, prefix="/reports", tags=["Reports"])

__all__ = ["api_router"]
