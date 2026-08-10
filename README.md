# SupplyHub

SupplyHub is a B2B platform where supplier organizations can manage their products and inventory, while buyer organizations can search for products and create orders.

## Project status

The backend currently supports typed supplier and buyer organizations, product, warehouse, inventory, and order management, including search, filtering, pagination, soft deactivation, stock levels, auditable stock adjustments, filtered stock movement history, concurrency-safe inventory reservations, immutable order price snapshots, atomic order placement, cancellation, full fulfillment, and append-only order status history. Automated tests run against a dedicated PostgreSQL test database.

## Local development

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

## Initial architecture

The project will begin as a modular monolith.

This means that there will be a single backend application, but it will be internally divided into independent modules.

The initial modules will be:

* Authentication.
* Organizations.
* Users and permissions.
* Catalog.
* Inventory.
* Orders.
* Search.
* Audit.

Microservices will not be used initially because the business rules must first be understood and implemented correctly within an application that is easier to develop, test, and operate.

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
* MongoDB for audit events.
* OpenSearch for advanced product search.

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

### MongoDB

MongoDB will be used to store audit events and operation history.

For example:

* Who modified a product.
* What information changed.
* When the change occurred.
* Which values existed before and after the change.

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

## Initial roadmap

1. Define the product scope.
2. Prepare the repository structure.
3. Create the local environment with Docker.
4. Create the backend application.
5. Connect PostgreSQL.
6. Implement the product module.
7. Create the frontend application.
8. Implement authentication and organizations.
9. Implement inventory management.
10. Implement order management.
11. Integrate OpenSearch.
12. Integrate MongoDB.
13. Add asynchronous processing.
14. Add automated tests.
15. Configure continuous integration and deployment.

## Project principles

* Complexity should only be added when it solves a real problem.
* Every feature should be documented.
* Business rules should have automated tests.
* PostgreSQL will be the primary source of truth.
* Errors should be handled explicitly.
* The architecture should support maintainability.
* Artificial intelligence tools will be used as assistants, not as substitutes for technical understanding.

## Author

This project is being developed as part of a professional learning process focused on full-stack development and software architecture.
