import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.db.session import session_factory
from app.main import app
from app.models.identity import OrganizationMembership, User
from app.models.organization import Organization

PASSWORD = "correct-horse-battery-staple"


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
            "password": PASSWORD,
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
    headers: dict[str, str],
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/organizations/{organization_id}/memberships/",
        json={"user_id": user_id, "role": role},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def authorization_headers(user_id: object) -> dict[str, str]:
    token = create_access_token(uuid.UUID(str(user_id)))
    return {"Authorization": f"Bearer {token}"}


def seed_membership(
    db_session: Session,
    organization_id: object,
    user_id: object,
    role: str,
    *,
    is_active: bool = True,
) -> OrganizationMembership:
    membership = OrganizationMembership(
        organization_id=uuid.UUID(str(organization_id)),
        user_id=uuid.UUID(str(user_id)),
        role=role,
        is_active=is_active,
    )
    db_session.add(membership)
    db_session.commit()
    db_session.refresh(membership)
    return membership


def create_organization_admin(
    client: TestClient,
    db_session: Session,
    organization_id: object,
) -> dict[str, str]:
    administrator = create_user(client)
    seed_membership(
        db_session,
        organization_id,
        administrator["id"],
        "organization_admin",
    )
    return authorization_headers(administrator["id"])


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


def test_create_and_list_membership(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client, "supplier")
    headers = create_organization_admin(client, db_session, organization["id"])
    user = create_user(client)
    membership = create_membership(
        client,
        organization["id"],
        user["id"],
        "catalog_manager",
        headers,
    )

    response = client.get(
        f"/api/v1/organizations/{organization['id']}/memberships/",
        params={"role": "catalog_manager", "is_active": True},
        headers=headers,
    )

    assert membership["organization_id"] == organization["id"]
    assert membership["user_id"] == user["id"]
    assert membership["role"] == "catalog_manager"
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == membership["id"]


def test_reject_duplicate_membership(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client, "supplier")
    headers = create_organization_admin(client, db_session, organization["id"])
    user = create_user(client)
    create_membership(client, organization["id"], user["id"], "viewer", headers)

    response = client.post(
        f"/api/v1/organizations/{organization['id']}/memberships/",
        json={"user_id": user["id"], "role": "organization_admin"},
        headers=headers,
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
    db_session: Session,
    organization_type: str,
    role: str,
) -> None:
    organization = create_organization(client, organization_type)
    headers = create_organization_admin(client, db_session, organization["id"])
    user = create_user(client)

    response = client.post(
        f"/api/v1/organizations/{organization['id']}/memberships/",
        json={"user_id": user["id"], "role": role},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Membership role is incompatible with the organization type"
    }


def test_update_and_deactivate_membership(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client, "both")
    headers = create_organization_admin(client, db_session, organization["id"])
    user = create_user(client)
    membership = create_membership(
        client,
        organization["id"],
        user["id"],
        "viewer",
        headers,
    )
    endpoint = (
        f"/api/v1/organizations/{organization['id']}/memberships/{membership['id']}"
    )

    update_response = client.patch(endpoint, json={"role": "buyer"}, headers=headers)
    deactivate_response = client.post(f"{endpoint}/deactivate", headers=headers)
    repeated_response = client.post(f"{endpoint}/deactivate", headers=headers)

    assert update_response.status_code == 200
    assert update_response.json()["role"] == "buyer"
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False
    assert repeated_response.status_code == 200
    assert repeated_response.json()["is_active"] is False


def test_paginate_memberships(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client, "supplier")
    headers = create_organization_admin(client, db_session, organization["id"])
    for _ in range(2):
        user = create_user(client)
        create_membership(
            client,
            organization["id"],
            user["id"],
            "viewer",
            headers,
        )

    response = client.get(
        f"/api/v1/organizations/{organization['id']}/memberships/",
        params={"limit": 1, "offset": 1},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert len(response.json()["items"]) == 1


def test_membership_creation_requires_authentication(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client, "supplier")
    target_user = create_user(client)

    response = client.post(
        f"/api/v1/organizations/{organization['id']}/memberships/",
        json={"user_id": target_user["id"], "role": "viewer"},
    )
    stored_membership = db_session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization["id"],
            OrganizationMembership.user_id == target_user["id"],
        )
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert stored_membership is None


def test_reject_user_without_organization_membership(client: TestClient) -> None:
    organization = create_organization(client, "supplier")
    user = create_user(client)

    response = client.get(
        f"/api/v1/organizations/{organization['id']}/memberships/",
        headers=authorization_headers(user["id"]),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}


def test_reject_inactive_organization_membership(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client, "supplier")
    user = create_user(client)
    seed_membership(
        db_session,
        organization["id"],
        user["id"],
        "organization_admin",
        is_active=False,
    )

    response = client.get(
        f"/api/v1/organizations/{organization['id']}/memberships/",
        headers=authorization_headers(user["id"]),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}


def test_reject_membership_without_required_permission(
    client: TestClient,
    db_session: Session,
) -> None:
    organization = create_organization(client, "supplier")
    user = create_user(client)
    seed_membership(
        db_session,
        organization["id"],
        user["id"],
        "viewer",
    )

    response = client.get(
        f"/api/v1/organizations/{organization['id']}/memberships/",
        headers=authorization_headers(user["id"]),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}


