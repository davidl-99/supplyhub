import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.identity import OrganizationMembership, User


def build_organization_payload() -> dict[str, str]:
    unique_value = uuid.uuid4().hex

    return {
        "name": f"Test Organization {unique_value}",
        "slug": f"test-organization-{unique_value}",
    }


def create_organization(
    client: TestClient,
    *,
    organization_type: str = "supplier",
) -> dict[str, object]:
    payload = build_organization_payload()
    payload["organization_type"] = organization_type
    response = client.post(
        "/api/v1/organizations/",
        json=payload,
    )

    assert response.status_code == 201

    return response.json()


def create_user(db_session: Session) -> User:
    user = User(
        email=f"product-user-{uuid.uuid4().hex}@example.com",
        full_name="Product Test User",
        password_hash="not-used-by-product-authorization-tests",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def authorization_headers(user_id: object) -> dict[str, str]:
    token = create_access_token(uuid.UUID(str(user_id)))
    return {"Authorization": f"Bearer {token}"}


def create_product_actor(
    _client: TestClient,
    db_session: Session,
    organization_id: object,
    *,
    role: str = "catalog_manager",
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
    headers: dict[str, str],
) -> dict[str, object]:
    response = client.post(
        "/api/v1/products/",
        json=build_product_payload(organization_id),
        headers=headers,
    )

    assert response.status_code == 201

    return response.json()


def test_create_product(client: TestClient, db_session: Session) -> None:
    organization = create_organization(client)
    headers = create_product_actor(client, db_session, organization["id"])
    payload = build_product_payload(str(organization["id"]))

    response = client.post(
        "/api/v1/products/",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 201

    body = response.json()

    assert body["organization_id"] == organization["id"]
    assert body["sku"] == payload["sku"]
    assert body["name"] == payload["name"]
    assert Decimal(body["price"]) == Decimal("1299.99")
    assert body["currency"] == "USD"
    assert body["is_active"] is True


def test_reject_product_for_buyer_organization(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client, organization_type="buyer")
    headers = create_product_actor(
        client,
        db_session,
        organization["id"],
        role="organization_admin",
    )

    response = client.post(
        "/api/v1/products/",
        json=build_product_payload(str(organization["id"])),
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Organization cannot supply products"}


def test_reject_duplicate_sku_in_same_organization(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    organization_id = str(organization["id"])
    headers = create_product_actor(client, db_session, organization_id)
    sku = "DUPLICATE-001"

    first_response = client.post(
        "/api/v1/products/",
        json=build_product_payload(organization_id, sku),
        headers=headers,
    )

    second_response = client.post(
        "/api/v1/products/",
        json=build_product_payload(organization_id, sku),
        headers=headers,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {
        "detail": "Product SKU already exists for this organization",
    }


def test_allow_same_sku_in_different_organizations(
    client: TestClient,
    db_session: Session,
) -> None:
    first_organization = create_organization(client)
    second_organization = create_organization(client)
    first_headers = create_product_actor(
        client,
        db_session,
        first_organization["id"],
    )
    second_headers = create_product_actor(
        client,
        db_session,
        second_organization["id"],
    )
    sku = "SHARED-001"

    first_response = client.post(
        "/api/v1/products/",
        json=build_product_payload(str(first_organization["id"]), sku),
        headers=first_headers,
    )

    second_response = client.post(
        "/api/v1/products/",
        json=build_product_payload(str(second_organization["id"]), sku),
        headers=second_headers,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201


def test_reject_product_for_unauthorized_organization(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)

    response = client.post(
        "/api/v1/products/",
        json=build_product_payload(str(uuid.uuid4())),
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}


def test_reject_product_for_inactive_organization(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    organization_id = str(organization["id"])
    headers = create_product_actor(client, db_session, organization_id)

    deactivate_response = client.post(
        f"/api/v1/organizations/{organization_id}/deactivate",
    )

    response = client.post(
        "/api/v1/products/",
        json=build_product_payload(organization_id),
        headers=headers,
    )

    assert deactivate_response.status_code == 200
    assert response.status_code == 409
    assert response.json() == {
        "detail": "Organization is inactive",
    }


def test_list_products_by_organization(
    client: TestClient,
    db_session: Session,
) -> None:
    first_organization = create_organization(client)
    second_organization = create_organization(client)
    first_headers = create_product_actor(
        client,
        db_session,
        first_organization["id"],
    )
    second_headers = create_product_actor(
        client,
        db_session,
        second_organization["id"],
    )

    first_product = create_product(
        client,
        str(first_organization["id"]),
        first_headers,
    )

    create_product(
        client,
        str(second_organization["id"]),
        second_headers,
    )

    response = client.get(
        "/api/v1/products/",
        params={
            "organization_id": first_organization["id"],
        },
        headers=first_headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == first_product["id"]
    assert body["limit"] == 20
    assert body["offset"] == 0


def test_get_and_update_product(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    headers = create_product_actor(client, db_session, organization["id"])
    product = create_product(
        client,
        str(organization["id"]),
        headers,
    )

    get_response = client.get(
        f"/api/v1/products/{product['id']}",
        headers=headers,
    )

    update_response = client.patch(
        f"/api/v1/products/{product['id']}",
        json={
            "name": "Updated Test Product",
            "price": 1499.99,
            "description": None,
        },
        headers=headers,
    )

    assert get_response.status_code == 200
    assert get_response.json()["id"] == product["id"]

    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Updated Test Product"
    assert Decimal(update_response.json()["price"]) == Decimal("1499.99")
    assert update_response.json()["description"] is None


def test_deactivate_product(client: TestClient, db_session: Session) -> None:
    organization = create_organization(client)
    headers = create_product_actor(client, db_session, organization["id"])
    product = create_product(
        client,
        str(organization["id"]),
        headers,
    )

    endpoint = f"/api/v1/products/{product['id']}/deactivate"

    first_response = client.post(endpoint, headers=headers)
    second_response = client.post(endpoint, headers=headers)

    assert first_response.status_code == 200
    assert first_response.json()["is_active"] is False

    assert second_response.status_code == 200
    assert second_response.json()["is_active"] is False


def test_get_unknown_product(client: TestClient, db_session: Session) -> None:
    organization = create_organization(client)
    headers = create_product_actor(client, db_session, organization["id"])

    response = client.get(
        f"/api/v1/products/{uuid.uuid4()}",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Product not found",
    }


def test_search_products(client: TestClient, db_session: Session) -> None:
    organization = create_organization(client)
    organization_id = str(organization["id"])
    headers = create_product_actor(client, db_session, organization_id)

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

    client.post("/api/v1/products/", json=keyboard_payload, headers=headers)
    client.post("/api/v1/products/", json=monitor_payload, headers=headers)

    response = client.get(
        "/api/v1/products/",
        params={
            "organization_id": organization_id,
            "search": "keyboard",
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["sku"] == "KEYBOARD-001"


def test_filter_products_by_status(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    organization_id = str(organization["id"])
    headers = create_product_actor(client, db_session, organization_id)

    active_product = create_product(
        client,
        organization_id,
        headers,
    )
    inactive_product = create_product(
        client,
        organization_id,
        headers,
    )

    client.post(
        f"/api/v1/products/{inactive_product['id']}/deactivate",
        headers=headers,
    )

    response = client.get(
        "/api/v1/products/",
        params={
            "organization_id": organization_id,
            "is_active": True,
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == active_product["id"]


def test_paginate_products(client: TestClient, db_session: Session) -> None:
    organization = create_organization(client)
    organization_id = str(organization["id"])
    headers = create_product_actor(client, db_session, organization_id)

    for _ in range(3):
        create_product(client, organization_id, headers)

    first_page = client.get(
        "/api/v1/products/",
        params={
            "organization_id": organization_id,
            "limit": 2,
            "offset": 0,
        },
        headers=headers,
    )

    second_page = client.get(
        "/api/v1/products/",
        params={
            "organization_id": organization_id,
            "limit": 2,
            "offset": 2,
        },
        headers=headers,
    )

    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert len(first_page.json()["items"]) == 2

    assert second_page.status_code == 200
    assert second_page.json()["total"] == 3
    assert len(second_page.json()["items"]) == 1


def test_require_authentication_to_create_product(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    headers = create_product_actor(client, db_session, organization["id"])

    create_response = client.post(
        "/api/v1/products/",
        json=build_product_payload(str(organization["id"])),
    )

    list_response = client.get(
        "/api/v1/products/",
        params={"organization_id": organization["id"]},
        headers=headers,
    )

    assert create_response.status_code == 401
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


def test_require_organization_filter_when_listing_products(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    headers = create_product_actor(client, db_session, organization["id"])

    response = client.get(
        "/api/v1/products/",
        headers=headers,
    )

    assert response.status_code == 422


def test_reject_cross_organization_collection_access(
    client: TestClient,
    db_session: Session,
) -> None:
    actor_organization = create_organization(client)
    target_organization = create_organization(client)
    actor_headers = create_product_actor(
        client,
        db_session,
        actor_organization["id"],
    )

    create_response = client.post(
        "/api/v1/products/",
        json=build_product_payload(str(target_organization["id"])),
        headers=actor_headers,
    )
    list_response = client.get(
        "/api/v1/products/",
        params={"organization_id": target_organization["id"]},
        headers=actor_headers,
    )

    assert create_response.status_code == 403
    assert list_response.status_code == 403
    assert create_response.json() == {"detail": "Not enough permissions"}
    assert list_response.json() == {"detail": "Not enough permissions"}


def test_conceal_cross_organization_product(
    client: TestClient,
    db_session: Session,
) -> None:
    actor_organization = create_organization(client)
    target_organization = create_organization(client)
    actor_headers = create_product_actor(
        client,
        db_session,
        actor_organization["id"],
    )
    target_headers = create_product_actor(
        client,
        db_session,
        target_organization["id"],
    )
    product = create_product(
        client,
        str(target_organization["id"]),
        target_headers,
    )
    endpoint = f"/api/v1/products/{product['id']}"

    get_response = client.get(endpoint, headers=actor_headers)
    update_response = client.patch(
        endpoint,
        json={"name": "Unauthorized Update"},
        headers=actor_headers,
    )
    deactivate_response = client.post(
        f"{endpoint}/deactivate",
        headers=actor_headers,
    )
    stored_response = client.get(endpoint, headers=target_headers)

    assert get_response.status_code == 404
    assert update_response.status_code == 404
    assert deactivate_response.status_code == 404
    assert get_response.json() == {"detail": "Product not found"}
    assert update_response.json() == {"detail": "Product not found"}
    assert deactivate_response.json() == {"detail": "Product not found"}
    assert stored_response.status_code == 200
    assert stored_response.json()["name"] == product["name"]
    assert stored_response.json()["is_active"] is True


def test_allow_read_but_reject_forbidden_product_mutations(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    manager_headers = create_product_actor(
        client,
        db_session,
        organization["id"],
    )
    viewer_headers = create_product_actor(
        client,
        db_session,
        organization["id"],
        role="viewer",
    )
    product = create_product(
        client,
        str(organization["id"]),
        manager_headers,
    )
    endpoint = f"/api/v1/products/{product['id']}"

    read_response = client.get(endpoint, headers=viewer_headers)
    update_response = client.patch(
        endpoint,
        json={"name": "Forbidden Update"},
        headers=viewer_headers,
    )
    deactivate_response = client.post(
        f"{endpoint}/deactivate",
        headers=viewer_headers,
    )

    assert read_response.status_code == 200
    assert update_response.status_code == 403
    assert deactivate_response.status_code == 403
    assert update_response.json() == {"detail": "Not enough permissions"}
    assert deactivate_response.json() == {"detail": "Not enough permissions"}


def test_reject_inactive_membership_for_product_list(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    headers = create_product_actor(
        client,
        db_session,
        organization["id"],
        is_active=False,
    )

    response = client.get(
        "/api/v1/products/",
        params={"organization_id": organization["id"]},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}
