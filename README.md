# SupplyHub

SupplyHub is a B2B platform where supplier organizations can manage their products and inventory, while buyer organizations can search for products and create orders.

## Project status

The backend currently supports JWT authentication, users, organization-scoped memberships, typed supplier and buyer organizations, product, warehouse, inventory, and order management, including Argon2 password hashing, search, filtering, pagination, soft deactivation, stock levels, auditable stock adjustments, filtered stock movement history, concurrency-safe inventory reservations, immutable order price snapshots, atomic order placement, cancellation, full fulfillment, and append-only order status history. Automated tests run against a dedicated PostgreSQL test database.

## Local development

Copy `.env.example` to `.env`. Generate a local authentication secret with:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Store the generated value in `AUTH_SECRET_KEY`. Never commit the local `.env` file or reuse this development secret in another environment.

Start the development and test databases from the repository root:

```powershell
docker compose up -d
```

Apply migrations to the development database and run the API:

```powershell
cd apps\api
..\..\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8001
```

Run the test suite in a separate terminal:

```powershell
cd apps\api
..\..\.venv\Scripts\Activate.ps1
python -m pytest -v
```

Tests connect to the dedicated `supplyhub_test` database on port `5433` and apply pending migrations automatically. The test service uses disposable local credentials and does not store data in the development database volume.

Install development tools and check linting and formatting before committing backend changes:

```powershell
python -m pip install -r requirements.txt
python -m ruff check .
python -m ruff format --check .
python -m mypy app
```

## Problem

Many companies need to manage catalogs, inventory, and orders between organizations.

A traditional online store is usually designed for individual consumers. SupplyHub is focused on business-to-business relationships, where the system must support:

* Multiple organizations.
* Multiple employees within each organization.
* Roles and permissions.
* Multiple warehouses.
* Customer-specific pricing.
* Inventory reservations.
* Operation auditing.
* Advanced product search.

## Goal

The goal of this project is to build a professional application that demonstrates knowledge of:

* Frontend development.
* Backend development.
* API design.
* Software architecture.
* Relational databases.
* Document databases.
* Search engines.
* Automated testing.
* Docker.
* Continuous integration and continuous deployment.
* Technical documentation.

## User roles

### Platform administrator

Manages the overall SupplyHub platform.

### Organization administrator

Manages users, roles, and settings for an organization.

### Catalog manager

Creates, updates, and deactivates products.

### Warehouse operator

Manages inventory levels and stock movements.

### Buyer

Searches for products and creates orders.

### Viewer

Can view information but cannot modify it.

## MVP features

The first functional version will include:

* Organization creation.
* User management.
* Role and permission management.
* Product creation and management.
* Warehouse management.
* Inventory management.
* Product search.
* Order creation.
* Order status tracking.
* Audit event registration.

## Features outside the MVP

The following features will not be developed initially:

* Real payment processing.
* Electronic invoicing.
* Mobile applications.
* Artificial intelligence recommendations.
* Kubernetes.
* Microservices.
* Microfrontends.
* Multiple backend programming languages.
* Shipping carrier integrations.

These features may be evaluated after the first stable version is completed.

## Architecture

SupplyHub is implemented as a modular monolith: one deployable backend application divided into explicit business modules.

Backend modules follow a consistent request flow:

```text
HTTP request
    -> router
    -> service
    -> repository
    -> SQLAlchemy session
    -> PostgreSQL
```

Routers handle HTTP concerns and dependency injection, services enforce business rules and transaction outcomes, and repositories own database queries.

Current business modules include:

* Authentication.
* Organizations.
* Identity and organization memberships.
* Catalog.
* Inventory.
* Orders.

PostgreSQL is authoritative for business data. Search indexes, caches, and future read models must remain rebuildable projections. Microservices will only be introduced when a module has clear data ownership, stable contracts, independent operational requirements, and documented failure-recovery behavior.

Orders and Inventory intentionally share a transactional boundary while order placement, reservation, cancellation, and fulfillment require atomic consistency. Notifications and Search are potential future extraction candidates because their workloads can be asynchronous or projection-based.

## Planned technologies

### Frontend

* React.
* TypeScript.

### Backend

* Python.
* FastAPI.
* SQLAlchemy.
* Alembic.
* Pydantic.
* Pytest.

### Storage

* PostgreSQL as the primary source of truth.
* MongoDB for the asynchronous audit and operational event-history projection.
* OpenSearch for advanced product search when the PostgreSQL baseline no longer satisfies the required search experience.
* Additional datastores only when demonstrated access, retention, or scaling requirements justify them.

### Infrastructure

* Docker.
* Docker Compose.
* GitHub Actions.

## Storage strategy

### PostgreSQL

PostgreSQL will store the primary business data:

* Users.
* Organizations.
* Products.
* Warehouses.
* Inventory.
* Orders.
* Roles and permissions.

PostgreSQL will be the primary source of truth for the system.

### Audit and derived data

Audit events will record who performed an action, which organization and resource were affected, when it occurred, and safe metadata describing the change. PostgreSQL will store the transactional outbox so business state and event publication intent commit atomically. Asynchronous workers will project those events into MongoDB, which will provide a flexible document model for operational audit history, independent retention, and audit-focused queries. Consumers must be idempotent, and the MongoDB projection must be replayable and rebuildable from durable events.

### OpenSearch

OpenSearch will be used to provide advanced product search capabilities.

It will support:

* Full-text search.
* Category filters.
* Brand filters.
* Price ranges.
* Attribute filters.
* Result sorting.

OpenSearch will not be the primary source of truth. Its indexes must be rebuildable from the information stored in PostgreSQL.

## Roadmap

Development follows small, verified milestones. The planned sequence is:

1. Complete authentication, centralized permissions, and multi-tenant isolation.
2. Add secure signup, email verification, invitations, password recovery, and revocable browser sessions.
3. Introduce a deliberately limited public product catalog while keeping operational inventory and warehouses private.
4. Build the React and TypeScript buyer and supplier experiences.
5. Extend the commercial order lifecycle with confirmation, shipping, delivery, partial fulfillment, and safe retries.
6. Add immutable audit events, a PostgreSQL transactional outbox, asynchronous workers, and an idempotent MongoDB audit projection with replay and reconciliation support.
7. Add notifications, signed webhooks, and OpenSearch as independently recoverable asynchronous projections.
8. Add structured logs, metrics, traces, dashboards, alerts, and reliability exercises.
9. Establish staging and production delivery, secret management, backups, restoration tests, security scanning, and rollback procedures.
10. Extract independently deployable services only when stable boundaries and operational requirements justify the added complexity.
11. Add commercial SaaS capabilities such as subscriptions, plan limits, integrations, support tooling, and privacy workflows.

## Project principles

* Complexity should only be added when it solves a real problem.
* Every feature should be documented.
* Business rules should have automated tests.
* PostgreSQL will be the primary source of truth.
* Errors should be handled explicitly.
* The architecture should support maintainability.
* Private business data must be protected by server-side authentication, tenant isolation, and permission checks.
* Critical commands and asynchronous consumers must tolerate safe retries without duplicate effects.
* Public API representations must be intentionally separated from internal operational schemas.

## Author

This project is being developed as part of a professional learning process focused on full-stack development and software architecture.
