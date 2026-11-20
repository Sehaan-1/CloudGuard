from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.wsgi import WSGIMiddleware

from cloudguard.dashboard.dash_app import create_dash_app
from cloudguard.dashboard.routes import api_router


def create_app() -> FastAPI:
    server = FastAPI(
        title="CloudGuard FinOps & Observability API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    server.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @server.get("/api/v1/health", tags=["System"])
    @server.get("/health", tags=["System"])
    async def health() -> dict[str, str]:
        return {
            "status": "healthy",
            "service": "cloudguard-dashboard",
            "version": "1.0.0",
        }

    server.include_router(api_router)

    dash_app = create_dash_app(requests_pathname_prefix="/")
    server.mount("/", WSGIMiddleware(dash_app.server))

    return server


app = create_app()
