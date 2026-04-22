# ShopStack

A 3-tier polyglot containerised application for learning DevOps by doing — not by reading about it.

**What it is:** A working e-commerce store selling DevOps books, courses, and gear. Built across three services in different languages, wired together with Docker Compose, observable with structured JSON logs, and designed to be broken and fixed.

**What it teaches:** Every tool in a real DevOps pipeline — Docker, networking, volumes, healthchecks, multi-stage builds, Postgres, Nginx proxying, structured logging, and a Prometheus-format metrics stub ready for the Observability module.

---

## Stack

| Service    | Language    | Image              | Port | Job                                        |
|------------|-------------|--------------------|------|--------------------------------------------|
| `frontend` | Nginx       | nginx:1.24-alpine  | 80   | Serves the store UI, proxies `/api/*` to API |
| `api`      | Python 3.12 | python:3.12-slim   | 8080 | Products, orders, health, metrics          |
| `worker`   | Go 1.22     | alpine:3.19        | —    | Health pinger every 10s, structured logs   |
| `db`       | Postgres 15 | postgres:15-alpine | 5432 | inventory schema + orders schema           |
| `adminer`  | —           | adminer:4          | 8081 | DB browser UI (dev only)                   |

---

## Traffic Flow

```
Browser
  │
  ▼
frontend :80   (Nginx — serves index.html, proxies /api/* requests)
  │
  ▼
api :8080      (Python FastAPI — all business logic)
  │
  ▼
db :5432       (Postgres — inventory.products + orders.orders)

worker → api :8080/api/health  (pings every 10s, writes JSON logs)
adminer :8081                  (visual DB browser, dev only)
```

---

## Project Structure

```
shopstack/
├── docs/
│   ├── architecture.md   ← full architecture with mental models and ASCII diagram
│   └── BREAK_IT.md       ← 8 sabotage scenarios with diagnosis commands
├── db/
│   └── init.sql          ← seeds inventory + orders schemas, 6 products
├── infra/
│   ├── docker-compose.yml
│   ├── k8s/              ← Kubernetes manifests (filled in Week 2)
│   └── terraform/        ← Terraform modules (filled in Week 6)
├── scripts/
│   ├── setup.sh          ← Docker install for Ubuntu EC2
│   └── health-check.sh   ← Bash health check script (filled in Week 7)
└── services/
    ├── api/
    │   ├── Dockerfile        ← python:3.12-slim, layer-cache optimised
    │   ├── requirements.txt  ← fastapi, uvicorn, asyncpg, pydantic
    │   └── src/
    │       └── main.py       ← all endpoints, retry loop, structured logs
    ├── frontend/
    │   ├── Dockerfile        ← nginx:1.24-alpine
    │   ├── nginx.conf        ← proxy rules, timeout config, access log
    │   └── html/
    │       └── index.html    ← store UI, live health banner, API inspector
    └── worker/
        ├── Dockerfile        ← multi-stage Go build, final image ~10MB
        ├── go.mod
        └── main.go           ← health pinger, JSON logs, 10s interval
```

---

## Quick Start — AWS EC2

```bash
# 1. Launch EC2 t3.small — Ubuntu 22.04 — on AWS
# Security group: port 22 (your IP), port 80 (anywhere), port 8080 (anywhere), port 8081 (your IP)

# 2. SSH into the instance
ssh -i your-key.pem ubuntu@YOUR_EC2_IP

# 3. Install Docker
bash scripts/setup.sh
newgrp docker

# 4. Clone the repo
git clone https://github.com/AkhilTejaDoosari/shopstack.git
cd shopstack/infra

# 5. Start the stack
docker compose up --build -d

# 6. Verify
docker ps
curl http://localhost/api/health

# 7. Open in browser
http://YOUR_EC2_IP
```

---

## Live URLs

