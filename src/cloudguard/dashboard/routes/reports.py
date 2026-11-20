from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from cloudguard.dashboard.services import dashboard_service

router = APIRouter()

_reports_registry: dict[str, Path] = {}


class ReportGenerateRequest(BaseModel):
    provider: str = Field(default="mock")
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None)
    title: str = Field(default="CloudGuard FinOps Executive Report")
    format: str = Field(default="pdf")


class ReportGenerateResponse(BaseModel):
    id: str
    status: str
    filename: str
    format: str


@router.post("/generate", response_model=ReportGenerateResponse)
async def generate_report(req: ReportGenerateRequest) -> ReportGenerateResponse:
    report_id, file_path = await dashboard_service.generate_report(
        provider=req.provider,
        start_date=req.start_date,
        end_date=req.end_date,
        title=req.title,
        fmt=req.format,
    )
    _reports_registry[report_id] = file_path

    return ReportGenerateResponse(
        id=report_id,
        status="generated",
        filename=file_path.name,
        format=req.format.lower(),
    )


@router.get("/{report_id}/download")
async def download_report(report_id: str) -> FileResponse:
    if report_id not in _reports_registry:
        reports_dir = Path("./reports")
        candidates = list(reports_dir.glob(f"*{report_id}*"))
        if candidates:
            file_path = candidates[0]
            _reports_registry[report_id] = file_path
        else:
            raise HTTPException(status_code=404, detail="Report not found")
    else:
        file_path = _reports_registry[report_id]

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found on disk")

    media_type = "application/pdf"
    if file_path.suffix == ".html":
        media_type = "text/html"
    elif file_path.suffix == ".json":
        media_type = "application/json"

    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type=media_type,
    )