def test_reject_cross_organization_membership_mutation(
    client: TestClient,
    db_session: Session,
) -> None:
    actor_organization = create_organization(client, "supplier")
    target_organization = create_organization(client, "supplier")
    actor = create_user(client)
    target_user = create_user(client)
    seed_membership(
        db_session,
        actor_organization["id"],
        actor["id"],
        "organization_admin",
    )
    target_membership = seed_membership(
        db_session,
        target_organization["id"],
        target_user["id"],
        "viewer",
    )

    response = client.post(
        f"/api/v1/organizations/{target_organization['id']}"
        f"/memberships/{target_membership.id}/deactivate",
        headers=authorization_headers(actor["id"]),
    )
    db_session.refresh(target_membership)

    assert response.status_code == 403
    assert response.json() == {"detail": "Not enough permissions"}
    assert target_membership.is_active is True


@pytest.mark.parametrize("operation", ["demote", "deactivate"])
def test_reject_removing_last_active_administrator(
    client: TestClient,
    db_session: Session,
    operation: str,
) -> None:
    organization = create_organization(client, "supplier")
    administrator = create_user(client)
    membership = seed_membership(
        db_session,
        organization["id"],
        administrator["id"],
        "organization_admin",
    )
    endpoint = f"/api/v1/organizations/{organization['id']}/memberships/{membership.id}"
    headers = authorization_headers(administrator["id"])

    if operation == "demote":
        response = client.patch(endpoint, json={"role": "viewer"}, headers=headers)
    else:
        response = client.post(f"{endpoint}/deactivate", headers=headers)
    db_session.refresh(membership)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Organization must have at least one active administrator"
    }
    assert membership.role == "organization_admin"
    assert membership.is_active is True


@pytest.mark.parametrize("operation", ["demote", "deactivate"])
def test_allow_administrator_to_remove_own_access_when_another_admin_exists(
    client: TestClient,
    db_session: Session,
    operation: str,
) -> None:
    organization = create_organization(client, "supplier")
    acting_administrator = create_user(client)
    other_administrator = create_user(client)
    acting_membership = seed_membership(
        db_session,
        organization["id"],
        acting_administrator["id"],
        "organization_admin",
    )
    seed_membership(
        db_session,
        organization["id"],
        other_administrator["id"],
        "organization_admin",
    )
    endpoint = (
        f"/api/v1/organizations/{organization['id']}/memberships/{acting_membership.id}"
    )
    headers = authorization_headers(acting_administrator["id"])

    if operation == "demote":
        response = client.patch(endpoint, json={"role": "viewer"}, headers=headers)
    else:
        response = client.post(f"{endpoint}/deactivate", headers=headers)

    assert response.status_code == 200
    if operation == "demote":
        assert response.json()["role"] == "viewer"
        assert response.json()["is_active"] is True
    else:
        assert response.json()["role"] == "organization_admin"
        assert response.json()["is_active"] is False


def test_concurrent_administrator_deactivations_leave_one_active(
    migrated_database: None,
) -> None:
    organization_id = uuid.uuid4()
    administrator_ids = (uuid.uuid4(), uuid.uuid4())
    membership_ids = (uuid.uuid4(), uuid.uuid4())

    with session_factory() as setup_session:
        setup_session.add(
            Organization(
                id=organization_id,
                name="Concurrent Authorization Organization",
                slug=f"concurrent-authorization-{uuid.uuid4().hex}",
                organization_type="supplier",
            )
        )
        setup_session.add_all(
            [
                User(
                    id=user_id,
                    email=f"concurrent-{user_id}@example.com",
                    full_name="Concurrent Administrator",
                    password_hash="test-only-password-hash",
                )
                for user_id in administrator_ids
            ]
        )
        setup_session.flush()
        setup_session.add_all(
            [
                OrganizationMembership(
                    id=membership_id,
                    organization_id=organization_id,
                    user_id=user_id,
                    role="organization_admin",
                )
                for membership_id, user_id in zip(
                    membership_ids,
                    administrator_ids,
                    strict=True,
                )
            ]
        )
        setup_session.commit()

    start_barrier = Barrier(2)

    def deactivate_administrator(
        user_id: uuid.UUID,
        membership_id: uuid.UUID,
    ) -> int:
        token = create_access_token(user_id)
        start_barrier.wait(timeout=10)
        with TestClient(app) as concurrent_client:
            response = concurrent_client.post(
                f"/api/v1/organizations/{organization_id}"
                f"/memberships/{membership_id}/deactivate",
                headers={"Authorization": f"Bearer {token}"},
            )
        return response.status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    deactivate_administrator,
                    user_id,
                    membership_id,
                )
                for user_id, membership_id in zip(
                    administrator_ids,
                    membership_ids,
                    strict=True,
                )
            ]
            status_codes = sorted(future.result() for future in futures)

        with session_factory() as verification_session:
            active_administrators = verification_session.scalar(
                select(func.count())
                .select_from(OrganizationMembership)
                .where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.role == "organization_admin",
                    OrganizationMembership.is_active.is_(True),
                )
            )

        assert status_codes == [200, 409]
        assert active_administrators == 1
    finally:
        with session_factory() as cleanup_session:
            cleanup_session.execute(
                delete(OrganizationMembership).where(
                    OrganizationMembership.organization_id == organization_id
                )
            )
            cleanup_session.execute(delete(User).where(User.id.in_(administrator_ids)))
            cleanup_session.execute(
                delete(Organization).where(Organization.id == organization_id)
            )
            cleanup_session.commit()
