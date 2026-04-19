# ShopStack

A polyglot microservice stack for learning DevOps by doing — not by reading about it.

**What it is:** A working e-commerce store (DevOps books, courses, and gear) built across three services in different languages, wired together with Docker Compose, observable with structured JSON logs, and designed to be broken and fixed.

**What it teaches:** Every tool in a real DevOps pipeline — Docker, networking, volumes, healthchecks, multi-stage builds, Postgres, nginx proxying, structured logging, and a Prometheus-format metrics stub ready for the Observability module.

---

## Stack

| Service    | Language      | Image              | Port | Job                                       |
|------------|---------------|--------------------|------|-------------------------------------------|
| `frontend` | Nginx         | nginx:1.24-alpine  | 80   | Serve the store UI, proxy `/api/*` to API |
| `api`      | Python 3.12   | python:3.12-slim   | 8080 | Products, orders, health, metrics         |
| `worker`   | Go 1.22       | alpine:3.19        | —    | Health pinger, structured logs            |
| `db`       | Postgres 15   | postgres:15-alpine | 5432 | Products (inventory schema), orders schema|
| `adminer`  | —             | adminer:4          | 8081 | DB browser UI                             |

### Traffic flow

```
Browser
  │
  ▼
frontend :80  (nginx — serves HTML, proxies /api/*)
  │
  ▼
api :8080  (Python FastAPI — all business logic)
  │
  ▼
db :5432  (Postgres — inventory.products + orders.orders schemas)

worker  →  api :8080/api/health  (pings every 10s, writes structured logs)
```

### Why two schemas in one Postgres?

`inventory` and `orders` are logically separate — the API only queries its own schema. When you move to Kubernetes, splitting them into two separate database containers is one config change. The data ownership principle is already in place.

---

## Quick start

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/shopstack
cd shopstack

# 2. On a fresh Ubuntu AWS instance, run setup first
bash setup.sh
newgrp docker        # reload group permissions — or log out and back in

# 3. Start the stack
docker compose up --build -d

# 4. Verify everything is running
docker ps
curl http://localhost/api/health

# 5. Open in your browser
http://YOUR_EC2_PUBLIC_IP
```

> **AWS note:** Make sure your EC2 security group allows inbound traffic on ports 80 and 8081.

---

## Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Stack health — db status, uptime, per-dependency status |
| `/api/products` | GET | All products from Postgres (inventory schema) |
| `/api/products/:id` | GET | Single product |
| `/api/orders` | GET | Recent orders joined with product names |
| `/api/orders/create` | POST | Create an order, decrement stock (atomic transaction) |
| `/api/stress` | GET | 3s delay + CPU loop — for watching logs and docker stats |
| `/api/metrics` | GET | Prometheus-format counters — stub for Observability module |

---

## Logs

All services emit structured JSON logs. Same format, same fields — ready for Loki.

```bash
# Follow all services
docker compose logs -f

# Follow one service
docker compose logs -f api

# Filter to errors across all services
docker compose logs -f | grep '"level":"error"'

# See why a container crashed (logs from before the last restart)
docker logs --previous shopstack-api-1

# Resource usage — run while hitting /api/stress
docker stats
```

**Example log line:**
```json
{"ts":"2025-01-01T12:00:00Z","level":"info","service":"api","event":"order_created","order_id":5,"product_id":1,"total":39.99}
```

---

## Break it on purpose

See [`BREAK_IT.md`](./BREAK_IT.md) for 8 documented sabotage scenarios — each with the exact change, what breaks, how to diagnose it, and how to fix it.

Covers: startup race condition, wrong env vars, nginx proxy misconfiguration, Dockerfile layer cache, volume wipe, import error, timeout, port conflict.

---

## Project structure

```
shopstack/
├── setup.sh              ← Docker install for Ubuntu AWS
├── docker-compose.yml    ← single command to run everything
├── init.sql              ← seeds inventory + orders schemas
├── BREAK_IT.md           ← 8 sabotage scenarios with diagnosis
│
├── frontend/
│   ├── Dockerfile        ← nginx:1.24-alpine, 6 lines
│   ├── nginx.conf        ← proxy rules + access log + timeout config
│   └── html/index.html   ← live health UI, product store, order history
│
├── api/
│   ├── Dockerfile        ← python:3.12-slim, 10 lines
│   ├── requirements.txt  ← fastapi, uvicorn, asyncpg, pydantic
│   └── main.py           ← all endpoints, retry loop, structured logs
│
└── worker/
    ├── Dockerfile        ← multi-stage Go build, final image ~10MB
    ├── go.mod
    └── main.go           ← health pinger, JSON logs, 10s interval
```

---

## Useful commands

```bash
# Start
docker compose up --build -d

# Stop (data preserved)
docker compose down

# Stop + wipe database (init.sql re-runs on next up)
docker compose down -v

# Rebuild one service
docker compose up --build api -d

# Shell inside a container
docker exec -it shopstack-api-1 bash
docker exec -it shopstack-db-1  psql -U shopstack -d shopstack

# Inspect networks
docker network inspect shopstack_backend
docker network inspect shopstack_frontend

# Adminer (DB browser UI)
http://localhost:8081
# System: PostgreSQL | Server: db | User: shopstack | Password: shopstack_dev | DB: shopstack
```

---

## Part of the DevOps Runbook

This stack is the hands-on project for the [devops-runbook](https://github.com/YOUR_USERNAME/devops-runbook) — a personal reference covering Linux, Git, Networking, Docker, Kubernetes, CI/CD, Observability, AWS, and Terraform.

ShopStack progresses with each module:

| Module | What changes |
|---|---|
| Docker | You are here — stack runs locally on compose |
| Kubernetes | Same services deployed to Minikube with manifests |
| CI/CD | GitHub Actions builds and pushes the API image on every commit |
| Observability | Prometheus scrapes `/api/metrics`, Grafana dashboards, Loki for logs |
| AWS | Stack deployed to EKS, RDS for the database, ALB for the load balancer |
| Terraform | All AWS infrastructure defined as code |
