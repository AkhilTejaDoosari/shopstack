# BREAK_IT.md — ShopStack Sabotage Guide

> Break things on purpose. Fix them yourself. That's the whole point.
> Every break here is a real production failure mode.
> Every diagnosis command is one you'll use on the job.

---

## How to use this guide

1. Read the break description
2. Make the change
3. Run `docker compose up --build -d` (or just `docker compose restart <service>`)
4. Watch what breaks
5. Diagnose it using the commands provided
6. Fix it
7. Verify it's fixed
8. Move to the next one

**Rule:** Do not look at the fix until you've tried to diagnose it yourself.

---

## Logs — your first tools

Before any break, learn these:

```bash
# Follow all service logs live (best for startup issues)
docker compose logs -f

# Follow one service
docker compose logs -f api
docker compose logs -f db
docker compose logs -f worker
docker compose logs -f frontend

# See the last 50 lines from one service
docker compose logs --tail=50 api

# IMPORTANT: If a container crashed and restarted, logs shows the current run.
# To see why it crashed:
docker logs --previous shopstack-api-1

# Container status
docker ps
docker ps -a   # includes stopped containers

# Resource usage (CPU, memory) — run this while hitting /api/stress
docker stats

# Inspect a container's config, networks, volumes
docker inspect shopstack-api-1
```

---

## Break 1 — Remove `depends_on` (startup race condition)

**What it teaches:** `depends_on` and why Postgres needs time after the container starts.

**The change:** In `docker-compose.yml`, remove the `depends_on` block from the `api` service.

**What to run:**
```bash
docker compose down
docker compose up --build -d
docker compose logs -f api
```

**What you'll see:**
```
api    | {"level":"warn","service":"api","event":"db_connect_failed","attempt":1,"error":"..."}
api    | {"level":"warn","service":"api","event":"db_connect_failed","attempt":2,"error":"..."}
```

Or the API may start, crash, and restart immediately.

**Why:** The db container started but Postgres wasn't accepting connections yet. The API tried to connect and failed. Without the retry loop in `main.py`, it would crash completely.

**Diagnose:**
```bash
docker ps                          # Is db healthy? Look at the STATUS column
docker compose logs db             # What is Postgres saying?
docker exec shopstack-db-1 pg_isready -U shopstack -d shopstack
```

**Fix:** Restore `depends_on` with `condition: service_healthy`.

---

## Break 2 — Wrong DB_HOST (connection refused)

**What it teaches:** How env vars wire services together. Docker DNS.

**The change:** In `docker-compose.yml`, change `DB_HOST: db` to `DB_HOST: database`.

**What to run:**
```bash
docker compose up --build -d
docker compose logs -f api
```

**What you'll see:**
```
{"level":"warn","event":"db_connect_failed","error":"could not translate host name \"database\""}
```

**Why:** `db` is the service name in compose — Docker DNS resolves it automatically. `database` doesn't exist on the network. The API retries 12 times, then gives up.

**Diagnose:**
```bash
docker compose logs api | grep "db_connect"
docker network inspect shopstack_backend   # What hostnames are registered?
docker exec shopstack-api-1 ping db        # Can the api container reach the db by name?
```

**Fix:** Change `DB_HOST` back to `db`.

---

## Break 3 — Wrong nginx proxy_pass (502 Bad Gateway)

**What it teaches:** How nginx proxying works. What a 502 means.

**The change:** In `frontend/nginx.conf`, change:
```
proxy_pass http://api:8080;
```
to:
```
proxy_pass http://apiservice:8080;
```

**What to run:**
```bash
docker compose up --build -d
# Open http://your-ip in the browser
```

**What you'll see:** The page loads (nginx is running) but the status banner shows API is down, and all API calls return `502 Bad Gateway`.

**Why:** `api` resolves via Docker DNS on the frontend network. `apiservice` doesn't exist. nginx can't connect upstream.

**Diagnose:**
```bash
docker compose logs frontend           # nginx logs the 502
curl -v http://localhost/api/health   # You'll see the 502 in the response
docker network inspect shopstack_frontend  # What services are on this network?
```

**Fix:** Restore `proxy_pass http://api:8080;` in nginx.conf.

---

## Break 4 — Reorder Dockerfile COPY layers (cache miss every build)

**What it teaches:** Docker layer caching. Why order matters.

**The change:** In `api/Dockerfile`, swap the COPY order:
```dockerfile
# Change this:
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

# To this:
COPY . .
RUN pip install -r requirements.txt
```

**What to run:**
```bash
# Change a line in api/main.py (add a comment)
echo "# test" >> api/main.py
# Build and time it
time docker compose build api
```

**What you'll see:** `pip install` runs from scratch even though `requirements.txt` didn't change. Every code change triggers a full dependency reinstall.

**Why:** Docker invalidates all layers below a changed layer. `COPY . .` copies everything including source code. When source changes, the layer is invalidated, and `RUN pip install` below it re-runs even if requirements.txt is identical.

