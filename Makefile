.PHONY: help install dev lint format test test-cov benchmark docker-build docker-up docker-down clean

PYTHON ?= python
PIP ?= pip
PYTEST ?= pytest
RUFF ?= ruff

help:
	@echo "Available targets:"
	@echo "  install       Install package in editable mode"
	@echo "  dev           Install package with dev dependencies"
	@echo "  lint          Run ruff linter"
	@echo "  format        Format code using ruff"
	@echo "  test          Run full pytest test suite"
	@echo "  test-cov      Run pytest with coverage report"
	@echo "  benchmark     Run 100k record benchmark"
	@echo "  docker-build  Build docker image"
	@echo "  docker-up     Start docker compose stack"
	@echo "  docker-down   Stop docker compose stack"
	@echo "  clean         Clean cache and build artifacts"

install:
	$(PIP) install -e .

dev:
	$(PIP) install -e ".[dev,postgres,pdf]"

lint:
	$(RUFF) check src/ tests/ scripts/

format:
	$(RUFF) format src/ tests/ scripts/
	$(RUFF) check --fix src/ tests/ scripts/

test:
	$(PYTEST) -v

test-cov:
	$(PYTEST) --cov=cloudguard --cov-report=html --cov-report=term-missing -v

benchmark:
	$(PYTHON) scripts/benchmark.py --records 100000

docker-build:
	docker build -t cloudguard:latest .

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').glob('.*cache')]"
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').glob('*.egg-info')]"
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').glob('htmlcov')]"
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').glob('build')]"
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').glob('dist')]"
