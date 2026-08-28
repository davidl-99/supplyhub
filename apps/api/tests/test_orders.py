import uuid
from decimal import Decimal
from typing import NamedTuple

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.identity import OrganizationMembership, User
from app.modules.orders.repository import OrderRepository


class OrderContext(NamedTuple):
    buyer: dict[str, object]
    supplier: dict[str, object]
    product: dict[str, object]
    warehouse: dict[str, object]
    buyer_headers: dict[str, str]
    supplier_headers: dict[str, str]


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


def create_user(db_session: Session) -> User:
    user = User(
        email=f"order-user-{uuid.uuid4().hex}@example.com",
        full_name="Order Test User",
        password_hash="not-used-by-order-tests",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def authorization_headers(user_id: object) -> dict[str, str]:
    token = create_access_token(uuid.UUID(str(user_id)))
    return {"Authorization": f"Bearer {token}"}


def create_order_actor(
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
    sku: str,
    price: str = "25.00",
) -> dict[str, object]:
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
    headers: dict[str, str],
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
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def adjust_inventory(
    client: TestClient,
    product_id: object,
    warehouse_id: object,
    quantity: int,
    headers: dict[str, str],
) -> None:
    response = client.post(
        "/api/v1/inventory/adjustments",
        json={
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "quantity_delta": quantity,
        },
        headers=headers,
    )
    assert response.status_code == 201


def create_order_resources(
    client: TestClient,
    db_session: Session,
) -> OrderContext:
    buyer = create_organization(client, "buyer")
    supplier = create_organization(client, "supplier")
    buyer_headers = create_order_actor(db_session, buyer["id"])
    supplier_headers = create_order_actor(db_session, supplier["id"])
    product = create_product(client, supplier["id"], supplier_headers, sku="ORDER-001")
    warehouse = create_warehouse(client, supplier["id"], supplier_headers)
    return OrderContext(
        buyer=buyer,
        supplier=supplier,
        product=product,
        warehouse=warehouse,
        buyer_headers=buyer_headers,
        supplier_headers=supplier_headers,
    )


def order_line(context: OrderContext, quantity: int) -> dict[str, object]:
    return {
        "product_id": context.product["id"],
        "warehouse_id": context.warehouse["id"],
        "quantity": quantity,
    }


def create_order(
    client: TestClient,
    buyer_id: object,
    supplier_id: object,
    lines: list[dict[str, object]],
    headers: dict[str, str],
) -> dict[str, object]:
    response = client.post(
        "/api/v1/orders/",
        json={
            "buyer_organization_id": buyer_id,
            "supplier_organization_id": supplier_id,
            "lines": lines,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def create_placed_order(
    client: TestClient,
    context: OrderContext,
    *,
    stock: int = 10,
    quantity: int = 4,
) -> dict[str, object]:
    adjust_inventory(
        client,
        context.product["id"],
        context.warehouse["id"],
        stock,
        context.supplier_headers,
    )
    order = create_order(
        client,
        context.buyer["id"],
        context.supplier["id"],
        [order_line(context, quantity)],
        context.buyer_headers,
    )
    response = client.post(
        f"/api/v1/orders/{order['id']}/place",
        headers=context.buyer_headers,
    )
    assert response.status_code == 200
    return response.json()


def read_level(client: TestClient, context: OrderContext) -> dict[str, object]:
    response = client.get(
        f"/api/v1/inventory/levels/{context.warehouse['id']}/{context.product['id']}",
        headers=context.supplier_headers,
    )
    assert response.status_code == 200
    return response.json()


def test_get_order_for_update_refreshes_stale_identity_map_state(
    client: TestClient,
    db_session: Session,
) -> None:
    """``SELECT ... FOR UPDATE`` must be authoritative even when the order
    is already present, with stale attributes, in the session's identity
    map.

    Without ``populate_existing=True`` on the locking query, SQLAlchemy
    would return the already-cached Python object as-is: the row would be
    locked at the database level, but the caller would still be looking at
    the pre-lock values, silently defeating the point of the lock.
    """
    context = create_order_resources(client, db_session)
    order = create_order(
        client,
        context.buyer["id"],
        context.supplier["id"],
        [order_line(context, 1)],
        context.buyer_headers,
    )
    order_id = uuid.UUID(str(order["id"]))

    repository = OrderRepository(db_session)
    draft = repository.get_by_id(order_id)
    assert draft is not None
    assert draft.status == "draft"

    # Change the row without going through the ORM, simulating a concurrent
    # transaction that committed while this object sat in the identity map.
    db_session.execute(
        text("UPDATE orders SET status = :status WHERE id = :id"),
        {"status": "cancelled", "id": order_id},
    )

    locked = repository.get_by_id(order_id, for_update=True)

    assert locked is draft
    assert locked.status == "cancelled"


def test_create_draft_order_with_price_snapshot(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)

    body = create_order(
        client,
        context.buyer["id"],
        context.supplier["id"],
        [order_line(context, 3)],
        context.buyer_headers,
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
    context = create_order_resources(client, db_session)
    order = create_order(
        client,
        context.buyer["id"],
        context.supplier["id"],
        [order_line(context, 1)],
        context.buyer_headers,
    )

    update_response = client.patch(
        f"/api/v1/products/{context.product['id']}",
        json={"price": "99.00"},
        headers=context.supplier_headers,
    )
    get_response = client.get(
        f"/api/v1/orders/{order['id']}",
        headers=context.buyer_headers,
    )

    assert update_response.status_code == 200
    assert Decimal(get_response.json()["lines"][0]["unit_price"]) == Decimal("25.00")


def test_reject_invalid_order_organization_capabilities(
    client: TestClient,
    db_session: Session,
) -> None:
    supplier = create_organization(client, "supplier")
    supplier_headers = create_order_actor(db_session, supplier["id"])
    product = create_product(client, supplier["id"], supplier_headers, sku="ROLE-001")
    warehouse = create_warehouse(
        client, supplier["id"], supplier_headers, code="ROLE-WH"
    )

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
        headers=supplier_headers,
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Buyer organization cannot buy"}


def test_place_order_creates_inventory_reservation(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)

    placed_order = create_placed_order(client, context)
    level = read_level(client, context)

    assert placed_order["status"] == "placed"
    assert placed_order["placed_at"] is not None
    assert placed_order["lines"][0]["reservation_id"] is not None
    assert level["quantity"] == 10
    assert level["reserved_quantity"] == 4
    assert level["available_quantity"] == 6


def test_place_order_rolls_back_all_lines_when_inventory_is_insufficient(
    client: TestClient,
    db_session: Session,
) -> None:
    buyer = create_organization(client, "buyer")
    supplier = create_organization(client, "supplier")
    buyer_headers = create_order_actor(db_session, buyer["id"])
    supplier_headers = create_order_actor(db_session, supplier["id"])
    warehouse = create_warehouse(
        client, supplier["id"], supplier_headers, code="ATOMIC-WH"
    )
    first_product = create_product(
        client, supplier["id"], supplier_headers, sku="ATOMIC-001"
    )
    second_product = create_product(
        client, supplier["id"], supplier_headers, sku="ATOMIC-002"
    )
    adjust_inventory(client, first_product["id"], warehouse["id"], 10, supplier_headers)
    adjust_inventory(client, second_product["id"], warehouse["id"], 1, supplier_headers)
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
        buyer_headers,
    )

    response = client.post(f"/api/v1/orders/{order['id']}/place", headers=buyer_headers)
    first_level = client.get(
        f"/api/v1/inventory/levels/{warehouse['id']}/{first_product['id']}",
        headers=supplier_headers,
    ).json()
    order_response = client.get(f"/api/v1/orders/{order['id']}", headers=buyer_headers)

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
    context = create_order_resources(client, db_session)
    order = create_placed_order(client, context)

    response = client.post(
        f"/api/v1/orders/{order['id']}/cancel", headers=context.buyer_headers
    )
    repeated_response = client.post(
        f"/api/v1/orders/{order['id']}/cancel", headers=context.buyer_headers
    )
    level = read_level(client, context)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancelled_at"] is not None
    assert repeated_response.status_code == 200
    assert level["reserved_quantity"] == 0


def test_list_orders_by_buyer_and_status(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    order = create_order(
        client,
        context.buyer["id"],
        context.supplier["id"],
        [order_line(context, 1)],
        context.buyer_headers,
    )

    response = client.get(
        "/api/v1/orders/",
        params={"buyer_organization_id": context.buyer["id"], "status": "draft"},
        headers=context.buyer_headers,
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == order["id"]


def test_fulfill_order_consumes_reservation_and_creates_movement(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    placed_order = create_placed_order(client, context)
    reservation_id = placed_order["lines"][0]["reservation_id"]

    response = client.post(
        f"/api/v1/orders/{placed_order['id']}/fulfill",
        headers=context.supplier_headers,
    )
    level = read_level(client, context)
    reservation_response = client.get(
        f"/api/v1/inventory/reservations/{reservation_id}",
        headers=context.supplier_headers,
    )
    movements_response = client.get(
        "/api/v1/inventory/movements",
        params={
            "organization_id": context.supplier["id"],
            "warehouse_id": context.warehouse["id"],
            "product_id": context.product["id"],
        },
        headers=context.supplier_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "fulfilled"
    assert response.json()["fulfilled_at"] is not None
    assert level["quantity"] == 6
    assert level["reserved_quantity"] == 0
    assert level["available_quantity"] == 6
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
    context = create_order_resources(client, db_session)
    order = create_order(
        client,
        context.buyer["id"],
        context.supplier["id"],
        [order_line(context, 1)],
        context.buyer_headers,
    )

    response = client.post(
        f"/api/v1/orders/{order['id']}/fulfill",
        headers=context.supplier_headers,
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Order is not placed"}


def test_reject_cancellation_for_fulfilled_order(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    order = create_placed_order(client, context, stock=5, quantity=2)
    client.post(
        f"/api/v1/orders/{order['id']}/fulfill", headers=context.supplier_headers
    )

    response = client.post(
        f"/api/v1/orders/{order['id']}/cancel", headers=context.buyer_headers
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Fulfilled orders cannot be cancelled"}


def test_order_history_records_full_lifecycle(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    order = create_placed_order(client, context, stock=5, quantity=2)
    client.post(
        f"/api/v1/orders/{order['id']}/fulfill", headers=context.supplier_headers
    )

    response = client.get(
        f"/api/v1/orders/{order['id']}/history", headers=context.buyer_headers
    )

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
    context = create_order_resources(client, db_session)
    order = create_order(
        client,
        context.buyer["id"],
        context.supplier["id"],
        [order_line(context, 1)],
        context.buyer_headers,
    )
    for _ in range(2):
        client.post(
            f"/api/v1/orders/{order['id']}/cancel", headers=context.buyer_headers
        )

    response = client.get(
        f"/api/v1/orders/{order['id']}/history",
        params={"limit": 1, "offset": 1},
        headers=context.buyer_headers,
    )

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["limit"] == 1
    assert response.json()["offset"] == 1
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["from_status"] == "draft"
    assert response.json()["items"][0]["to_status"] == "cancelled"


def test_conceal_unknown_order(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client, "buyer")
    headers = create_order_actor(db_session, organization["id"])
    unknown_id = uuid.uuid4()

    responses = [
        client.get(f"/api/v1/orders/{unknown_id}", headers=headers),
        client.get(f"/api/v1/orders/{unknown_id}/history", headers=headers),
        client.post(f"/api/v1/orders/{unknown_id}/place", headers=headers),
        client.post(f"/api/v1/orders/{unknown_id}/cancel", headers=headers),
        client.post(f"/api/v1/orders/{unknown_id}/fulfill", headers=headers),
    ]

    for response in responses:
        assert response.status_code == 404
        assert response.json() == {"detail": "Order not found"}


def test_require_authentication_for_order_endpoints(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    order = create_order(
        client,
        context.buyer["id"],
        context.supplier["id"],
        [order_line(context, 1)],
        context.buyer_headers,
    )
    order_id = order["id"]

    responses = [
        client.post(
            "/api/v1/orders/",
            json={
                "buyer_organization_id": context.buyer["id"],
                "supplier_organization_id": context.supplier["id"],
                "lines": [order_line(context, 1)],
            },
        ),
        client.get(
            "/api/v1/orders/",
            params={"buyer_organization_id": context.buyer["id"]},
        ),
        client.get(f"/api/v1/orders/{order_id}"),
        client.get(f"/api/v1/orders/{order_id}/history"),
        client.post(f"/api/v1/orders/{order_id}/place"),
        client.post(f"/api/v1/orders/{order_id}/cancel"),
        client.post(f"/api/v1/orders/{order_id}/fulfill"),
    ]

    for response in responses:
        assert response.status_code == 401


def test_require_organization_filter_when_listing_orders(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client, "buyer")
    headers = create_order_actor(db_session, organization["id"])

    unscoped_response = client.get("/api/v1/orders/", headers=headers)
    status_only_response = client.get(
        "/api/v1/orders/", params={"status": "draft"}, headers=headers
    )

    assert unscoped_response.status_code == 422
    assert status_only_response.status_code == 422


def test_reject_cross_organization_order_listing(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    outsider_organization = create_organization(client, "buyer")
    outsider_headers = create_order_actor(db_session, outsider_organization["id"])

    responses = [
        client.get(
            "/api/v1/orders/",
            params={"buyer_organization_id": context.buyer["id"]},
            headers=outsider_headers,
        ),
        client.get(
            "/api/v1/orders/",
            params={"supplier_organization_id": context.supplier["id"]},
            headers=outsider_headers,
        ),
        client.get(
            "/api/v1/orders/",
            params={
                "buyer_organization_id": context.buyer["id"],
                "supplier_organization_id": context.supplier["id"],
            },
            headers=outsider_headers,
        ),
    ]

    for response in responses:
        assert response.status_code == 403
        assert response.json() == {"detail": "Not enough permissions"}


def test_list_orders_from_either_party_filter(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    other = create_order_resources(client, db_session)
    order = create_order(
        client,
        context.buyer["id"],
        context.supplier["id"],
        [order_line(context, 1)],
        context.buyer_headers,
    )
    create_order(
        client,
        other.buyer["id"],
        other.supplier["id"],
        [order_line(other, 1)],
        other.buyer_headers,
    )

    buyer_response = client.get(
        "/api/v1/orders/",
        params={"buyer_organization_id": context.buyer["id"]},
        headers=context.buyer_headers,
    )
    supplier_response = client.get(
        "/api/v1/orders/",
        params={"supplier_organization_id": context.supplier["id"]},
        headers=context.supplier_headers,
    )

    assert buyer_response.status_code == 200
    assert buyer_response.json()["total"] == 1
    assert buyer_response.json()["items"][0]["id"] == order["id"]
    assert supplier_response.status_code == 200
    assert supplier_response.json()["total"] == 1
    assert supplier_response.json()["items"][0]["id"] == order["id"]


def test_conceal_orders_from_another_tenant(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    order = create_placed_order(client, context)
    outsider_organization = create_organization(client, "buyer")
    outsider_headers = create_order_actor(db_session, outsider_organization["id"])
    endpoint = f"/api/v1/orders/{order['id']}"

    responses = [
        client.get(endpoint, headers=outsider_headers),
        client.get(f"{endpoint}/history", headers=outsider_headers),
        client.post(f"{endpoint}/place", headers=outsider_headers),
        client.post(f"{endpoint}/cancel", headers=outsider_headers),
        client.post(f"{endpoint}/fulfill", headers=outsider_headers),
    ]
    owner_response = client.get(endpoint, headers=context.buyer_headers)
    level = read_level(client, context)

    for response in responses:
        assert response.status_code == 404
        assert response.json() == {"detail": "Order not found"}
    assert owner_response.status_code == 200
    assert owner_response.json()["status"] == "placed"
    assert level["reserved_quantity"] == 4


def test_allow_both_parties_to_read_order(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    order = create_placed_order(client, context)
    endpoint = f"/api/v1/orders/{order['id']}"

    buyer_response = client.get(endpoint, headers=context.buyer_headers)
    supplier_response = client.get(endpoint, headers=context.supplier_headers)
    buyer_history = client.get(f"{endpoint}/history", headers=context.buyer_headers)
    supplier_history = client.get(
        f"{endpoint}/history", headers=context.supplier_headers
    )

    assert buyer_response.status_code == 200
    assert supplier_response.status_code == 200
    assert buyer_history.status_code == 200
    assert supplier_history.status_code == 200


def test_reject_buyer_fulfillment(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    order = create_placed_order(client, context)

    response = client.post(
        f"/api/v1/orders/{order['id']}/fulfill", headers=context.buyer_headers
    )
    stored_response = client.get(
        f"/api/v1/orders/{order['id']}", headers=context.buyer_headers
    )
    level = read_level(client, context)

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}
    assert stored_response.json()["status"] == "placed"
    assert level["reserved_quantity"] == 4


def test_reject_supplier_placement(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    adjust_inventory(
        client,
        context.product["id"],
        context.warehouse["id"],
        10,
        context.supplier_headers,
    )
    order = create_order(
        client,
        context.buyer["id"],
        context.supplier["id"],
        [order_line(context, 4)],
        context.buyer_headers,
    )

    response = client.post(
        f"/api/v1/orders/{order['id']}/place", headers=context.supplier_headers
    )
    stored_response = client.get(
        f"/api/v1/orders/{order['id']}", headers=context.supplier_headers
    )
    level = read_level(client, context)

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}
    assert stored_response.json()["status"] == "draft"
    assert stored_response.json()["lines"][0]["reservation_id"] is None
    assert level["reserved_quantity"] == 0


def test_reject_supplier_cancellation(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    order = create_placed_order(client, context)

    response = client.post(
        f"/api/v1/orders/{order['id']}/cancel", headers=context.supplier_headers
    )
    stored_response = client.get(
        f"/api/v1/orders/{order['id']}", headers=context.supplier_headers
    )
    level = read_level(client, context)

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}
    assert stored_response.json()["status"] == "placed"
    assert level["reserved_quantity"] == 4


def test_allow_read_but_reject_forbidden_order_commands(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    order = create_placed_order(client, context)
    buyer_viewer_headers = create_order_actor(
        db_session, context.buyer["id"], role="viewer"
    )
    supplier_viewer_headers = create_order_actor(
        db_session, context.supplier["id"], role="viewer"
    )
    endpoint = f"/api/v1/orders/{order['id']}"

    read_response = client.get(endpoint, headers=buyer_viewer_headers)
    history_response = client.get(f"{endpoint}/history", headers=buyer_viewer_headers)
    list_response = client.get(
        "/api/v1/orders/",
        params={"buyer_organization_id": context.buyer["id"]},
        headers=buyer_viewer_headers,
    )
    create_response = client.post(
        "/api/v1/orders/",
        json={
            "buyer_organization_id": context.buyer["id"],
            "supplier_organization_id": context.supplier["id"],
            "lines": [order_line(context, 1)],
        },
        headers=buyer_viewer_headers,
    )
    cancel_response = client.post(f"{endpoint}/cancel", headers=buyer_viewer_headers)
    fulfill_response = client.post(
        f"{endpoint}/fulfill", headers=supplier_viewer_headers
    )

    assert read_response.status_code == 200
    assert history_response.status_code == 200
    assert list_response.status_code == 200
    assert create_response.status_code == 403
    assert cancel_response.status_code == 403
    assert fulfill_response.status_code == 403


def test_reject_role_without_order_permissions(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    order = create_placed_order(client, context)
    catalog_headers = create_order_actor(
        db_session, context.buyer["id"], role="catalog_manager"
    )

    list_response = client.get(
        "/api/v1/orders/",
        params={"buyer_organization_id": context.buyer["id"]},
        headers=catalog_headers,
    )
    create_response = client.post(
        "/api/v1/orders/",
        json={
            "buyer_organization_id": context.buyer["id"],
            "supplier_organization_id": context.supplier["id"],
            "lines": [order_line(context, 1)],
        },
        headers=catalog_headers,
    )
    read_response = client.get(f"/api/v1/orders/{order['id']}", headers=catalog_headers)

    assert list_response.status_code == 403
    assert create_response.status_code == 403
    assert read_response.status_code == 403
    assert read_response.json() == {"detail": "Not enough permissions"}


def test_allow_buyer_role_order_workflow(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    buyer_headers = create_order_actor(db_session, context.buyer["id"], role="buyer")
    adjust_inventory(
        client,
        context.product["id"],
        context.warehouse["id"],
        10,
        context.supplier_headers,
    )

    order = create_order(
        client,
        context.buyer["id"],
        context.supplier["id"],
        [order_line(context, 3)],
        buyer_headers,
    )
    place_response = client.post(
        f"/api/v1/orders/{order['id']}/place", headers=buyer_headers
    )
    cancel_response = client.post(
        f"/api/v1/orders/{order['id']}/cancel", headers=buyer_headers
    )

    assert place_response.status_code == 200
    assert place_response.json()["status"] == "placed"
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"


def test_allow_warehouse_operator_to_fulfill_supplier_order(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    order = create_placed_order(client, context)
    operator_headers = create_order_actor(
        db_session, context.supplier["id"], role="warehouse_operator"
    )

    response = client.post(
        f"/api/v1/orders/{order['id']}/fulfill", headers=operator_headers
    )
    level = read_level(client, context)

    assert response.status_code == 200
    assert response.json()["status"] == "fulfilled"
    assert level["quantity"] == 6
    assert level["reserved_quantity"] == 0


def test_reject_inactive_membership_for_orders(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    order = create_placed_order(client, context)
    inactive_headers = create_order_actor(
        db_session, context.buyer["id"], is_active=False
    )

    list_response = client.get(
        "/api/v1/orders/",
        params={"buyer_organization_id": context.buyer["id"]},
        headers=inactive_headers,
    )
    create_response = client.post(
        "/api/v1/orders/",
        json={
            "buyer_organization_id": context.buyer["id"],
            "supplier_organization_id": context.supplier["id"],
            "lines": [order_line(context, 1)],
        },
        headers=inactive_headers,
    )
    read_response = client.get(
        f"/api/v1/orders/{order['id']}", headers=inactive_headers
    )

    assert list_response.status_code == 403
    assert create_response.status_code == 403
    assert read_response.status_code == 404
    assert read_response.json() == {"detail": "Order not found"}


def test_reject_order_creation_for_foreign_buyer_organization(
    client: TestClient,
    db_session: Session,
) -> None:
    context = create_order_resources(client, db_session)
    outsider_organization = create_organization(client, "buyer")
    outsider_headers = create_order_actor(db_session, outsider_organization["id"])

    response = client.post(
        "/api/v1/orders/",
        json={
            "buyer_organization_id": context.buyer["id"],
            "supplier_organization_id": context.supplier["id"],
            "lines": [order_line(context, 1)],
        },
        headers=outsider_headers,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}