| What          | URL                                        |   
|---------------|--------------------------------------------|
| Store UI      | http://YOUR_EC2_IP                         |
| Adminer DB UI | http://YOUR_EC2_IP:8081                    |
| API health    | http://YOUR_EC2_IP:8080/api/health         |
| API products  | http://YOUR_EC2_IP:8080/api/products       |
| API orders    | http://YOUR_EC2_IP:8080/api/orders         |
| API metrics   | http://YOUR_EC2_IP:8080/api/metrics        |

### Adminer Login

| Field    | Value         |
|----------|---------------|
| System   | PostgreSQL    |
| Server   | db            |
| Username | shopstack     |
| Password | shopstack_dev |
| Database | shopstack     |

---

## Endpoints

| Method | Endpoint              | Description                                      |
|--------|-----------------------|--------------------------------------------------|
| GET    | `/api/health`         | Stack health — db status, uptime per dependency  |
| GET    | `/api/products`       | All products from inventory.products             |
| GET    | `/api/products/:id`   | Single product by ID                             |
| GET    | `/api/orders`         | Recent orders joined with product names          |
| POST   | `/api/orders/create`  | Create order, decrement stock — atomic           |
| GET    | `/api/stress`         | 3s delay + CPU loop — for observability practice |
| GET    | `/api/metrics`        | Prometheus format counters — Observability stub  |

---

## Logs

All services emit structured JSON logs. Same format across Python and Go — ready for Loki.

```bash
# Follow all services live
docker compose logs -f

# Follow one service
docker compose logs -f api

# Filter to errors only
docker compose logs -f | grep '"level":"error"'

# See why a container crashed before the last restart
docker logs --previous infra-api-1

# Resource usage — run while hitting /api/stress
docker stats
```

Example log line:
```json
{"ts":"2026-04-19T00:00:00Z","level":"info","service":"api","event":"order_created","order_id":5,"product_id":1,"total":39.99}
```

---

## Useful Commands

```bash
# Start (from infra/ folder)
cd infra
docker compose up --build -d

# Stop — data preserved
docker compose down

# Stop + wipe database — init.sql reruns on next start
docker compose down -v

# Rebuild one service
docker compose up --build api -d

# Check all container status
docker ps

# Shell inside a container
docker exec -it infra-api-1 bash
docker exec -it infra-db-1 psql -U shopstack -d shopstack

# Inspect networks
docker network inspect infra_backend
docker network inspect infra_web

# View all logs
docker compose logs -f
```

---

## Break It on Purpose

See [`docs/BREAK_IT.md`](./docs/BREAK_IT.md) for 8 documented sabotage scenarios.   

Each scenario has the exact change to make, what breaks, the diagnosis commands, and the fix.   

Covers: startup race condition, wrong env vars, nginx proxy misconfiguration, Dockerfile layer cache, volume wipe, Python import error, nginx timeout, port conflict.   

---

## Networks

```
web network → nginx ↔ api
backend network  → api ↔ db ↔ worker ↔ adminer
```

The database is not reachable from Nginx directly. The API is the only service that talks to the database.   
This is intentional isolation — same concept as AWS public and private subnets.   

---

## Part of the DevOps Runbook

This stack is the hands-on project for the [devops-runbook](https://github.com/AkhilTejaDoosari/devops-runbook) — a personal reference covering Linux, Git, Networking, Docker, Kubernetes, CI/CD, Observability, AWS, Terraform, and Ansible.   

ShopStack progresses with each module:   

| Module        | What changes                                              |
|---------------|-----------------------------------------------------------|
| Docker        | You are here — stack runs on EC2 with Docker Compose      |
| Kubernetes    | Same services deployed as K8s manifests on AWS            |
| CI/CD         | GitHub Actions builds and pushes images on every commit   |
| Observability | Prometheus scrapes `/api/metrics`, Grafana dashboards     |
| AWS           | EKS cluster, RDS for database, ALB for load balancer      |
| Terraform     | All AWS infrastructure provisioned as code                |
| Ansible       | EC2 servers configured automatically with playbooks       |

---
