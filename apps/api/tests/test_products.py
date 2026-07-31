import uuid
from decimal import Decimal

from fastapi.testclient import TestClient


def build_organization_payload() -> dict[str, str]:
    unique_value = uuid.uuid4().hex

    return {
        "name": f"Test Organization {unique_value}",
        "slug": f"test-organization-{unique_value}",
    }


def create_organization(
    client: TestClient,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/organizations/",
        json=build_organization_payload(),
    )

    assert response.status_code == 201

    return response.json()


def build_product_payload(
    organization_id: str,
    sku: str | None = None,
) -> dict[str, object]:
    return {
        "organization_id": organization_id,
        "sku": sku or f"PRODUCT-{uuid.uuid4().hex.upper()}",
        "name": "Test Product",
        "description": "Product created during an automated test.",
        "price": 1299.99,
        "currency": "USD",
    }


def create_product(
    client: TestClient,
    organization_id: str,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/products/",
        json=build_product_payload(organization_id),
    )

    assert response.status_code == 201

    return response.json()


def test_create_product(client: TestClient) -> None:
    organization = create_organization(client)
    payload = build_product_payload(str(organization["id"]))

    response = client.post(
        "/api/v1/products/",
        json=payload,
    )

    assert response.status_code == 201

    body = response.json()

    assert body["organization_id"] == organization["id"]
    assert body["sku"] == payload["sku"]
    assert body["name"] == payload["name"]
    assert Decimal(body["price"]) == Decimal("1299.99")
    assert body["currency"] == "USD"
    assert body["is_active"] is True


def test_reject_duplicate_sku_in_same_organization(
    client: TestClient,
) -> None:
    organization = create_organization(client)
    organization_id = str(organization["id"])
    sku = "DUPLICATE-001"

    first_response = client.post(
        "/api/v1/products/",
        json=build_product_payload(organization_id, sku),
    )

    second_response = client.post(
        "/api/v1/products/",
        json=build_product_payload(organization_id, sku),
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {
        "detail": "Product SKU already exists for this organization",
    }


def test_allow_same_sku_in_different_organizations(
    client: TestClient,
) -> None:
    first_organization = create_organization(client)
    second_organization = create_organization(client)
    sku = "SHARED-001"

    first_response = client.post(
        "/api/v1/products/",
        json=build_product_payload(
            str(first_organization["id"]),
            sku,
        ),
    )

    second_response = client.post(
        "/api/v1/products/",
        json=build_product_payload(
            str(second_organization["id"]),
            sku,
        ),
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201


def test_reject_product_for_unknown_organization(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/products/",
        json=build_product_payload(str(uuid.uuid4())),
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Organization not found",
    }


def test_reject_product_for_inactive_organization(
    client: TestClient,
) -> None:
    organization = create_organization(client)
    organization_id = str(organization["id"])

    deactivate_response = client.post(
        f"/api/v1/organizations/{organization_id}/deactivate",
    )

    response = client.post(
        "/api/v1/products/",
        json=build_product_payload(organization_id),
    )

    assert deactivate_response.status_code == 200
    assert response.status_code == 409
    assert response.json() == {
        "detail": "Organization is inactive",
    }


def test_list_products_by_organization(
    client: TestClient,
) -> None:
    first_organization = create_organization(client)
    second_organization = create_organization(client)

    first_product = create_product(
        client,
        str(first_organization["id"]),
    )

    create_product(
        client,
        str(second_organization["id"]),
    )

    response = client.get(
        "/api/v1/products/",
        params={
            "organization_id": first_organization["id"],
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == first_product["id"]
    assert body["limit"] == 20
    assert body["offset"] == 0


def test_get_and_update_product(client: TestClient) -> None:
    organization = create_organization(client)
    product = create_product(
        client,
        str(organization["id"]),
    )

    get_response = client.get(
        f"/api/v1/products/{product['id']}",
    )

    update_response = client.patch(
        f"/api/v1/products/{product['id']}",
        json={
            "name": "Updated Test Product",
            "price": 1499.99,
            "description": None,
        },
    )

    assert get_response.status_code == 200
    assert get_response.json()["id"] == product["id"]

    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Updated Test Product"
    assert Decimal(update_response.json()["price"]) == Decimal("1499.99")
    assert update_response.json()["description"] is None


def test_deactivate_product(client: TestClient) -> None:
    organization = create_organization(client)
    product = create_product(
        client,
        str(organization["id"]),
    )

    endpoint = f"/api/v1/products/{product['id']}/deactivate"

    first_response = client.post(endpoint)
    second_response = client.post(endpoint)

    assert first_response.status_code == 200
    assert first_response.json()["is_active"] is False

    assert second_response.status_code == 200
    assert second_response.json()["is_active"] is False


def test_get_unknown_product(client: TestClient) -> None:
    response = client.get(
        f"/api/v1/products/{uuid.uuid4()}",
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Product not found",
    }


def test_search_products(client: TestClient) -> None:
    organization = create_organization(client)
    organization_id = str(organization["id"])

    keyboard_payload = build_product_payload(
        organization_id,
        "KEYBOARD-001",
    )
    keyboard_payload["name"] = "Industrial Keyboard"

    monitor_payload = build_product_payload(
        organization_id,
        "MONITOR-001",
    )
    monitor_payload["name"] = "Business Monitor"

    client.post("/api/v1/products/", json=keyboard_payload)
    client.post("/api/v1/products/", json=monitor_payload)

    response = client.get(
        "/api/v1/products/",
        params={
            "organization_id": organization_id,
            "search": "keyboard",
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["sku"] == "KEYBOARD-001"


def test_filter_products_by_status(
    client: TestClient,
) -> None:
    organization = create_organization(client)
    organization_id = str(organization["id"])

    active_product = create_product(
        client,
        organization_id,
    )
    inactive_product = create_product(
        client,
        organization_id,
    )

    client.post(f"/api/v1/products/{inactive_product['id']}/deactivate")

    response = client.get(
        "/api/v1/products/",
        params={
            "organization_id": organization_id,
            "is_active": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == active_product["id"]


def test_paginate_products(client: TestClient) -> None:
    organization = create_organization(client)
    organization_id = str(organization["id"])

    for _ in range(3):
        create_product(client, organization_id)

    first_page = client.get(
        "/api/v1/products/",
        params={
            "organization_id": organization_id,
            "limit": 2,
            "offset": 0,
        },
    )

    second_page = client.get(
        "/api/v1/products/",
        params={
            "organization_id": organization_id,
            "limit": 2,
            "offset": 2,
        },
    )

    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert len(first_page.json()["items"]) == 2

    assert second_page.status_code == 200
    assert second_page.json()["total"] == 3
    assert len(second_page.json()["items"]) == 1
