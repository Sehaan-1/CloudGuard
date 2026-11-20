from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cloudguard.cli.app import app

runner = CliRunner()


def test_cli_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "CloudGuard Version:" in result.output
    assert "1.0.0" in result.output


def test_cli_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "1.0.0" in result.output


def test_cli_analyze_mock_default():
    result = runner.invoke(app, ["analyze", "--provider", "mock"])
    assert result.exit_code == 0
    assert "Cloud Cost Analysis Summary" in result.output
    assert "Service Cost Breakdown" in result.output


def test_cli_analyze_json_output():
    result = runner.invoke(app, ["analyze", "--provider", "mock", "--output", "json"])
    assert result.exit_code == 0
    json_start = result.output.find("{")
    assert json_start != -1
    parsed = json.loads(result.output[json_start:])
    assert "summary" in parsed
    assert "anomalies" in parsed
    assert parsed["summary"]["total_cost"] > 0


def test_cli_analyze_markdown_output():
    result = runner.invoke(app, ["analyze", "--provider", "mock", "--output", "markdown"])
    assert result.exit_code == 0
    assert "CloudGuard Cost Analysis Report" in result.output


def test_cli_analyze_date_filtering():
    result = runner.invoke(
        app,
        [
            "analyze",
            "--provider",
            "mock",
            "--start",
            "2026-07-01",
            "--end",
            "2026-07-31",
        ],
    )
    assert result.exit_code == 0
    assert "2026-07-01" in result.output
    assert "2026-07-31" in result.output


def test_cli_analyze_invalid_dates():
    result = runner.invoke(
        app,
        [
            "analyze",
            "--provider",
            "mock",
            "--start",
            "2026-10-01",
            "--end",
            "2026-01-01",
        ],
    )
    assert result.exit_code != 0
    assert "Start date cannot be after end date" in result.output


def test_cli_analyze_all_providers():
    result = runner.invoke(app, ["analyze", "--provider", "all"])
    assert result.exit_code == 0
    assert "ALL" in result.output or "Cloud Cost Analysis Summary" in result.output


def test_cli_scan_mock_default():
    result = runner.invoke(app, ["scan", "--provider", "mock"])
    assert result.exit_code == 0
    assert "Infrastructure Waste & Audit Summary" in result.output
    assert "FinOps Optimization Recommendations" in result.output


def test_cli_scan_filter_types():
    result = runner.invoke(
        app,
        [
            "scan",
            "--provider",
            "mock",
            "--type",
            "idle-vms,orphaned-storage",
        ],
    )
    assert result.exit_code == 0
    assert "Idle Compute Workloads" in result.output
    assert "Orphaned Storage Volumes & Disks" in result.output


def test_cli_scan_json_output():
    result = runner.invoke(app, ["scan", "--provider", "mock", "--output", "json"])
    assert result.exit_code == 0
    json_start = result.output.find("{")
    assert json_start != -1
    parsed = json.loads(result.output[json_start:])
    assert "scan_result" in parsed
    assert "recommendations" in parsed


def test_cli_scan_tree_output():
    result = runner.invoke(app, ["scan", "--provider", "mock", "--output", "tree"])
    assert result.exit_code == 0
    assert "Infrastructure Waste Tree" in result.output


def test_cli_report_html(tmp_path: Path):
    target = tmp_path / "test_report.html"
    result = runner.invoke(
        app,
        [
            "report",
            "--provider",
            "mock",
            "--format",
            "html",
            "--output",
            str(target),
        ],
    )
    assert result.exit_code == 0
    assert target.exists()
    assert "<html" in target.read_text(encoding="utf-8").lower()


def test_cli_report_json(tmp_path: Path):
    target = tmp_path / "test_report.json"
    result = runner.invoke(
        app,
        [
            "report",
            "--provider",
            "mock",
            "--format",
            "json",
            "--output",
            str(target),
        ],
    )
    assert result.exit_code == 0
    assert target.exists()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "summary" in data


def test_cli_report_markdown(tmp_path: Path):
    target = tmp_path / "test_report.md"
    result = runner.invoke(
        app,
        [
            "report",
            "--provider",
            "mock",
            "--format",
            "markdown",
            "--output",
            str(target),
        ],
    )
    assert result.exit_code == 0
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "Financial Summary" in content


def test_cli_config_show():
    result = runner.invoke(app, ["config", "--show"])
    assert result.exit_code == 0
    assert "CloudGuard Configuration Settings" in result.output
    assert "default_provider" in result.output


def test_cli_config_get():
    result = runner.invoke(app, ["config", "--get", "default_provider"])
    assert result.exit_code == 0
    assert "default_provider = mock" in result.output


def test_cli_config_test_provider():
    result = runner.invoke(app, ["config", "--test", "--provider", "mock"])
    assert result.exit_code == 0
    assert "successful" in result.output


def test_cli_config_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["config", "--set", "azure.subscription_id=sub-test-999"])
    assert result.exit_code == 0
    env_file = tmp_path / ".env"
    assert env_file.exists()
    assert "AZURE_SUBSCRIPTION_ID=sub-test-999" in env_file.read_text(encoding="utf-8")


def test_cli_config_invalid_set():
    result = runner.invoke(app, ["config", "--set", "invalid_format_no_equals"])
    assert result.exit_code != 0
    assert "Invalid syntax" in result.output


def test_cli_config_unknown_key():
    result = runner.invoke(app, ["config", "--get", "totally_nonexistent_key_123"])
    assert result.exit_code != 0
    assert "Unknown configuration key" in result.output


def test_cli_dashboard_mocked(monkeypatch: pytest.MonkeyPatch):
    from unittest.mock import MagicMock

    mock_uvicorn = MagicMock()
    monkeypatch.setattr("uvicorn.run", mock_uvicorn.run)
    result = runner.invoke(app, ["dashboard", "--host", "127.0.0.1", "--port", "9000"])
    assert result.exit_code == 0
    assert "Launching CloudGuard Observability Dashboard" in result.output


def test_cli_report_unsupported_format():
    result = runner.invoke(app, ["report", "--provider", "mock", "--format", "unsupported_xyz"])
    assert result.exit_code != 0
    assert "Unsupported format" in result.output


def test_cli_scan_all_types():
    result = runner.invoke(
        app,
        [
            "scan",
            "--provider",
            "mock",
            "--type",
            "underutilized-vms,untagged-resources",
        ],
    )
    assert result.exit_code == 0
    assert "Underutilized Instances" in result.output or "Untagged Assets" in result.output
