from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_e2e_cli_version():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, "-m", "cloudguard.cli", "version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert "1.0.0" in result.stdout


def test_e2e_cli_analyze_mock():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cloudguard.cli",
            "analyze",
            "--provider",
            "mock",
            "--start",
            "2026-08-01",
            "--end",
            "2026-08-20",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert "Cloud Cost Analysis Summary" in result.stdout
    assert "Virtual Machines" in result.stdout


def test_e2e_cli_scan_mock():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cloudguard.cli",
            "scan",
            "--provider",
            "mock",
            "--type",
            "idle-vms",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert "Infrastructure Waste & Audit Summary" in result.stdout


def test_e2e_cli_report_generation(tmp_path: Path):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    target = tmp_path / "e2e_report.pdf"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cloudguard.cli",
            "report",
            "--provider",
            "mock",
            "--format",
            "pdf",
            "--output",
            str(target),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert target.exists()
    assert target.stat().st_size > 0
