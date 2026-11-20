# Deployment Guide

CloudGuard supports containerized production deployments using Docker, Docker Compose, and Kubernetes architectures.

## Architecture Overview

The multi-container deployment architecture includes:
- **CloudGuard App Container**: FastAPI backend service serving Plotly Dash dashboard and REST APIs on port 8050.
- **PostgreSQL Database**: Relational storage for historical cost records, resource inventory, anomaly findings, and optimization recommendations.
- **Redis Cache**: In-memory caching engine for low-latency queries and API response acceleration with fallback.

## Docker Compose Quickstart

### Prerequisites
- Docker Engine 24.0+
- Docker Compose 2.20+

### Environment Configuration
Create a `.env` file from the provided template:

```bash
cp .env.example .env
```

Set the database password and provider credentials in `.env`:

```env
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://cloudguard:your_secure_password@db:5432/cloudguard
REDIS_HOST=redis
REDIS_PORT=6379
DB_PASSWORD=your_secure_password
DEFAULT_PROVIDER=mock
```

### Starting the Stack

```bash
docker compose up -d
```

### Verifying Service Health

```bash
docker compose ps
curl -f http://localhost:8050/api/v1/health
```

### Stopping the Stack

```bash
docker compose down
```

To remove all persistent database and cache volumes:

```bash
docker compose down -v
```

## Production Dockerfile Build

Build the standalone container image:

```bash
docker build -t cloudguard:latest .
```

Run the standalone container with SQLite storage:

```bash
docker run -d \
  --name cloudguard-app \
  -p 8050:8050 \
  -e APP_ENV=production \
  -e DEFAULT_PROVIDER=mock \
  cloudguard:latest
```

## Kubernetes Deployment Blueprint

For high-availability cloud deployments on Azure AKS or AWS EKS:
- Deploy PostgreSQL using AWS RDS Aurora or Azure Database for PostgreSQL.
- Deploy Redis using AWS ElastiCache or Azure Cache for Redis.
- Deploy CloudGuard as a Stateless Deployment with Horizontal Pod Autoscaler targeting CPU utilization at 70%.
- Configure Liveness Probe: `HTTP GET /api/v1/health` on port 8050.
- Configure Readiness Probe: `HTTP GET /api/v1/health` on port 8050.