**Diagnose:**
```bash
docker build api/ --no-cache    # Force full rebuild, see all layers
docker history shopstack-api    # See the layers and their sizes
```

**Fix:** Always COPY dependency files first, install, then COPY source.

---

## Break 5 — Remove the DB volume (data wipe)

**What it teaches:** The difference between `docker compose down` and `docker compose down -v`.

**The change:** This one doesn't require editing files.

**What to run:**
```bash
# First, buy something in the store — create an order
# Then:
docker compose down -v    # -v removes volumes
docker compose up -d
# Open the store — check orders
```

**What you'll see:** All orders are gone. Products are re-seeded from `init.sql`. The `-v` flag deleted the named volume that held Postgres data.

**Why:** `docker compose down` stops containers and removes them. The named volume persists. `docker compose down -v` also deletes the volume. This is a data wipe. In production this is catastrophic. In dev it's how you reset to a clean state.

**Diagnose:**
```bash
docker volume ls                          # Before: db-data volume exists
docker compose down -v
docker volume ls                          # After: it's gone
docker compose up -d
docker compose logs db | grep "init"      # init.sql ran again
```

**Fix:** Don't run `-v` unless you mean to wipe. `docker compose down` alone is safe.

---

## Break 6 — Wrong Python import (startup crash)

**What it teaches:** How to read Python startup errors in Docker logs.

**The change:** In `api/requirements.txt`, delete the `asyncpg` line.

**What to run:**
```bash
docker compose up --build -d
docker compose logs api
```

**What you'll see:**
```
ModuleNotFoundError: No module named 'asyncpg'
```
Then the container exits. `docker ps` shows it as `Restarting`.

**Diagnose:**
```bash
docker ps -a                        # Status column shows "Restarting" or "Exited"
docker compose logs api             # First 10 lines tell you everything
docker logs --previous shopstack-api-1   # See the crash before the restart
```

**Fix:** Restore `asyncpg==0.29.0` in requirements.txt. Rebuild.

---

## Break 7 — nginx timeout too short for /api/stress (504)

**What it teaches:** Timeouts, upstream latency, and what 504 means vs 502.

**The change:** In `frontend/nginx.conf`, change:
```
proxy_read_timeout 10s;
```
to:
```
proxy_read_timeout 2s;
```

**What to run:**
```bash
docker compose up --build -d
# In the API Inspector panel, click /api/stress
# Or: curl http://localhost/api/stress
```

**What you'll see:** After 2 seconds, nginx returns `504 Gateway Timeout` — before the API finishes the 3-second stress response.

**Why:** nginx waited 2s for the upstream (the API) to respond. The API takes 3s on `/api/stress`. nginx gave up first and returned 504 to the client. The API kept running — check `docker compose logs api` to see it complete.

**Diagnose:**
```bash
curl -v http://localhost/api/stress       # See the 504 in real time
docker compose logs api                  # API completed the request anyway
docker compose logs frontend             # nginx logged "upstream timed out"
```

**Fix:** Restore `proxy_read_timeout 10s;`. Or increase to 30s if you want to receive the full stress response.

---

## Break 8 — Port conflict (container won't start)

**What it teaches:** Port binding errors and how to find what's using a port.

**The change:** Before running compose, manually start a container on port 80:
```bash
docker run -d -p 80:80 --name port-blocker nginx:alpine
```

**Then run:**
```bash
docker compose up -d
```

**What you'll see:**
```
Error response from daemon: driver failed programming external connectivity:
Bind for 0.0.0.0:80 failed: port is already allocated
```

**Diagnose:**
```bash
docker ps                        # See port-blocker running on :80
ss -tlnp | grep ':80'            # What process has port 80 on the host?
sudo lsof -i :80                 # Alternative — which PID owns port 80
```

**Fix:**
```bash
docker stop port-blocker
docker rm port-blocker
docker compose up -d
```

---

## Watch all logs in real time — the full picture

```bash
# Every service, structured JSON, live
docker compose logs -f

# Filter to just errors across all services
docker compose logs -f | grep '"level":"error"'
docker compose logs -f | grep '"level":"warn"'

# Watch resource usage while hitting /api/stress
docker stats

# See what networks each container is on
docker network ls
docker network inspect shopstack_backend
docker network inspect shopstack_frontend

# Run a shell inside a container to debug from inside
docker exec -it shopstack-api-1 bash
docker exec -it shopstack-db-1  psql -U shopstack -d shopstack
```

---

## After every break — the verification checklist

```bash
docker ps                                    # All 5 containers running?
curl http://localhost/api/health             # {"status":"ok",...}
curl http://localhost/api/products           # 6 products returned?
curl http://localhost/api/metrics            # Prometheus counters?
# Open the browser — is the status banner green?
# Does the congrats block say "CONGRATS — stack is fully alive"?
```

When all of the above pass: the stack is healthy. Move to the next break.
