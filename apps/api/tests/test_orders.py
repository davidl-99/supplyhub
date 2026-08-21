import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.identity import OrganizationMembership, User


def create_organization(
    client: TestClient,
    organization_type: str,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": f"Order {organization_type.title()} Organization",
            "slug": f"order-{organization_type}-{uuid.uuid4().hex}",
            "organization_type": organization_type,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_catalog_manager_headers(
    db_session: Session,
    organization_id: object,
) -> dict[str, str]:
    user = User(
        email=f"order-product-user-{uuid.uuid4().hex}@example.com",
        full_name="Order Product Test User",
        password_hash="not-used-by-order-tests",
    )
    db_session.add(user)
    db_session.flush()
    membership = OrganizationMembership(
        organization_id=uuid.UUID(str(organization_id)),
        user_id=user.id,
        role="catalog_manager",
    )
    db_session.add(membership)
    db_session.commit()
    return {
        "Authorization": f"Bearer {create_access_token(user.id)}",
    }


def create_product(
    client: TestClient,
    db_session: Session,
    organization_id: object,
    *,
    sku: str,
    price: str = "25.00",
) -> dict[str, object]:
    headers = create_catalog_manager_headers(db_session, organization_id)
    response = client.post(
        "/api/v1/products/",
        json={
            "organization_id": organization_id,
            "sku": sku,
            "name": f"Order Product {sku}",
            "price": price,
            "currency": "USD",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def create_warehouse(
    client: TestClient,
    organization_id: object,
    *,
    code: str = "ORDER-WH",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/warehouses/",
        json={
            "organization_id": organization_id,
            "code": code,
            "name": f"Order Warehouse {code}",
        },
    )
    assert response.status_code == 201
    return response.json()


def adjust_inventory(
    client: TestClient,
    product_id: object,
    warehouse_id: object,
    quantity: int,
) -> None:
    response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "quantity_delta": quantity,
        },
    )
    assert response.status_code == 201


def create_order_resources(
    client: TestClient,
    db_session: Session,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    buyer = create_organization(client, "buyer")
    supplier = create_organization(client, "supplier")
    product = create_product(client, db_session, supplier["id"], sku="ORDER-001")
    warehouse = create_warehouse(client, supplier["id"])
    return buyer, supplier, product, warehouse


def create_order(
    client: TestClient,
    buyer_id: object,
    supplier_id: object,
    lines: list[dict[str, object]],
) -> dict[str, object]:
    response = client.post(
        "/api/v1/orders/",
        json={
            "buyer_organization_id": buyer_id,
            "supplier_organization_id": supplier_id,
            "lines": lines,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_draft_order_with_price_snapshot(
    client: TestClient,
    db_session: Session,
) -> None:
    buyer, supplier, product, warehouse = create_order_resources(client, db_session)

    body = create_order(
        client,
        buyer["id"],
        supplier["id"],
        [{"product_id": product["id"], "warehouse_id": warehouse["id"], "quantity": 3}],
    )

    assert body["status"] == "draft"
    assert body["currency"] == "USD"
    assert Decimal(body["total"]) == Decimal("75.00")
    assert body["lines"][0]["product_sku"] == "ORDER-001"
    assert Decimal(body["lines"][0]["unit_price"]) == Decimal("25.00")
    assert body["lines"][0]["reservation_id"] is None


def test_order_price_snapshot_survives_product_update(
    client: TestClient,
    db_session: Session,
) -> None:
    buyer, supplier, product, warehouse = create_order_resources(client, db_session)
    order = create_order(
        client,
        buyer["id"],
        supplier["id"],
        [{"product_id": product["id"], "warehouse_id": warehouse["id"], "quantity": 1}],
    )

    update_response = client.patch(
        f"/api/v1/products/{product['id']}",
        json={"price": "99.00"},
        headers=create_catalog_manager_headers(
            db_session,
            product["organization_id"],
        ),
    )
    get_response = client.get(f"/api/v1/orders/{order['id']}")

    assert update_response.status_code == 200
    assert Decimal(get_response.json()["lines"][0]["unit_price"]) == Decimal("25.00")


def test_reject_invalid_order_organization_capabilities(
    client: TestClient,
    db_session: Session,
) -> None:
    supplier = create_organization(client, "supplier")
    product = create_product(client, db_session, supplier["id"], sku="ROLE-001")
    warehouse = create_warehouse(client, supplier["id"], code="ROLE-WH")

    response = client.post(
        "/api/v1/orders/",
        json={
            "buyer_organization_id": supplier["id"],
            "supplier_organization_id": create_organization(client, "buyer")["id"],
            "lines": [
                {
                    "product_id": product["id"],
                    "warehouse_id": warehouse["id"],
                    "quantity": 1,
                }
            ],
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Buyer organization cannot buy"}


def test_place_order_creates_inventory_reservation(
    client: TestClient,
    db_session: Session,
) -> None:
    buyer, supplier, product, warehouse = create_order_resources(client, db_session)
    adjust_inventory(client, product["id"], warehouse["id"], 10)
    order = create_order(
        client,
        buyer["id"],
        supplier["id"],
        [{"product_id": product["id"], "warehouse_id": warehouse["id"], "quantity": 4}],
    )

    response = client.post(f"/api/v1/orders/{order['id']}/place")
    level_response = client.get(
        f"/api/v1/inventory/levels/{warehouse['id']}/{product['id']}"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "placed"
    assert response.json()["placed_at"] is not None
    assert response.json()["lines"][0]["reservation_id"] is not None
    assert level_response.json()["quantity"] == 10
    assert level_response.json()["reserved_quantity"] == 4
    assert level_response.json()["available_quantity"] == 6


def test_place_order_rolls_back_all_lines_when_inventory_is_insufficient(
    client: TestClient,
    db_session: Session,
) -> None:
    buyer = create_organization(client, "buyer")
    supplier = create_organization(client, "supplier")
    warehouse = create_warehouse(client, supplier["id"], code="ATOMIC-WH")
    first_product = create_product(client, db_session, supplier["id"], sku="ATOMIC-001")
    second_product = create_product(
        client, db_session, supplier["id"], sku="ATOMIC-002"
    )
    adjust_inventory(client, first_product["id"], warehouse["id"], 10)
    adjust_inventory(client, second_product["id"], warehouse["id"], 1)
    order = create_order(
        client,
        buyer["id"],
        supplier["id"],
        [
            {
                "product_id": first_product["id"],
                "warehouse_id": warehouse["id"],
                "quantity": 4,
            },
            {
                "product_id": second_product["id"],
                "warehouse_id": warehouse["id"],
                "quantity": 2,
            },
        ],
    )

    response = client.post(f"/api/v1/orders/{order['id']}/place")
    first_level = client.get(
        f"/api/v1/inventory/levels/{warehouse['id']}/{first_product['id']}"
    ).json()
    order_response = client.get(f"/api/v1/orders/{order['id']}")

    assert response.status_code == 409
    assert first_level["reserved_quantity"] == 0
    assert order_response.json()["status"] == "draft"
    assert all(
        line["reservation_id"] is None for line in order_response.json()["lines"]
    )


def test_cancel_placed_order_releases_reservations(
    client: TestClient,
    db_session: Session,
) -> None:
    buyer, supplier, product, warehouse = create_order_resources(client, db_session)
    adjust_inventory(client, product["id"], warehouse["id"], 10)
    order = create_order(
        client,
        buyer["id"],
        supplier["id"],
        [{"product_id": product["id"], "warehouse_id": warehouse["id"], "quantity": 4}],
    )
    client.post(f"/api/v1/orders/{order['id']}/place")

    response = client.post(f"/api/v1/orders/{order['id']}/cancel")
    repeated_response = client.post(f"/api/v1/orders/{order['id']}/cancel")
    level_response = client.get(
        f"/api/v1/inventory/levels/{warehouse['id']}/{product['id']}"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancelled_at"] is not None
    assert repeated_response.status_code == 200
    assert level_response.json()["reserved_quantity"] == 0


def test_list_orders_by_buyer_and_status(
    client: TestClient,
    db_session: Session,
) -> None:
    buyer, supplier, product, warehouse = create_order_resources(client, db_session)
    order = create_order(
        client,
        buyer["id"],
        supplier["id"],
        [{"product_id": product["id"], "warehouse_id": warehouse["id"], "quantity": 1}],
    )

    response = client.get(
        "/api/v1/orders/",
        params={"buyer_organization_id": buyer["id"], "status": "draft"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == order["id"]


def test_fulfill_order_consumes_reservation_and_creates_movement(
    client: TestClient,
    db_session: Session,
) -> None:
    buyer, supplier, product, warehouse = create_order_resources(client, db_session)
    adjust_inventory(client, product["id"], warehouse["id"], 10)
    order = create_order(
        client,
        buyer["id"],
        supplier["id"],
        [
            {
                "product_id": product["id"],
                "warehouse_id": warehouse["id"],
                "quantity": 4,
            }
        ],
    )
    placed_order = client.post(f"/api/v1/orders/{order['id']}/place").json()
    reservation_id = placed_order["lines"][0]["reservation_id"]

    response = client.post(f"/api/v1/orders/{order['id']}/fulfill")
    level_response = client.get(
        f"/api/v1/inventory/levels/{warehouse['id']}/{product['id']}"
    )
    reservation_response = client.get(
        f"/api/v1/inventory/reservations/{reservation_id}"
    )
    movements_response = client.get(
        "/api/v1/inventory/movements",
        params={"warehouse_id": warehouse["id"], "product_id": product["id"]},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "fulfilled"
    assert response.json()["fulfilled_at"] is not None
    assert level_response.json()["quantity"] == 6
    assert level_response.json()["reserved_quantity"] == 0
    assert level_response.json()["available_quantity"] == 6
    assert reservation_response.json()["status"] == "consumed"
    fulfillment_movement = next(
        item
        for item in movements_response.json()["items"]
        if item["quantity_delta"] == -4
    )
    assert fulfillment_movement["resulting_quantity"] == 6
    assert fulfillment_movement["reason"].startswith("Fulfilled order")


def test_reject_fulfillment_for_draft_order(
    client: TestClient,
    db_session: Session,
) -> None:
    buyer, supplier, product, warehouse = create_order_resources(client, db_session)
    order = create_order(
        client,
        buyer["id"],
        supplier["id"],
        [
            {
                "product_id": product["id"],
                "warehouse_id": warehouse["id"],
                "quantity": 1,
            }
        ],
    )

    response = client.post(f"/api/v1/orders/{order['id']}/fulfill")

    assert response.status_code == 409
    assert response.json() == {"detail": "Order is not placed"}


def test_reject_cancellation_for_fulfilled_order(
    client: TestClient,
    db_session: Session,
) -> None:
    buyer, supplier, product, warehouse = create_order_resources(client, db_session)
    adjust_inventory(client, product["id"], warehouse["id"], 5)
    order = create_order(
        client,
        buyer["id"],
        supplier["id"],
        [
            {
                "product_id": product["id"],
                "warehouse_id": warehouse["id"],
                "quantity": 2,
            }
        ],
    )
    client.post(f"/api/v1/orders/{order['id']}/place")
    client.post(f"/api/v1/orders/{order['id']}/fulfill")

    response = client.post(f"/api/v1/orders/{order['id']}/cancel")

    assert response.status_code == 409
    assert response.json() == {"detail": "Fulfilled orders cannot be cancelled"}


def test_order_history_records_full_lifecycle(
    client: TestClient,
    db_session: Session,
) -> None:
    buyer, supplier, product, warehouse = create_order_resources(client, db_session)
    adjust_inventory(client, product["id"], warehouse["id"], 5)
    order = create_order(
        client,
        buyer["id"],
        supplier["id"],
        [
            {
                "product_id": product["id"],
                "warehouse_id": warehouse["id"],
                "quantity": 2,
            }
        ],
    )
    client.post(f"/api/v1/orders/{order['id']}/place")
    client.post(f"/api/v1/orders/{order['id']}/fulfill")

    response = client.get(f"/api/v1/orders/{order['id']}/history")

    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert [
        (event["from_status"], event["to_status"]) for event in response.json()["items"]
    ] == [
        (None, "draft"),
        ("draft", "placed"),
        ("placed", "fulfilled"),
    ]


def test_cancelled_order_history_is_append_only_and_paginated(
    client: TestClient,
    db_session: Session,
) -> None:
    buyer, supplier, product, warehouse = create_order_resources(client, db_session)
    order = create_order(
        client,
        buyer["id"],
        supplier["id"],
        [
            {
                "product_id": product["id"],
                "warehouse_id": warehouse["id"],
                "quantity": 1,
            }
        ],
    )
    client.post(f"/api/v1/orders/{order['id']}/cancel")
    client.post(f"/api/v1/orders/{order['id']}/cancel")

    response = client.get(
        f"/api/v1/orders/{order['id']}/history",
        params={"limit": 1, "offset": 1},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["limit"] == 1
    assert response.json()["offset"] == 1
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["from_status"] == "draft"
    assert response.json()["items"][0]["to_status"] == "cancelled"


def test_get_history_for_unknown_order(client: TestClient) -> None:
    response = client.get(f"/api/v1/orders/{uuid.uuid4()}/history")

    assert response.status_code == 404
    assert response.json() == {"detail": "Order not found"}
