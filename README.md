# Intelligent API Traffic Management System

An API gateway and control plane for routing, rate limiting, traffic visibility, and adaptive protection.

## Start the development stack

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Services: gateway at `http://localhost:8000`, dashboard at `http://localhost:3001`, control plane at 8010, demo backends at 8001 and 8002, Prometheus at 9090, Grafana at 3000, PostgreSQL at 5432, and Redis at 6379. The first gateway start runs Alembic migrations automatically. Use the `ADMIN_TOKEN` from `.env` (development default: `local-admin-token-change-me`) in the dashboard.

The demo backends support `X-Demo-Delay-Ms` and `X-Demo-Error-Rate` request headers, or `BACKEND_A_*` / `BACKEND_B_*` environment values.

## Modules

1. Infrastructure, schema, demo backends
2. Authenticated API gateway and proxy
3. Atomic Redis rate limiting
4. Backend balancing and resilience
5. Events, metrics, and observability
6. Control plane API and dashboard
7. Anomaly scoring and traffic forecasts
8. Dynamic policy engine and integrated evaluation

See [docs/architecture.md](docs/architecture.md) for the initial system outline.
