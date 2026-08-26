import uuid
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.identity import OrganizationMembership, User


class InventoryContext(NamedTuple):
    organization_id: str
    product: dict[str, object]
    warehouse: dict[str, object]
    headers: dict[str, str]


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


def create_user(db_session: Session) -> User:
    user = User(
        email=f"inventory-user-{uuid.uuid4().hex}@example.com",
        full_name="Inventory Test User",
        password_hash="not-used-by-inventory-tests",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def authorization_headers(user_id: object) -> dict[str, str]:
    token = create_access_token(uuid.UUID(str(user_id)))
    return {"Authorization": f"Bearer {token}"}


def create_inventory_actor(
    _client: TestClient,
    db_session: Session,
    organization_id: object,
    *,
    role: str = "organization_admin",
    is_active: bool = True,
) -> dict[str, str]:
    user = create_user(db_session)
    membership = OrganizationMembership(
        organization_id=uuid.UUID(str(organization_id)),
        user_id=user.id,
        role=role,
        is_active=is_active,
    )
    db_session.add(membership)
    db_session.commit()
    return authorization_headers(user.id)


def create_product(
    client: TestClient,
    organization_id: object,
    headers: dict[str, str],
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
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def create_warehouse(
    client: TestClient,
    organization_id: object,
    headers: dict[str, str],
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
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def create_inventory_resources(
    client: TestClient,
    db_session: Session,
) -> InventoryContext:
    organization = create_organization(client)
    headers = create_inventory_actor(client, db_session, organization["id"])
    product = create_product(client, organization["id"], headers)
    warehouse = create_warehouse(client, organization["id"], headers)
    return InventoryContext(
        organization_id=str(organization["id"]),
        product=product,
        warehouse=warehouse,
        headers=headers,
    )


def adjust_inventory(
    client: TestClient,
    product_id: object,
    warehouse_id: object,
    quantity_delta: int,
    headers: dict[str, str],
) -> dict[str, object]:
    response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "quantity_delta": quantity_delta,
            "reason": "Initial inventory count",
        },
        headers=headers,
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


def test_adjust_inventory_creates_level_and_movement(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)

    body = adjust_inventory(
        client,
        context.product["id"],
        context.warehouse["id"],
        25,
        context.headers,
    )

    assert body["level"]["quantity"] == 25
    assert body["movement"]["quantity_delta"] == 25
    assert body["movement"]["resulting_quantity"] == 25
    assert body["movement"]["inventory_level_id"] == body["level"]["id"]


def test_adjust_inventory_updates_existing_level(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)
    adjust_inventory(
        client,
        context.product["id"],
        context.warehouse["id"],
        25,
        context.headers,
    )

    body = adjust_inventory(
        client,
        context.product["id"],
        context.warehouse["id"],
        -10,
        context.headers,
    )

    assert body["level"]["quantity"] == 15
    assert body["movement"]["resulting_quantity"] == 15


def test_reject_adjustment_that_would_make_inventory_negative(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)

    response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": context.product["id"],
            "warehouse_id": context.warehouse["id"],
            "quantity_delta": -1,
        },
        headers=context.headers,
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Inventory quantity cannot become negative"}


def test_conceal_product_from_another_organization_on_adjustment(
    client: TestClient,
    db_session: Session,
) -> None:
    product_organization = create_organization(client)
    warehouse_organization = create_organization(client)
    product_headers = create_inventory_actor(
        client,
        db_session,
        product_organization["id"],
    )
    warehouse_headers = create_inventory_actor(
        client,
        db_session,
        warehouse_organization["id"],
    )
    product = create_product(client, product_organization["id"], product_headers)
    warehouse = create_warehouse(
        client,
        warehouse_organization["id"],
        warehouse_headers,
    )

    response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": product["id"],
            "warehouse_id": warehouse["id"],
            "quantity_delta": 5,
        },
        headers=warehouse_headers,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Product not found"}


@pytest.mark.parametrize("inactive_resource", ["product", "warehouse"])
def test_reject_inactive_inventory_resource(
    client: TestClient,
    db_session: Session,
    inactive_resource: str,
) -> None:
    context = create_inventory_resources(client, db_session)
    resource = context.product if inactive_resource == "product" else context.warehouse
    client.post(
        f"/api/v1/{inactive_resource}s/{resource['id']}/deactivate",
        headers=context.headers,
    )

    response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": context.product["id"],
            "warehouse_id": context.warehouse["id"],
            "quantity_delta": 5,
        },
        headers=context.headers,
    )

    assert response.status_code == 409
    assert response.json() == {"detail": f"{inactive_resource.title()} is inactive"}


def test_reject_zero_quantity_delta(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)

    response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": context.product["id"],
            "warehouse_id": context.warehouse["id"],
            "quantity_delta": 0,
        },
        headers=context.headers,
    )

    assert response.status_code == 422


