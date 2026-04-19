"""
ShopStack API — Python FastAPI
Handles: products, orders, health, metrics
Talks to: Postgres (inventory + orders schemas)
"""

import os
import time
import json
import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import asyncpg
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

# ── Structured logging ────────────────────────────────────────────────────────
# JSON logs from day one — ready for Loki when you reach Observability module.
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("shopstack.api")

def emit(level: str, event: str, **kwargs):
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "service": "api",
        "event": event,
        **kwargs,
    }
    print(json.dumps(record), flush=True)


# ── DB connection pool ────────────────────────────────────────────────────────
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "shopstack")
DB_USER = os.getenv("DB_USER", "shopstack")
DB_PASS = os.getenv("DB_PASS", "shopstack_dev")

pool: asyncpg.Pool | None = None

# Metrics counters — stub for Prometheus scraping in Observability module
_counters = {
    "http_requests_total": 0,
    "orders_created_total": 0,
    "db_errors_total": 0,
}


async def get_pool() -> asyncpg.Pool:
    """Retry loop — waits for Postgres to be ready, not just running."""
    global pool
    if pool:
        return pool

    max_attempts = 12
    for attempt in range(1, max_attempts + 1):
        try:
            emit("info", "db_connect_attempt", attempt=attempt, host=DB_HOST)
            pool = await asyncpg.create_pool(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASS,
                min_size=2,
                max_size=10,
                command_timeout=10,
            )
            emit("info", "db_connected", host=DB_HOST, database=DB_NAME)
            return pool
        except Exception as exc:
            emit("warn", "db_connect_failed", attempt=attempt, error=str(exc))
            if attempt == max_attempts:
                emit("error", "db_connect_exhausted", max_attempts=max_attempts)
                raise
            await asyncio.sleep(3)


# ── App lifecycle ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    emit("info", "startup", version="1.0.0")
    await get_pool()
    yield
    if pool:
        await pool.close()
    emit("info", "shutdown")


app = FastAPI(title="ShopStack API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request logging middleware ────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    _counters["http_requests_total"] += 1
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - start) * 1000, 2)
    emit(
        "info", "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
    )
    return response


# ── Models ────────────────────────────────────────────────────────────────────
class OrderCreate(BaseModel):
    product_id: int
    quantity: int = 1


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    """
    Structured health check.
    Returns per-dependency status — not just HTTP 200.
    This is exactly what a K8s readiness probe expects.
    """
    db_status = "ok"
    db_error = None
    uptime = int(time.monotonic())

    try:
        p = await get_pool()
        async with p.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as exc:
        db_status = "error"
        db_error = str(exc)
        _counters["db_errors_total"] += 1

    overall = "ok" if db_status == "ok" else "degraded"

    return {
        "status": overall,
        "service": "api",
        "version": "1.0.0",
        "uptime_seconds": uptime,
        "dependencies": {
            "postgres": {
                "status": db_status,
                **({"error": db_error} if db_error else {}),
            }
        },
        "ts": datetime.now(timezone.utc).isoformat(),
    }


# ── Metrics stub ──────────────────────────────────────────────────────────────
@app.get("/api/metrics", response_class=PlainTextResponse)
async def metrics():
    """
    Prometheus-format metrics stub.
    When you reach the Observability module, swap this for:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator().instrument(app).expose(app)
    The /metrics path and format stay the same. Zero rework.
    """
    lines = [
        "# HELP http_requests_total Total HTTP requests handled by the API",
        "# TYPE http_requests_total counter",
        f'http_requests_total{{service="api"}} {_counters["http_requests_total"]}',
        "",
        "# HELP orders_created_total Total orders placed",
        "# TYPE orders_created_total counter",
        f'orders_created_total{{service="api"}} {_counters["orders_created_total"]}',
        "",
        "# HELP db_errors_total Total database connection errors",
        "# TYPE db_errors_total counter",
        f'db_errors_total{{service="api"}} {_counters["db_errors_total"]}',
        "",
    ]
    return "\n".join(lines)


# ── Products ──────────────────────────────────────────────────────────────────
@app.get("/api/products")
async def list_products():
    try:
        p = await get_pool()
        async with p.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, category, price, stock, description, created_at
                FROM inventory.products
                ORDER BY id
                """
            )
        return [dict(r) for r in rows]
    except Exception as exc:
        _counters["db_errors_total"] += 1
        emit("error", "products_fetch_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=f"Database error: {exc}")


@app.get("/api/products/{product_id}")
async def get_product(product_id: int):
    try:
        p = await get_pool()
        async with p.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM inventory.products WHERE id = $1", product_id
            )
        if not row:
            raise HTTPException(status_code=404, detail="Product not found")
        return dict(row)
    except HTTPException:
        raise
    except Exception as exc:
        _counters["db_errors_total"] += 1
        raise HTTPException(status_code=503, detail=str(exc))


# ── Orders ────────────────────────────────────────────────────────────────────
@app.get("/api/orders")
async def list_orders():
    try:
        p = await get_pool()
        async with p.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT o.id, o.product_id, p.name as product_name,
                       o.quantity, o.total, o.status, o.created_at
                FROM orders.orders o
                JOIN inventory.products p ON p.id = o.product_id
                ORDER BY o.created_at DESC
                LIMIT 50
                """
            )
        return [dict(r) for r in rows]
    except Exception as exc:
        _counters["db_errors_total"] += 1
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/orders/create", status_code=201)
async def create_order(body: OrderCreate):
    try:
        p = await get_pool()
        async with p.acquire() as conn:
            # Verify product exists and has stock
            product = await conn.fetchrow(
                "SELECT id, name, price, stock FROM inventory.products WHERE id = $1",
                body.product_id,
            )
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")
            if product["stock"] < body.quantity:
                raise HTTPException(
                    status_code=409,
                    detail=f"Insufficient stock. Available: {product['stock']}",
                )

            total = float(product["price"]) * body.quantity

            # Decrement stock and create order atomically
            async with conn.transaction():
                await conn.execute(
                    "UPDATE inventory.products SET stock = stock - $1 WHERE id = $2",
                    body.quantity, body.product_id,
                )
                order = await conn.fetchrow(
                    """
                    INSERT INTO orders.orders (product_id, quantity, total, status)
                    VALUES ($1, $2, $3, 'confirmed')
                    RETURNING id, product_id, quantity, total, status, created_at
                    """,
                    body.product_id, body.quantity, total,
                )

        _counters["orders_created_total"] += 1
        emit("info", "order_created", order_id=order["id"], product_id=body.product_id, total=total)
        return {**dict(order), "product_name": product["name"]}

    except HTTPException:
        raise
    except Exception as exc:
        _counters["db_errors_total"] += 1
        emit("error", "order_create_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


# ── Stress endpoint ───────────────────────────────────────────────────────────
@app.get("/api/stress")
async def stress():
    """
    Two things:
    1. 3-second delay (response time stress)
    2. CPU loop (compute stress — this is what the K8s HPA actually reacts to)

    When you get to Prometheus, you'll see http_requests_total climb
    and duration_ms spike. That's real observability, not a tutorial.
    """
    start = time.monotonic()

    # CPU work — compute 100k iterations
    total = 0
    for i in range(100_000):
        total += i * i

    # Simulated downstream latency
    await asyncio.sleep(3)

    duration = round(time.monotonic() - start, 3)
    emit("warn", "stress_endpoint_hit", duration_seconds=duration, cpu_work=total)

    return {
        "message": "Stress complete",
        "duration_seconds": duration,
        "cpu_iterations": 100_000,
        "tip": "Watch docker stats while hitting this endpoint. Then watch /api/metrics.",
    }
