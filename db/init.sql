-- ShopStack database seed
-- Two schemas: one per service — this is the microservice data ownership pattern.
-- inventory schema  → owned by the API (products)
-- orders schema     → owned by the API (orders)
-- Same Postgres instance, logically separated. When you split to two DBs in K8s,
-- you change one line per service. The thinking is already right.

CREATE SCHEMA IF NOT EXISTS inventory;
CREATE SCHEMA IF NOT EXISTS orders;

-- Products table
CREATE TABLE IF NOT EXISTS inventory.products (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(200)   NOT NULL,
    category    VARCHAR(100)   NOT NULL,
    price       NUMERIC(10,2)  NOT NULL,
    stock       INTEGER        NOT NULL DEFAULT 0,
    description TEXT,
    created_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

-- Orders table
CREATE TABLE IF NOT EXISTS orders.orders (
    id          SERIAL PRIMARY KEY,
    product_id  INTEGER        NOT NULL,
    quantity    INTEGER        NOT NULL DEFAULT 1,
    total       NUMERIC(10,2)  NOT NULL,
    status      VARCHAR(50)    NOT NULL DEFAULT 'confirmed',
    created_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

-- Seed products — DevOps tooling domain
INSERT INTO inventory.products (name, category, price, stock, description) VALUES
(
    'The Linux Command Line',
    'book',
    39.99,
    150,
    'William Shotts. The definitive guide to the Linux shell. Every DevOps engineer has read this.'
),
(
    'AWS Solutions Architect — Complete Course',
    'course',
    89.99,
    999,
    'Hands-on AWS course covering EC2, VPC, EKS, RDS, IAM, S3, and CloudWatch. 42 hours of video.'
),
(
    'Mechanical Keyboard TKL — Brown Switches',
    'gear',
    129.99,
    34,
    'Tenkeyless layout. Brown tactile switches. The kind of keyboard you justify as a productivity tool.'
),
(
    'Kubernetes in Action',
    'book',
    49.99,
    85,
    'Marko Luksa. The book that makes K8s click. Used in engineering teams at Google and Stripe.'
),
(
    'Docker & Kubernetes Bootcamp',
    'course',
    74.99,
    999,
    'Build, ship, and run containers. Covers Compose, multi-stage builds, EKS, and Helm charts.'
),
(
    'USB-C Hub — 7 Port',
    'gear',
    59.99,
    60,
    'HDMI 4K, 3x USB-A, SD card, USB-C PD, Ethernet. For the engineer with one port and seven cables.'
);

-- One seed order so the orders endpoint returns real data on first boot
INSERT INTO orders.orders (product_id, quantity, total, status) VALUES
(1, 1, 39.99, 'confirmed');