def test_get_and_list_inventory_levels(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    headers = create_inventory_actor(client, db_session, organization["id"])
    warehouse = create_warehouse(client, organization["id"], headers)
    first_product = create_product(client, organization["id"], headers, sku="ITEM-001")
    second_product = create_product(client, organization["id"], headers, sku="ITEM-002")
    adjust_inventory(client, first_product["id"], warehouse["id"], 10, headers)
    adjust_inventory(client, second_product["id"], warehouse["id"], 20, headers)

    list_response = client.get(
        "/api/v1/inventory/levels",
        params={
            "organization_id": organization["id"],
            "warehouse_id": warehouse["id"],
            "limit": 1,
            "offset": 0,
        },
        headers=headers,
    )
    get_response = client.get(
        f"/api/v1/inventory/levels/{warehouse['id']}/{first_product['id']}",
        headers=headers,
    )

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 2
    assert len(list_response.json()["items"]) == 1
    assert get_response.status_code == 200
    assert get_response.json()["quantity"] == 10


def test_list_stock_movements_by_inventory_level(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)
    first_adjustment = adjust_inventory(
        client,
        context.product["id"],
        context.warehouse["id"],
        25,
        context.headers,
    )
    adjust_inventory(
        client,
        context.product["id"],
        context.warehouse["id"],
        -5,
        context.headers,
    )

    response = client.get(
        "/api/v1/inventory/movements",
        params={
            "organization_id": context.organization_id,
            "inventory_level_id": first_adjustment["level"]["id"],
        },
        headers=context.headers,
    )

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert sorted(item["resulting_quantity"] for item in response.json()["items"]) == [
        20,
        25,
    ]


def test_filter_stock_movements_by_warehouse_product_and_date(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    headers = create_inventory_actor(client, db_session, organization["id"])
    first_warehouse = create_warehouse(
        client, organization["id"], headers, code="FIRST"
    )
    second_warehouse = create_warehouse(
        client, organization["id"], headers, code="SECOND"
    )
    first_product = create_product(client, organization["id"], headers, sku="ITEM-001")
    second_product = create_product(client, organization["id"], headers, sku="ITEM-002")
    adjust_inventory(client, first_product["id"], first_warehouse["id"], 10, headers)
    adjust_inventory(client, second_product["id"], first_warehouse["id"], 20, headers)
    adjust_inventory(client, first_product["id"], second_warehouse["id"], 30, headers)

    response = client.get(
        "/api/v1/inventory/movements",
        params={
            "organization_id": organization["id"],
            "warehouse_id": first_warehouse["id"],
            "product_id": first_product["id"],
            "created_from": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "created_to": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["resulting_quantity"] == 10


def test_paginate_stock_movements(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)
    for quantity_delta in (10, 5, -2):
        adjust_inventory(
            client,
            context.product["id"],
            context.warehouse["id"],
            quantity_delta,
            context.headers,
        )

    full_response = client.get(
        "/api/v1/inventory/movements",
        params={"organization_id": context.organization_id},
        headers=context.headers,
    )
    response = client.get(
        "/api/v1/inventory/movements",
        params={
            "organization_id": context.organization_id,
            "limit": 1,
            "offset": 1,
        },
        headers=context.headers,
    )

    assert full_response.status_code == 200
    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert response.json()["limit"] == 1
    assert response.json()["offset"] == 1
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["id"] == full_response.json()["items"][1]["id"]


def test_reject_invalid_stock_movement_date_range(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    headers = create_inventory_actor(client, db_session, organization["id"])
    now = datetime.now(UTC)

    response = client.get(
        "/api/v1/inventory/movements",
        params={
            "organization_id": organization["id"],
            "created_from": (now + timedelta(days=1)).isoformat(),
            "created_to": now.isoformat(),
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_create_inventory_reservation_reduces_available_quantity(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)
    adjust_inventory(
        client,
        context.product["id"],
        context.warehouse["id"],
        20,
        context.headers,
    )

    body = create_reservation(
        client,
        context.product["id"],
        context.warehouse["id"],
        8,
        external_reference="cart-123",
    )

    assert body["reservation"]["status"] == "active"
    assert body["reservation"]["external_reference"] == "cart-123"
    assert body["level"]["quantity"] == 20
    assert body["level"]["reserved_quantity"] == 8
    assert body["level"]["available_quantity"] == 12


def test_reject_reservation_above_available_quantity(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)
    adjust_inventory(
        client,
        context.product["id"],
        context.warehouse["id"],
        10,
        context.headers,
    )
    create_reservation(client, context.product["id"], context.warehouse["id"], 6)

    response = client.post(
        "/api/v1/inventory/reservations",
        json={
            "product_id": context.product["id"],
            "warehouse_id": context.warehouse["id"],
            "quantity": 5,
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Insufficient available inventory"}


def test_release_inventory_reservation_restores_availability(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)
    adjust_inventory(
        client,
        context.product["id"],
        context.warehouse["id"],
        10,
        context.headers,
    )
    reservation = create_reservation(
        client, context.product["id"], context.warehouse["id"], 4
    )

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
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)
    adjust_inventory(
        client,
        context.product["id"],
        context.warehouse["id"],
        10,
        context.headers,
    )
    reservation = create_reservation(
        client, context.product["id"], context.warehouse["id"], 4
    )

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
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)
    adjust_inventory(
        client,
        context.product["id"],
        context.warehouse["id"],
        10,
        context.headers,
    )
    create_reservation(client, context.product["id"], context.warehouse["id"], 8)

    response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": context.product["id"],
            "warehouse_id": context.warehouse["id"],
            "quantity_delta": -3,
        },
        headers=context.headers,
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Insufficient available inventory"}


def test_get_and_filter_inventory_reservations(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    headers = create_inventory_actor(client, db_session, organization["id"])
    warehouse = create_warehouse(client, organization["id"], headers)
    first_product = create_product(client, organization["id"], headers, sku="ITEM-001")
    second_product = create_product(client, organization["id"], headers, sku="ITEM-002")
    adjust_inventory(client, first_product["id"], warehouse["id"], 10, headers)
    adjust_inventory(client, second_product["id"], warehouse["id"], 10, headers)
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


def test_reject_non_positive_reservation_quantity(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)

    response = client.post(
        "/api/v1/inventory/reservations",
        json={
            "product_id": context.product["id"],
            "warehouse_id": context.warehouse["id"],
            "quantity": 0,
        },
    )

    assert response.status_code == 422


def test_require_authentication_for_inventory_endpoints(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)

    adjust_response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": context.product["id"],
            "warehouse_id": context.warehouse["id"],
            "quantity_delta": 5,
        },
    )
    levels_response = client.get(
        "/api/v1/inventory/levels",
        params={"organization_id": context.organization_id},
    )
    level_response = client.get(
        f"/api/v1/inventory/levels/{context.warehouse['id']}/{context.product['id']}"
    )
    movements_response = client.get(
        "/api/v1/inventory/movements",
        params={"organization_id": context.organization_id},
    )

    assert adjust_response.status_code == 401
    assert levels_response.status_code == 401
    assert level_response.status_code == 401
    assert movements_response.status_code == 401


def test_require_organization_filter_when_listing_inventory(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    headers = create_inventory_actor(client, db_session, organization["id"])

    levels_response = client.get("/api/v1/inventory/levels", headers=headers)
    movements_response = client.get("/api/v1/inventory/movements", headers=headers)

    assert levels_response.status_code == 422
    assert movements_response.status_code == 422


def test_reject_cross_organization_inventory_collection_access(
    client: TestClient,
    db_session: Session,
) -> None:
    actor_organization = create_organization(client)
    target_organization = create_organization(client)
    actor_headers = create_inventory_actor(
        client,
        db_session,
        actor_organization["id"],
    )

    levels_response = client.get(
        "/api/v1/inventory/levels",
        params={"organization_id": target_organization["id"]},
        headers=actor_headers,
    )
    movements_response = client.get(
        "/api/v1/inventory/movements",
        params={"organization_id": target_organization["id"]},
        headers=actor_headers,
    )

    assert levels_response.status_code == 403
    assert movements_response.status_code == 403
    assert levels_response.json() == {"detail": "Not enough permissions"}
    assert movements_response.json() == {"detail": "Not enough permissions"}


def test_conceal_cross_organization_inventory_write(
    client: TestClient,
    db_session: Session,
) -> None:
    target = create_inventory_resources(client, db_session)
    actor_organization = create_organization(client)
    actor_headers = create_inventory_actor(
        client,
        db_session,
        actor_organization["id"],
    )

    response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": target.product["id"],
            "warehouse_id": target.warehouse["id"],
            "quantity_delta": 5,
        },
        headers=actor_headers,
    )
    unknown_response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": target.product["id"],
            "warehouse_id": str(uuid.uuid4()),
            "quantity_delta": 5,
        },
        headers=actor_headers,
    )

    assert response.status_code == 404
    assert unknown_response.status_code == 404
    assert response.json() == {"detail": "Warehouse not found"}
    assert unknown_response.json() == {"detail": "Warehouse not found"}


def test_conceal_cross_organization_inventory_level(
    client: TestClient,
    db_session: Session,
) -> None:
    target = create_inventory_resources(client, db_session)
    adjust_inventory(
        client,
        target.product["id"],
        target.warehouse["id"],
        10,
        target.headers,
    )
    actor_organization = create_organization(client)
    actor_headers = create_inventory_actor(
        client,
        db_session,
        actor_organization["id"],
    )
    endpoint = (
        f"/api/v1/inventory/levels/{target.warehouse['id']}/{target.product['id']}"
    )

    foreign_response = client.get(endpoint, headers=actor_headers)
    owner_response = client.get(endpoint, headers=target.headers)

    assert foreign_response.status_code == 404
    assert foreign_response.json() == {"detail": "Inventory level not found"}
    assert owner_response.status_code == 200
    assert owner_response.json()["quantity"] == 10


def test_exclude_other_organization_rows_from_inventory_listings(
    client: TestClient,
    db_session: Session,
) -> None:
    actor = create_inventory_resources(client, db_session)
    other = create_inventory_resources(client, db_session)
    adjust_inventory(
        client,
        actor.product["id"],
        actor.warehouse["id"],
        10,
        actor.headers,
    )
    adjust_inventory(
        client,
        other.product["id"],
        other.warehouse["id"],
        20,
        other.headers,
    )

    levels_response = client.get(
        "/api/v1/inventory/levels",
        params={"organization_id": actor.organization_id},
        headers=actor.headers,
    )
    foreign_filter_response = client.get(
        "/api/v1/inventory/levels",
        params={
            "organization_id": actor.organization_id,
            "warehouse_id": other.warehouse["id"],
        },
        headers=actor.headers,
    )
    movements_response = client.get(
        "/api/v1/inventory/movements",
        params={"organization_id": actor.organization_id},
        headers=actor.headers,
    )

    assert levels_response.status_code == 200
    assert levels_response.json()["total"] == 1
    assert levels_response.json()["items"][0]["warehouse_id"] == actor.warehouse["id"]
    assert foreign_filter_response.status_code == 200
    assert foreign_filter_response.json()["total"] == 0
    assert movements_response.status_code == 200
    assert movements_response.json()["total"] == 1


def test_allow_read_but_reject_forbidden_inventory_mutations(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)
    adjust_inventory(
        client,
        context.product["id"],
        context.warehouse["id"],
        10,
        context.headers,
    )
    viewer_headers = create_inventory_actor(
        client,
        db_session,
        context.organization_id,
        role="viewer",
    )

    levels_response = client.get(
        "/api/v1/inventory/levels",
        params={"organization_id": context.organization_id},
        headers=viewer_headers,
    )
    level_response = client.get(
        f"/api/v1/inventory/levels/{context.warehouse['id']}/{context.product['id']}",
        headers=viewer_headers,
    )
    adjust_response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": context.product["id"],
            "warehouse_id": context.warehouse["id"],
            "quantity_delta": 5,
        },
        headers=viewer_headers,
    )

    assert levels_response.status_code == 200
    assert level_response.status_code == 200
    assert adjust_response.status_code == 403
    assert adjust_response.json() == {"detail": "Not enough permissions"}


