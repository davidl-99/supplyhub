import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.identity import OrganizationMembership, User


def bootstrap_admin_headers(client: TestClient) -> dict[str, str]:
    """Create a user whose only purpose is to own a new organization.

    Organization creation requires an authenticated caller and makes them the
    first administrator (ADR 0006). These tests are about warehouses, not
    onboarding, so they bootstrap a throwaway owner and seed the actor they
    actually exercise separately.
    """
    response = client.post(
        "/api/v1/users/",
        json={
            "email": f"warehouse-bootstrap-{uuid.uuid4().hex}@example.com",
            "full_name": "Warehouse Bootstrap Administrator",
            "password": "correct-horse-battery-staple",
        },
    )
    assert response.status_code == 201
    return authorization_headers(response.json()["id"])


def create_organization(
    client: TestClient,
    *,
    name: str = "Warehouse Organization",
    slug: str | None = None,
    organization_type: str = "supplier",
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    organization_slug = slug or f"warehouse-{uuid.uuid4().hex}"
    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": name,
            "slug": organization_slug,
            "organization_type": organization_type,
        },
        headers=headers or bootstrap_admin_headers(client),
    )
    assert response.status_code == 201
    return response.json()


def create_user(db_session: Session) -> User:
    user = User(
        email=f"warehouse-user-{uuid.uuid4().hex}@example.com",
        full_name="Warehouse Test User",
        password_hash="not-used-by-warehouse-authorization-tests",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def authorization_headers(user_id: object) -> dict[str, str]:
    token = create_access_token(uuid.UUID(str(user_id)))
    return {"Authorization": f"Bearer {token}"}


def create_warehouse_actor(
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


def create_warehouse(
    client: TestClient,
    organization_id: str,
    headers: dict[str, str],
    *,
    code: str = "MAIN",
    name: str = "Main Warehouse",
    address: str | None = "100 Supply Street",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/warehouses/",
        json={
            "organization_id": organization_id,
            "code": code,
            "name": name,
            "address": address,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def test_create_warehouse(client: TestClient, db_session: Session) -> None:
    organization = create_organization(client)
    headers = create_warehouse_actor(client, db_session, organization["id"])

    response = client.post(
        "/api/v1/warehouses/",
        json={
            "organization_id": organization["id"],
            "code": "BOG-01",
            "name": "Bogota Distribution Center",
            "address": "100 Logistics Avenue",
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["organization_id"] == organization["id"]
    assert body["code"] == "BOG-01"
    assert body["is_active"] is True


def test_reject_warehouse_for_buyer_organization(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client, organization_type="buyer")
    headers = create_warehouse_actor(client, db_session, organization["id"])

    response = client.post(
        "/api/v1/warehouses/",
        json={
            "organization_id": organization["id"],
            "code": "BUYER-01",
            "name": "Buyer Warehouse",
        },
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Organization cannot manage warehouses"}


def test_reject_duplicate_code_in_same_organization(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    organization_id = str(organization["id"])
    headers = create_warehouse_actor(client, db_session, organization_id)
    create_warehouse(client, organization_id, headers, code="MAIN")

    response = client.post(
        "/api/v1/warehouses/",
        json={
            "organization_id": organization_id,
            "code": "MAIN",
            "name": "Another Warehouse",
        },
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Warehouse code already exists for this organization"
    }


def test_allow_same_code_in_different_organizations(
    client: TestClient,
    db_session: Session,
) -> None:
    first_organization = create_organization(client)
    second_organization = create_organization(client)
    first_headers = create_warehouse_actor(
        client,
        db_session,
        first_organization["id"],
    )
    second_headers = create_warehouse_actor(
        client,
        db_session,
        second_organization["id"],
    )

    first = create_warehouse(
        client,
        str(first_organization["id"]),
        first_headers,
        code="MAIN",
    )
    second = create_warehouse(
        client,
        str(second_organization["id"]),
        second_headers,
        code="MAIN",
    )

    assert first["code"] == second["code"]
    assert first["organization_id"] != second["organization_id"]


def test_reject_warehouse_for_unauthorized_organization(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)

    response = client.post(
        "/api/v1/warehouses/",
        json={
            "organization_id": str(uuid.uuid4()),
            "code": "MAIN",
            "name": "Main Warehouse",
        },
        headers=authorization_headers(user.id),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}


def test_reject_warehouse_for_inactive_organization(
    client: TestClient,
    db_session: Session,
) -> None:
    owner_headers = bootstrap_admin_headers(client)
    organization = create_organization(client, headers=owner_headers)
    headers = create_warehouse_actor(client, db_session, organization["id"])

    client.post(
        f"/api/v1/organizations/{organization['id']}/deactivate",
        headers=owner_headers,
    )
    inactive_response = client.post(
        "/api/v1/warehouses/",
        json={
            "organization_id": organization["id"],
            "code": "MAIN",
            "name": "Main Warehouse",
        },
        headers=headers,
    )
    assert inactive_response.status_code == 409
    assert inactive_response.json() == {"detail": "Organization is inactive"}


def test_list_and_search_warehouses(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    organization_id = str(organization["id"])
    headers = create_warehouse_actor(client, db_session, organization_id)
    create_warehouse(
        client,
        organization_id,
        headers,
        code="BOG-01",
        name="Bogota Warehouse",
    )
    create_warehouse(
        client,
        organization_id,
        headers,
        code="MED-01",
        name="Medellin Warehouse",
    )

    response = client.get(
        "/api/v1/warehouses/",
        params={"organization_id": organization_id, "search": "bogota"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["code"] == "BOG-01"


def test_update_warehouse(client: TestClient, db_session: Session) -> None:
    organization = create_organization(client)
    headers = create_warehouse_actor(client, db_session, organization["id"])
    warehouse = create_warehouse(client, str(organization["id"]), headers)

    response = client.patch(
        f"/api/v1/warehouses/{warehouse['id']}",
        json={"code": "SECONDARY", "name": "Secondary Warehouse", "address": None},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "SECONDARY"
    assert body["name"] == "Secondary Warehouse"
    assert body["address"] is None


def test_reject_empty_warehouse_update(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    headers = create_warehouse_actor(client, db_session, organization["id"])
    warehouse = create_warehouse(client, str(organization["id"]), headers)

    response = client.patch(
        f"/api/v1/warehouses/{warehouse['id']}",
        json={},
        headers=headers,
    )

    assert response.status_code == 422


def test_deactivate_warehouse_is_idempotent(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    headers = create_warehouse_actor(client, db_session, organization["id"])
    warehouse = create_warehouse(client, str(organization["id"]), headers)
    endpoint = f"/api/v1/warehouses/{warehouse['id']}/deactivate"

    first_response = client.post(endpoint, headers=headers)
    second_response = client.post(endpoint, headers=headers)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["is_active"] is False
    assert second_response.json()["is_active"] is False


def test_get_unknown_warehouse(client: TestClient, db_session: Session) -> None:
    organization = create_organization(client)
    headers = create_warehouse_actor(client, db_session, organization["id"])

    response = client.get(
        f"/api/v1/warehouses/{uuid.uuid4()}",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Warehouse not found"}


def test_require_authentication_to_create_warehouse(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    headers = create_warehouse_actor(client, db_session, organization["id"])

    create_response = client.post(
        "/api/v1/warehouses/",
        json={
            "organization_id": organization["id"],
            "code": "MAIN",
            "name": "Main Warehouse",
        },
    )

    list_response = client.get(
        "/api/v1/warehouses/",
        params={"organization_id": organization["id"]},
        headers=headers,
    )

    assert create_response.status_code == 401
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


def test_require_organization_filter_when_listing_warehouses(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    headers = create_warehouse_actor(client, db_session, organization["id"])

    response = client.get(
        "/api/v1/warehouses/",
        headers=headers,
    )

    assert response.status_code == 422


def test_reject_cross_organization_collection_access(
    client: TestClient,
    db_session: Session,
) -> None:
    actor_organization = create_organization(client)
    target_organization = create_organization(client)
    actor_headers = create_warehouse_actor(
        client,
        db_session,
        actor_organization["id"],
    )

    create_response = client.post(
        "/api/v1/warehouses/",
        json={
            "organization_id": target_organization["id"],
            "code": "MAIN",
            "name": "Main Warehouse",
        },
        headers=actor_headers,
    )
    list_response = client.get(
        "/api/v1/warehouses/",
        params={"organization_id": target_organization["id"]},
        headers=actor_headers,
    )

    assert create_response.status_code == 403
    assert list_response.status_code == 403
    assert create_response.json() == {"detail": "Not enough permissions"}
    assert list_response.json() == {"detail": "Not enough permissions"}


def test_conceal_cross_organization_warehouse(
    client: TestClient,
    db_session: Session,
) -> None:
    actor_organization = create_organization(client)
    target_organization = create_organization(client)
    actor_headers = create_warehouse_actor(
        client,
        db_session,
        actor_organization["id"],
    )
    target_headers = create_warehouse_actor(
        client,
        db_session,
        target_organization["id"],
    )
    warehouse = create_warehouse(
        client,
        str(target_organization["id"]),
        target_headers,
    )
    endpoint = f"/api/v1/warehouses/{warehouse['id']}"

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
    assert get_response.json() == {"detail": "Warehouse not found"}
    assert update_response.json() == {"detail": "Warehouse not found"}
    assert deactivate_response.json() == {"detail": "Warehouse not found"}
    assert stored_response.status_code == 200
    assert stored_response.json()["name"] == warehouse["name"]
    assert stored_response.json()["is_active"] is True


def test_allow_read_but_reject_forbidden_warehouse_mutations(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    admin_headers = create_warehouse_actor(
        client,
        db_session,
        organization["id"],
    )
    operator_headers = create_warehouse_actor(
        client,
        db_session,
        organization["id"],
        role="warehouse_operator",
    )
    warehouse = create_warehouse(
        client,
        str(organization["id"]),
        admin_headers,
    )
    endpoint = f"/api/v1/warehouses/{warehouse['id']}"

    read_response = client.get(endpoint, headers=operator_headers)
    update_response = client.patch(
        endpoint,
        json={"name": "Forbidden Update"},
        headers=operator_headers,
    )
    deactivate_response = client.post(
        f"{endpoint}/deactivate",
        headers=operator_headers,
    )

    assert read_response.status_code == 200
    assert update_response.status_code == 403
    assert deactivate_response.status_code == 403
    assert update_response.json() == {"detail": "Not enough permissions"}
    assert deactivate_response.json() == {"detail": "Not enough permissions"}


def test_reject_inactive_membership_for_warehouse_list(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client)
    headers = create_warehouse_actor(
        client,
        db_session,
        organization["id"],
        is_active=False,
    )

    response = client.get(
        "/api/v1/warehouses/",
        params={"organization_id": organization["id"]},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}
