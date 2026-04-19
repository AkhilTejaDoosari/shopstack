# ShopStack — Architecture

ShopStack is a 3-tier polyglot containerised application.   
Three tiers: Presentation → Application → Data.       
Five containers. Each one has one job. None overlap.      

As a DevOps engineer you need to know how to run, connect, monitor, and debug each service.   
You do not need to know how to write the code inside them.   

---

## The Three Tiers

**Tier 1 — Presentation (what the user sees)**   
Nginx serves the HTML, CSS, and JavaScript to the browser.   
It also proxies every /api/* request to the Python API.   
Nginx does not know what a product is. It just delivers files and forwards requests.   

**Tier 2 — Application (the brain)**   
Python FastAPI handles all business logic.   
It decides what happens when you buy a product — check stock, write the order, decrement stock.   
It talks to the database. It never stores anything itself.   

**Tier 3 — Data (the memory)**   
Postgres stores everything permanently.   
Products, stock levels, orders, totals.   
It has no logic. It just saves and retrieves rows when the API asks.   

---

## Traffic Flow

```
Browser
  │
  ▼
Nginx :80        ← serves index.html to browser
  │                 proxies /api/* requests to API
  ▼
Python API :8080 ← handles all business logic
  │                 reads and writes to database
  ▼
Postgres :5432   ← stores all data permanently on EC2 disk

Go Worker        ← runs in background
  │                 pings /api/health every 10 seconds
  └──► API :8080    writes structured JSON logs

Adminer :8081    ← visual database browser (dev only)
  └──► Postgres     lets you see tables and run SQL queries
```

## What is Nginx and What is Proxying

Nginx is a web server. Think of it as a traffic cop at the front door.

When you open http://18.219.143.12 in your browser:
```
Browser asks:  "give me the webpage"
Nginx answers: "here is index.html"
```

That is serving static files.

When the JavaScript asks for products:
```
Browser asks Nginx: "GET /api/products"
Nginx thinks:       "I don't handle /api/ — that goes to Python"
Nginx forwards it:  → Python API :8080
Python answers:     returns the products as JSON
Nginx passes back:  sends JSON to the browser
```

That forwarding is called proxying. Nginx receives the request and passes
it to someone else. It is a middleman.

Why not talk to Python directly?
Nginx handles SSL certificates, compression, rate limiting, and serving
files fast. Python should only think about business logic. One job each.

Ingress in Kubernetes is the same concept. When you reach the K8s module,
Ingress is just Nginx running inside the cluster doing the same proxying job.
Same idea, different environment.

---

## What Each Service Is — DevOps Level

As a DevOps engineer you need to know how to operate each service.
You do not need to know how to write the code inside it.

**Nginx (frontend)**
- What it is: web server and reverse proxy
- Your job: make sure it is running, check access logs, fix proxy config
- Industry use: every major website runs Nginx or something equivalent

**Python FastAPI (api)**
- What it is: web framework that handles HTTP requests and business logic
- Your job: make sure it starts, read its logs, check health endpoint
- Industry use: used at Netflix, Uber, Microsoft

**Postgres (db)**
- What it is: relational database — stores data in tables with rows and columns
- Your job: make sure it is running, check connections, manage volumes
- Industry use: the most popular production database in the world

**Go Worker**
- What it is: a compiled background process that pings the API every 10 seconds
- Your job: check its logs to confirm health pings are happening
- Why Go: compiles to a 10MB binary vs 800MB Go compiler — demonstrates multi-stage Dockerfile
- Remove it and the store still works — it is a learning tool for the build pattern

**Adminer**
- What it is: a visual web browser for your Postgres database
- Your job: use it during development to verify data without writing SQL
- In production: this would never exist — databases are not exposed via UI
- Port 8081 is restricted to your IP only for this reason

---

## Where Data Lives

Everything lives on the EC2 instance disk right now.

```
EC2 t3.small — 8GB disk
├── Ubuntu OS          ~2GB
├── Docker images      ~3GB
└── Postgres data      ~50MB (growing as you place orders)
```

The named volume db-data is a folder managed by Docker at:
/var/lib/docker/volumes/infra_db-data/

If you terminate the EC2 instance the data is gone.
That is why in Week 5 you move Postgres to AWS RDS — a managed database
that lives separately from EC2 and survives instance termination.

---

## Services

| Service  | Language | Port | Job                               |
|----------|----------|------|-----------------------------------|
| frontend | Nginx    | 80   | Serves UI, proxies /api/* to API  |
| api      | Python   | 8080 | Products, orders, health, metrics |
| worker   | Go       | —    | Health pinger, structured logs    |
| db       | Postgres | 5432 | inventory + orders schemas        |
| adminer  | —        | 8081 | DB browser UI (dev only)          |

---

## Networks

Two Docker networks. Intentional isolation.   

```
frontend network → nginx ↔ api
backend network  → api ↔ db ↔ worker ↔ adminer
```

Nginx cannot reach the database directly.      
It can only talk to the API.   
The API is the only service allowed to talk to the database.   

This is the same logic as AWS public and private subnets.   
Public subnet  → can reach the internet.   
Private subnet → only reachable from inside the VPC.   

---

## Volumes

```
db-data → named volume → persists Postgres data across container restarts
```

Without the volume: delete the container, lose all data.   
With the volume: delete the container, data survives. Postgres reconnects on restart.   

docker compose down    → volume survives. Data is safe.   
docker compose down -v → volume deleted. Data gone. init.sql reruns on next start.     

---

## Database Schemas

A schema is a namespace. A folder inside the database that groups related tables.   

Without schemas everything is in one pile:
```
products
orders
users
```

With schemas you separate by domain:
```
inventory.products  ← belongs to inventory domain
orders.orders       ← belongs to orders domain
```

Why two schemas in ShopStack:   
Each schema represents one microservice domain.    
The products logic only touches inventory.      
The orders logic only touches orders. They never cross.      

This is the microservice data ownership principle.   
When you split into two separate services in Kubernetes you just point each service at its own schema.       
One line change. The thinking is already right.      

---

## Endpoints

An endpoint is a URL your API listens on. A door into the application.   
Every door has an address (the path) and a method (what you are doing).   

**GET — you are asking for information. Nothing changes.**
**POST — you are sending something to create or change. Something is written.**

```
GET  = read   = looking at a menu
POST = write  = placing an order
```

When you see in nginx logs:
```
GET /api/products → 200         someone loaded the store, all good
POST /api/orders/create → 500   someone tried to buy, it failed
```

You know instantly what happened and where to look.

| Method | Endpoint             | What it does                                     |
|--------|----------------------|--------------------------------------------------|
| GET    | /api/health          | Stack health — db status, uptime per dependency  |
| GET    | /api/products        | All products from inventory.products             |
| GET    | /api/products/:id    | Single product by ID                             |
| GET    | /api/orders          | Recent orders joined with product names          |
| POST   | /api/orders/create   | Create order, decrement stock — atomic           |
| GET    | /api/stress          | 3s delay + CPU loop — for observability practice |
| GET    | /api/metrics         | Prometheus format counters — Observability stub  |

---

## Live URLs

| What          | URL                                          |
|---------------|----------------------------------------------|
| Store UI      | http://18.219.143.12                         |
| Adminer DB UI | http://18.219.143.12:8081                    |
| API health    | http://18.219.143.12:8080/api/health         |
| API products  | http://18.219.143.12:8080/api/products       |
| API orders    | http://18.219.143.12:8080/api/orders         |
| API metrics   | http://18.219.143.12:8080/api/metrics        |
| API stress    | http://18.219.143.12:8080/api/stress         |

## Adminer Login

| Field    | Value         |
|----------|---------------|
| System   | PostgreSQL    |
| Server   | db            |
| Username | shopstack     |
| Password | shopstack_dev |
| Database | shopstack     |

---

## What Comes Next

This stack runs on EC2 with Docker Compose.
Each module takes it further.

| Module        | What changes                                       |
|---------------|----------------------------------------------------|
| Kubernetes    | Same services deployed as K8s manifests on AWS     |
| CI/CD         | GitHub Actions builds and pushes images on commit  |
| Observability | Prometheus scrapes /api/metrics, Grafana shows it  |
| AWS           | EKS cluster, RDS database, ALB load balancer       |
| Terraform     | All AWS infrastructure defined as code             |
| Ansible       | EC2 servers configured automatically               |

---   

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         AWS EC2 t3.small                                   │
│                         18.219.143.12                                      │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Docker Engine                                │   │
│  │                                                                     │   │
│  │   ┌──────────────────────────────────────────────────────────────┐  │   │
│  │   │                   frontend network                           │  │   │
│  │   │                                                              │  │   │
│  │   │   ┌──────────────────┐         ┌─────────────────────────┐   │  │   │
│  │   │   │   NGINX          │         │   PYTHON FASTAPI        │   │  │   │
│  │   │   │   frontend       │◄───────►│   api                   │   │  │   │
│  │   │   │                  │         │                         │   │  │   │
│  │   │   │  serves          │         │  /api/health            │   │  │   │
│  │   │   │  index.html      │         │  /api/products          │   │  │   │
│  │   │   │                  │         │  /api/orders            │   │  │   │
│  │   │   │  proxies /api/*  │         │  /api/orders/creat      │   │  │   │
│  │   │   │  → to api        │         │  /api/metrics           │   │  │   │
│  │   │   │                  │         │  /api/stress            │   │  │   │
│  │   │   │  PORT: 80        │         │                         │   │  │   │
│  │   │   └────────┬─────────┘         │  PORT: 8080             │   │  │   │
│  │   │            │                   └──────────┬──────────────┘   │  │   │
│  │   │            │ public :80                   │                  │  │   │
│  │   └────────────┼──────────────────────────────┼──────────────────┘  │   │
│  │                │                              │                     │   │
│  │   ┌────────────┼──────────────────────────────┼──────────────────┐  │   │
│  │   │            │        backend network       │                  │  │   │
│  │   │            │                              │                  │  │   │
│  │   │            │              ┌───────────────▼────────────────┐ │  │   │
│  │   │            │              │   POSTGRES 15                  │ │  │   │
│  │   │            │              │   db                           │ │  │   │
│  │   │            │              │                                │ │  │   │
│  │   │            │              │   inventory.products           │ │  │   │
│  │   │            │              │   ├── id                       │ │  │   │
│  │   │            │              │   ├── name                     │ │  │   │
│  │   │            │              │   ├── category                 │ │  │   │
│  │   │            │              │   ├── price                    │ │  │   │
│  │   │            │              │   └── stock                    │ │  │   │
│  │   │            │              │                                │ │  │   │
│  │   │            │              │   orders.orders                │ │  │   │
│  │   │            │              │   ├── id                       │ │  │   │
│  │   │            │              │   ├── product_id               │ │  │   │
│  │   │            │              │   ├── quantity                 │ │  │   │
│  │   │            │              │   ├── total                    │ │  │   │
│  │   │            │              │   └── status                   │ │  │   │
│  │   │            │              │                                │ │  │   │
│  │   │            │              │   PORT: 5432                   │ │  │   │
│  │   │            │              │   VOLUME: db-data              │ │  │   │
│  │   │            │              └────────────────────────────────┘ │  │   │
│  │   │            │                                                 │  │   │
│  │   │   ┌────────▼──────────┐   ┌────────────────────────────────┐ │  │   │
│  │   │   │   GO WORKER       │   │   ADMINER                      │ │  │   │
│  │   │   │   worker          │   │   adminer                      │ │  │   │
│  │   │   │                   │   │                                │ │  │   │
│  │   │   │  pings /api/health│   │  visual DB browser             │ │  │   │
│  │   │   │  every 10 seconds │   │  dev tool only                 │ │  │   │
│  │   │   │                   │   │  restricted to your IP         │ │  │   │
│  │   │   │  writes JSON logs │   │                                │ │  │   │
│  │   │   │                   │   │  PORT: 8081                    │ │  │   │
│  │   │   │  multi-stage build│   └────────────────────────────────┘ │  │   │
│  │   │   │  800MB → 10MB     │                                      │  │   │
│  │   │   │                   │                                      │  │   │
│  │   │   │  NO PORT exposed  │                                      │  │   │
│  │   │   └───────────────────┘                                      │  │   │
│  │   │                                                              │  │   │
│  │   └──────────────────────────────────────────────────────────────┘  │   │
│  │                                                                     │   │
│  │   ┌──────────────────────────────────────────────────────────────┐  │   │
│  │   │                     EC2 DISK — 8GB                           │  │   │
│  │   │                                                              │  │   │
│  │   │   Ubuntu OS ──────────────────── ~2GB                        │  │   │
│  │   │   Docker images ───────────────── ~3GB                       │  │   │
│  │   │   db-data volume (Postgres) ───── ~50MB                      │  │   │
│  │   │   /var/lib/docker/volumes/infra_db-data/                     │  │   │
│  │   │                                                              │  │   │
│  │   └──────────────────────────────────────────────────────────────┘  │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│   Security Group Inbound Rules                                             │
│   ├── Port 22   SSH        → your IP only                                  │
│   ├── Port 80   HTTP       → anywhere (the store)                          │
│   ├── Port 8080 Custom TCP → anywhere (direct API access)                  │
│   └── Port 8081 Custom TCP → your IP only (Adminer)                        │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘

                                    │
                              PUBLIC INTERNET
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
             ┌──────▼──────┐               ┌───────▼──────┐
             │   BROWSER   │               │   YOUR MAC   │
             │             │               │              │
             │ opens       │               │ SSH terminal │
             │ :80         │               │ port 22      │
             │ sees store  │               │              │
             └─────────────┘               └──────────────┘


REQUEST FLOW — buying a product   
────────────────────────────────
1. Browser opens http://18.219.143.12
2. Nginx serves index.html + CSS + JS
3. JS runs in browser, calls GET /api/products
4. Nginx proxies → Python API :8080
5. Python queries → SELECT * FROM inventory.products
6. Postgres returns 6 rows
7. Python returns JSON to Nginx
8. Nginx returns JSON to browser
9. JS renders product cards

10. User clicks buy →
11. JS calls POST /api/orders/create
12. Nginx proxies → Python API :8080
13. Python checks stock in inventory.products
14. Python writes row to orders.orders
15. Python decrements stock in inventory.products
16. Steps 13-15 happen atomically — all or nothing
17. Python returns order confirmed
18. JS shows "ordered ✓"
19. Stock count updates in the UI


WORKER FLOW — background health check
──────────────────────────────────────
Every 10 seconds:
Go Worker → GET http://api:8080/api/health
         ← {"status":"ok","db":"connected","uptime":142}
         → writes {"event":"health_ping_ok","latency_ms":2}


VOLUME BEHAVIOUR
─────────────────
docker compose down      → containers stop, volume SURVIVES, data SAFE
docker compose down -v   → containers stop, volume DELETED, data GONE
docker compose up        → Postgres reconnects to existing volume
docker compose up (new)  → Postgres runs init.sql, seeds 6 products


WHAT MOVES IN WEEK 5
──────────────────────
Right now:   Postgres lives on EC2 disk — dies if EC2 is terminated
Week 5:      Postgres moves to AWS RDS — survives EC2 termination
             db-data volume is replaced by RDS endpoint in secrets
             One config change. Everything else stays the same.
```
