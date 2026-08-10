import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.identity import User


def create_user(
    client: TestClient,
    *,
    email: str | None = None,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/users/",
        json={
            "email": email or f"user-{uuid.uuid4().hex}@example.com",
            "full_name": "SupplyHub User",
            "password": "correct-horse-battery-staple",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_organization(
    client: TestClient,
    organization_type: str,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": f"Identity {organization_type.title()} Organization",
            "slug": f"identity-{organization_type}-{uuid.uuid4().hex}",
            "organization_type": organization_type,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_membership(
    client: TestClient,
    organization_id: object,
    user_id: object,
    role: str,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/memberships/",
        json={"user_id": user_id, "role": role},
    )
    assert response.status_code == 201
    return response.json()


def test_create_user_hashes_password_and_hides_hash(
    client: TestClient,
    db_session: Session,
) -> None:
    body = create_user(client, email="Mixed.Case@Example.COM")

    stored_user = db_session.scalar(select(User).where(User.id == body["id"]))

    assert body["email"] == "mixed.case@example.com"
    assert body["is_active"] is True
    assert "password" not in body
    assert "password_hash" not in body
    assert stored_user is not None
    assert stored_user.password_hash.startswith("$argon2")
    assert verify_password("correct-horse-battery-staple", stored_user.password_hash)


def test_reject_duplicate_user_email_case_insensitively(client: TestClient) -> None:
    create_user(client, email="duplicate@example.com")

    response = client.post(
        "/api/v1/users/",
        json={
            "email": "DUPLICATE@example.com",
            "full_name": "Duplicate User",
            "password": "another-secure-password",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "User email already exists"}


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("invalid-email", "correct-horse-battery-staple"),
        ("valid@example.com", "too-short"),
    ],
)
def test_reject_invalid_user_credentials(
    client: TestClient,
    email: str,
    password: str,
) -> None:
    response = client.post(
        "/api/v1/users/",
        json={"email": email, "full_name": "Invalid User", "password": password},
    )

    assert response.status_code == 422


def test_create_and_list_membership(client: TestClient) -> None:
    organization = create_organization(client, "supplier")
    user = create_user(client)
    membership = create_membership(
        client, organization["id"], user["id"], "catalog_manager"
    )

    response = client.get(
        f"/api/v1/organizations/{organization['id']}/memberships/",
        params={"role": "catalog_manager", "is_active": True},
    )

    assert membership["organization_id"] == organization["id"]
    assert membership["user_id"] == user["id"]
    assert membership["role"] == "catalog_manager"
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == membership["id"]


def test_reject_duplicate_membership(client: TestClient) -> None:
    organization = create_organization(client, "supplier")
    user = create_user(client)
    create_membership(client, organization["id"], user["id"], "viewer")

    response = client.post(
        f"/api/v1/organizations/{organization['id']}/memberships/",
        json={"user_id": user["id"], "role": "organization_admin"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "User already has a membership in this organization"
    }


@pytest.mark.parametrize(
    ("organization_type", "role"),
    [("buyer", "catalog_manager"), ("supplier", "buyer")],
)
def test_reject_incompatible_membership_role(
    client: TestClient,
    organization_type: str,
    role: str,
) -> None:
    organization = create_organization(client, organization_type)
    user = create_user(client)

    response = client.post(
        f"/api/v1/organizations/{organization['id']}/memberships/",
        json={"user_id": user["id"], "role": role},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Membership role is incompatible with the organization type"
    }


def test_update_and_deactivate_membership(client: TestClient) -> None:
    organization = create_organization(client, "both")
    user = create_user(client)
    membership = create_membership(client, organization["id"], user["id"], "viewer")
    endpoint = (
        f"/api/v1/organizations/{organization['id']}/memberships/{membership['id']}"
    )

    update_response = client.patch(endpoint, json={"role": "buyer"})
    deactivate_response = client.post(f"{endpoint}/deactivate")
    repeated_response = client.post(f"{endpoint}/deactivate")

    assert update_response.status_code == 200
    assert update_response.json()["role"] == "buyer"
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False
    assert repeated_response.status_code == 200
    assert repeated_response.json()["is_active"] is False


def test_paginate_memberships(client: TestClient) -> None:
    organization = create_organization(client, "supplier")
    for _ in range(2):
        user = create_user(client)
        create_membership(client, organization["id"], user["id"], "viewer")

    response = client.get(
        f"/api/v1/organizations/{organization['id']}/memberships/",
        params={"limit": 1, "offset": 1},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1