def test_reject_role_without_inventory_permissions(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)
    catalog_headers = create_inventory_actor(
        client,
        db_session,
        context.organization_id,
        role="catalog_manager",
    )

    levels_response = client.get(
        "/api/v1/inventory/levels",
        params={"organization_id": context.organization_id},
        headers=catalog_headers,
    )
    adjust_response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": context.product["id"],
            "warehouse_id": context.warehouse["id"],
            "quantity_delta": 5,
        },
        headers=catalog_headers,
    )

    assert levels_response.status_code == 403
    assert adjust_response.status_code == 403
    assert levels_response.json() == {"detail": "Not enough permissions"}
    assert adjust_response.json() == {"detail": "Not enough permissions"}


def test_allow_warehouse_operator_to_adjust_inventory(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)
    operator_headers = create_inventory_actor(
        client,
        db_session,
        context.organization_id,
        role="warehouse_operator",
    )

    body = adjust_inventory(
        client,
        context.product["id"],
        context.warehouse["id"],
        7,
        operator_headers,
    )

    assert body["level"]["quantity"] == 7


def test_reject_inactive_membership_for_inventory(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_inventory_resources(client, db_session)
    inactive_headers = create_inventory_actor(
        client,
        db_session,
        context.organization_id,
        is_active=False,
    )

    levels_response = client.get(
        "/api/v1/inventory/levels",
        params={"organization_id": context.organization_id},
        headers=inactive_headers,
    )
    adjust_response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": context.product["id"],
            "warehouse_id": context.warehouse["id"],
            "quantity_delta": 5,
        },
        headers=inactive_headers,
    )

    assert levels_response.status_code == 403
    assert levels_response.json() == {"detail": "Not enough permissions"}
    assert adjust_response.status_code == 404
    assert adjust_response.json() == {"detail": "Warehouse not found"}
