import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient


def create_organization(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Inventory Organization",
            "slug": f"inventory-{uuid.uuid4().hex}",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_product(
    client: TestClient,
    organization_id: object,
    *,
    sku: str = "ITEM-001",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/products/",
        json={
            "organization_id": organization_id,
            "sku": sku,
            "name": "Inventory Item",
            "price": "10.00",
            "currency": "USD",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_warehouse(
    client: TestClient,
    organization_id: object,
    *,
    code: str = "MAIN",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/warehouses/",
        json={
            "organization_id": organization_id,
            "code": code,
            "name": "Main Warehouse",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_inventory_resources(
    client: TestClient,
) -> tuple[dict[str, object], dict[str, object]]:
    organization = create_organization(client)
    product = create_product(client, organization["id"])
    warehouse = create_warehouse(client, organization["id"])
    return product, warehouse


def adjust_inventory(
    client: TestClient,
    product_id: object,
    warehouse_id: object,
    quantity_delta: int,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "quantity_delta": quantity_delta,
            "reason": "Initial inventory count",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_reservation(
    client: TestClient,
    product_id: object,
    warehouse_id: object,
    quantity: int,
    *,
    external_reference: str | None = None,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/inventory/reservations",
        json={
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "quantity": quantity,
            "external_reference": external_reference,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_adjust_inventory_creates_level_and_movement(client: TestClient) -> None:
    product, warehouse = create_inventory_resources(client)

    body = adjust_inventory(client, product["id"], warehouse["id"], 25)

    assert body["level"]["quantity"] == 25
    assert body["movement"]["quantity_delta"] == 25
    assert body["movement"]["resulting_quantity"] == 25
    assert body["movement"]["inventory_level_id"] == body["level"]["id"]


def test_adjust_inventory_updates_existing_level(client: TestClient) -> None:
    product, warehouse = create_inventory_resources(client)
    adjust_inventory(client, product["id"], warehouse["id"], 25)

    body = adjust_inventory(client, product["id"], warehouse["id"], -10)

    assert body["level"]["quantity"] == 15
    assert body["movement"]["resulting_quantity"] == 15


def test_reject_adjustment_that_would_make_inventory_negative(
    client: TestClient,
) -> None:
    product, warehouse = create_inventory_resources(client)

    response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": product["id"],
            "warehouse_id": warehouse["id"],
            "quantity_delta": -1,
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Inventory quantity cannot become negative"}


def test_reject_product_and_warehouse_from_different_organizations(
    client: TestClient,
) -> None:
    first_organization = create_organization(client)
    second_organization = create_organization(client)
    product = create_product(client, first_organization["id"])
    warehouse = create_warehouse(client, second_organization["id"])

    response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": product["id"],
            "warehouse_id": warehouse["id"],
            "quantity_delta": 5,
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Product and warehouse belong to different organizations"
    }


@pytest.mark.parametrize("inactive_resource", ["product", "warehouse"])
def test_reject_inactive_inventory_resource(
    client: TestClient,
    inactive_resource: str,
) -> None:
    product, warehouse = create_inventory_resources(client)
    resource = product if inactive_resource == "product" else warehouse
    client.post(f"/api/v1/{inactive_resource}s/{resource['id']}/deactivate")

    response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": product["id"],
            "warehouse_id": warehouse["id"],
            "quantity_delta": 5,
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": f"{inactive_resource.title()} is inactive"}


def test_reject_zero_quantity_delta(client: TestClient) -> None:
    product, warehouse = create_inventory_resources(client)

    response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": product["id"],
            "warehouse_id": warehouse["id"],
            "quantity_delta": 0,
        },
    )

    assert response.status_code == 422


def test_get_and_list_inventory_levels(client: TestClient) -> None:
    organization = create_organization(client)
    warehouse = create_warehouse(client, organization["id"])
    first_product = create_product(client, organization["id"], sku="ITEM-001")
    second_product = create_product(client, organization["id"], sku="ITEM-002")
    adjust_inventory(client, first_product["id"], warehouse["id"], 10)
    adjust_inventory(client, second_product["id"], warehouse["id"], 20)

    list_response = client.get(
        "/api/v1/inventory/levels",
        params={"warehouse_id": warehouse["id"], "limit": 1, "offset": 0},
    )
    get_response = client.get(
        f"/api/v1/inventory/levels/{warehouse['id']}/{first_product['id']}"
    )

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 2
    assert len(list_response.json()["items"]) == 1
    assert get_response.status_code == 200
    assert get_response.json()["quantity"] == 10


def test_list_stock_movements_by_inventory_level(client: TestClient) -> None:
    product, warehouse = create_inventory_resources(client)
    first_adjustment = adjust_inventory(client, product["id"], warehouse["id"], 25)
    adjust_inventory(client, product["id"], warehouse["id"], -5)

    response = client.get(
        "/api/v1/inventory/movements",
        params={"inventory_level_id": first_adjustment["level"]["id"]},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert sorted(item["resulting_quantity"] for item in response.json()["items"]) == [
        20,
        25,
    ]


def test_filter_stock_movements_by_warehouse_product_and_date(
    client: TestClient,
) -> None:
    organization = create_organization(client)
    first_warehouse = create_warehouse(client, organization["id"], code="FIRST")
    second_warehouse = create_warehouse(client, organization["id"], code="SECOND")
    first_product = create_product(client, organization["id"], sku="ITEM-001")
    second_product = create_product(client, organization["id"], sku="ITEM-002")
    adjust_inventory(client, first_product["id"], first_warehouse["id"], 10)
    adjust_inventory(client, second_product["id"], first_warehouse["id"], 20)
    adjust_inventory(client, first_product["id"], second_warehouse["id"], 30)

    response = client.get(
        "/api/v1/inventory/movements",
        params={
            "warehouse_id": first_warehouse["id"],
            "product_id": first_product["id"],
            "created_from": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "created_to": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["resulting_quantity"] == 10


def test_paginate_stock_movements(client: TestClient) -> None:
    product, warehouse = create_inventory_resources(client)
    adjust_inventory(client, product["id"], warehouse["id"], 10)
    adjust_inventory(client, product["id"], warehouse["id"], 5)
    adjust_inventory(client, product["id"], warehouse["id"], -2)

    full_response = client.get("/api/v1/inventory/movements")
    response = client.get(
        "/api/v1/inventory/movements",
        params={"limit": 1, "offset": 1},
    )

    assert full_response.status_code == 200
    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert response.json()["limit"] == 1
    assert response.json()["offset"] == 1
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["id"] == full_response.json()["items"][1]["id"]


def test_reject_invalid_stock_movement_date_range(client: TestClient) -> None:
    now = datetime.now(UTC)

    response = client.get(
        "/api/v1/inventory/movements",
        params={
            "created_from": (now + timedelta(days=1)).isoformat(),
            "created_to": now.isoformat(),
        },
    )

    assert response.status_code == 422


def test_create_inventory_reservation_reduces_available_quantity(
    client: TestClient,
) -> None:
    product, warehouse = create_inventory_resources(client)
    adjust_inventory(client, product["id"], warehouse["id"], 20)

    body = create_reservation(
        client,
        product["id"],
        warehouse["id"],
        8,
        external_reference="cart-123",
    )

    assert body["reservation"]["status"] == "active"
    assert body["reservation"]["external_reference"] == "cart-123"
    assert body["level"]["quantity"] == 20
    assert body["level"]["reserved_quantity"] == 8
    assert body["level"]["available_quantity"] == 12


def test_reject_reservation_above_available_quantity(client: TestClient) -> None:
    product, warehouse = create_inventory_resources(client)
    adjust_inventory(client, product["id"], warehouse["id"], 10)
    create_reservation(client, product["id"], warehouse["id"], 6)

    response = client.post(
        "/api/v1/inventory/reservations",
        json={
            "product_id": product["id"],
            "warehouse_id": warehouse["id"],
            "quantity": 5,
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Insufficient available inventory"}


def test_release_inventory_reservation_restores_availability(
    client: TestClient,
) -> None:
    product, warehouse = create_inventory_resources(client)
    adjust_inventory(client, product["id"], warehouse["id"], 10)
    reservation = create_reservation(client, product["id"], warehouse["id"], 4)

    response = client.post(
        f"/api/v1/inventory/reservations/{reservation['reservation']['id']}/release"
    )
    repeated_response = client.post(
        f"/api/v1/inventory/reservations/{reservation['reservation']['id']}/release"
    )

    assert response.status_code == 200
    assert response.json()["reservation"]["status"] == "released"
    assert response.json()["level"]["reserved_quantity"] == 0
    assert response.json()["level"]["available_quantity"] == 10
    assert repeated_response.status_code == 409


def test_consume_inventory_reservation_updates_stock_and_creates_movement(
    client: TestClient,
) -> None:
    product, warehouse = create_inventory_resources(client)
    adjust_inventory(client, product["id"], warehouse["id"], 10)
    reservation = create_reservation(client, product["id"], warehouse["id"], 4)

    response = client.post(
        f"/api/v1/inventory/reservations/{reservation['reservation']['id']}/consume"
    )

    assert response.status_code == 200
    assert response.json()["reservation"]["status"] == "consumed"
    assert response.json()["level"]["quantity"] == 6
    assert response.json()["level"]["reserved_quantity"] == 0
    assert response.json()["level"]["available_quantity"] == 6
    assert response.json()["movement"]["quantity_delta"] == -4
    assert response.json()["movement"]["resulting_quantity"] == 6


def test_reject_adjustment_that_would_reduce_reserved_stock(
    client: TestClient,
) -> None:
    product, warehouse = create_inventory_resources(client)
    adjust_inventory(client, product["id"], warehouse["id"], 10)
    create_reservation(client, product["id"], warehouse["id"], 8)

    response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": product["id"],
            "warehouse_id": warehouse["id"],
            "quantity_delta": -3,
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Insufficient available inventory"}


def test_get_and_filter_inventory_reservations(client: TestClient) -> None:
    organization = create_organization(client)
    warehouse = create_warehouse(client, organization["id"])
    first_product = create_product(client, organization["id"], sku="ITEM-001")
    second_product = create_product(client, organization["id"], sku="ITEM-002")
    adjust_inventory(client, first_product["id"], warehouse["id"], 10)
    adjust_inventory(client, second_product["id"], warehouse["id"], 10)
    first_reservation = create_reservation(
        client, first_product["id"], warehouse["id"], 2
    )
    create_reservation(client, second_product["id"], warehouse["id"], 3)

    list_response = client.get(
        "/api/v1/inventory/reservations",
        params={
            "warehouse_id": warehouse["id"],
            "product_id": first_product["id"],
            "status": "active",
        },
    )
    get_response = client.get(
        f"/api/v1/inventory/reservations/{first_reservation['reservation']['id']}"
    )

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["items"][0]["quantity"] == 2
    assert get_response.status_code == 200
    assert get_response.json()["id"] == first_reservation["reservation"]["id"]


def test_reject_non_positive_reservation_quantity(client: TestClient) -> None:
    product, warehouse = create_inventory_resources(client)

    response = client.post(
        "/api/v1/inventory/reservations",
        json={
            "product_id": product["id"],
            "warehouse_id": warehouse["id"],
            "quantity": 0,
        },
    )

    assert response.status_code == 422
