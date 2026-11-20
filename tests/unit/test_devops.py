from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cloudguard.core.models import CloudProviderType
from cloudguard.data.database import close_db
from scripts.generate_mock_data import generate_mock_cost_records, generate_mock_resources
from scripts.seed_database import seed_data


def test_dockerfile_structure() -> None:
    dockerfile_path = Path("Dockerfile")
    assert dockerfile_path.exists()
    content = dockerfile_path.read_text(encoding="utf-8")

    assert "FROM python:3.11-slim AS builder" in content
    assert "FROM python:3.11-slim AS runtime" in content
    assert "EXPOSE 8050" in content
    assert "HEALTHCHECK" in content
    assert 'CMD ["cloudguard", "dashboard", "--host", "0.0.0.0", "--port", "8050"]' in content
    assert "WORKDIR /app" in content


def test_dockerignore_entries() -> None:
    dockerignore_path = Path(".dockerignore")
    assert dockerignore_path.exists()
    content = dockerignore_path.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines() if line.strip()]

    assert ".git" in lines
    assert ".venv" in lines
    assert "__pycache__" in lines
    assert ".env" in lines
    assert "reports/*.pdf" in lines


def test_docker_compose_structure() -> None:
    compose_path = Path("docker-compose.yml")
    assert compose_path.exists()
    content = compose_path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)

    assert "services" in data
    services = data["services"]
    assert "cloudguard" in services
    assert "redis" in services
    assert "db" in services

    assert "8050:8050" in services["cloudguard"]["ports"]
    assert "6379:6379" in services["redis"]["ports"]
    assert "5432:5432" in services["db"]["ports"]

    assert "healthcheck" in services["cloudguard"]
    assert "healthcheck" in services["redis"]
    assert "healthcheck" in services["db"]

    assert "volumes" in data
    assert "pgdata" in data["volumes"]
    assert "redisdata" in data["volumes"]


def test_github_actions_workflow() -> None:
    workflow_path = Path(".github/workflows/ci.yml")
    assert workflow_path.exists()
    content = workflow_path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)

    assert "on" in data or True in data
    assert "jobs" in data
    jobs = data["jobs"]
    assert "lint" in jobs
    assert "test" in jobs
    assert "perf" in jobs
    assert "build" in jobs
    assert "release" in jobs

    assert jobs["test"]["services"]["redis"]["image"] == "redis:7-alpine"


def test_makefile_targets() -> None:
    makefile_path = Path("Makefile")
    assert makefile_path.exists()
    content = makefile_path.read_text(encoding="utf-8")

    expected_targets = [
        "install:",
        "dev:",
        "lint:",
        "format:",
        "test:",
        "test-cov:",
        "benchmark:",
        "docker-build:",
        "docker-up:",
        "docker-down:",
        "clean:",
    ]
    for target in expected_targets:
        assert target in content


def test_deployment_documentation() -> None:
    doc_path = Path("docs/deployment.md")
    assert doc_path.exists()
    content = doc_path.read_text(encoding="utf-8")

    assert "# Deployment Guide" in content
    assert "docker compose up -d" in content
    assert "docker build" in content
    assert "Kubernetes" in content


def test_generate_mock_data_logic() -> None:
    records = generate_mock_cost_records(count=50, provider=CloudProviderType.MOCK, days=10)
    resources = generate_mock_resources(count=20, provider=CloudProviderType.MOCK)

    assert len(records) == 50
    assert len(resources) == 20
    assert all(r.amount > 0 for r in records)
    assert all(res.provider == CloudProviderType.MOCK for res in resources)


@pytest.mark.asyncio
async def test_seed_database_logic(tmp_path: Path) -> None:
    test_db = tmp_path / "test_seed.db"
    db_url = f"sqlite+aiosqlite:///{test_db.as_posix()}"

    try:
        await seed_data(
            database_url=db_url,
            provider_str="mock",
            days=7,
            cost_records_count=30,
            resources_count=10,
        )
        assert test_db.exists()
        assert test_db.stat().st_size > 0
    finally:
        await close_db()
