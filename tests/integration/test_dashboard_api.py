from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from cloudguard.dashboard.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoints(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "cloudguard-dashboard"

    res_root = client.get("/health")
    assert res_root.status_code == 200
    assert res_root.json()["status"] == "healthy"


def test_cost_summary_endpoint(client):
    res = client.get("/api/v1/costs/summary?provider=mock")
    assert res.status_code == 200
    data = res.json()
    assert "total_cost" in data
    assert "currency" in data
    assert "cost_by_service" in data
    assert data["total_cost"] > 0


def test_cost_by_service_endpoint(client):
    res = client.get("/api/v1/costs/by-service?provider=mock")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, dict)
    assert len(data) > 0


def test_cost_trend_endpoint(client):
    res = client.get("/api/v1/costs/trend?provider=mock&granularity=daily")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, dict)
    assert len(data) > 0


def test_cost_records_endpoint(client):
    res = client.get("/api/v1/costs/records?provider=mock")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "amount" in data[0]
    assert "service" in data[0]


def test_anomalies_endpoints(client):
    res = client.get("/api/v1/anomalies?provider=mock")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)

    if data:
        first_id = data[0]["id"]
        res_single = client.get(f"/api/v1/anomalies/{first_id}?provider=mock")
        assert res_single.status_code == 200
        assert res_single.json()["id"] == first_id

    res_404 = client.get("/api/v1/anomalies/non-existent-id?provider=mock")
    assert res_404.status_code == 404


def test_anomaly_endpoint_with_filters(client):
    res_filtered = client.get(
        "/api/v1/anomalies?provider=mock&start_date=2026-08-01&end_date=2026-08-20&method=composite&threshold=2.5&severity=high"
    )
    assert res_filtered.status_code == 200
    data = res_filtered.json()
    assert isinstance(data, list)


def test_resources_endpoints(client):
    res_scan = client.get("/api/v1/resources/scan?provider=mock")
    assert res_scan.status_code == 200
    scan_data = res_scan.json()
    assert "total_resources_scanned" in scan_data
    assert "total_waste_monthly" in scan_data

    res_idle = client.get("/api/v1/resources/idle?provider=mock")
    assert res_idle.status_code == 200
    assert isinstance(res_idle.json(), list)

    res_orphaned = client.get("/api/v1/resources/orphaned?provider=mock")
    assert res_orphaned.status_code == 200
    assert isinstance(res_orphaned.json(), list)

    res_under = client.get("/api/v1/resources/underutilized?provider=mock")
    assert res_under.status_code == 200
    assert isinstance(res_under.json(), list)

    res_untagged = client.get("/api/v1/resources/untagged?provider=mock")
    assert res_untagged.status_code == 200
    assert isinstance(res_untagged.json(), list)

    res_util = client.get("/api/v1/resources/utilization?provider=mock")
    assert res_util.status_code == 200
    assert isinstance(res_util.json(), list)


def test_recommendations_endpoints(client):
    res = client.get("/api/v1/recommendations?provider=mock")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) > 0

    first_id = data[0]["id"]
    res_single = client.get(f"/api/v1/recommendations/{first_id}?provider=mock")
    assert res_single.status_code == 200
    assert res_single.json()["id"] == first_id

    res_404 = client.get("/api/v1/recommendations/non-existent-id?provider=mock")
    assert res_404.status_code == 404


def test_report_generation_and_download(client):
    payload = {
        "provider": "mock",
        "title": "Integration Test Report",
        "format": "html",
    }
    res_gen = client.post("/api/v1/reports/generate", json=payload)
    assert res_gen.status_code == 200
    gen_data = res_gen.json()
    assert gen_data["status"] == "generated"
    assert "id" in gen_data
    report_id = gen_data["id"]

    res_dl = client.get(f"/api/v1/reports/{report_id}/download")
    assert res_dl.status_code == 200
    assert "html" in res_dl.headers.get("content-type", "")

    res_missing = client.get("/api/v1/reports/missing-report-id/download")
    assert res_missing.status_code == 404


def test_dash_ui_mounted(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
