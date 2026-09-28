import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.identity import OrganizationMembership

PASSWORD = "correct-horse-battery-staple"


def build_organization_payload() -> dict[str, str]:
    unique_value = uuid.uuid4().hex

    return {
        "name": f"Test Organization {unique_value}",
        "slug": f"test-organization-{unique_value}",
    }


def create_user(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/users/",
        json={
            "email": f"organization-user-{uuid.uuid4().hex}@example.com",
            "full_name": "Organization Test User",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()


def authorization_headers(user_id: object) -> dict[str, str]:
    token = create_access_token(uuid.UUID(str(user_id)))
    return {"Authorization": f"Bearer {token}"}


def create_actor(client: TestClient) -> dict[str, str]:
    """Create a user with no organization membership of its own."""
    return authorization_headers(create_user(client)["id"])


def create_organization(
    client: TestClient,
    headers: dict[str, str],
    *,
    organization_type: str | None = None,
) -> dict[str, object]:
    payload = build_organization_payload()
    if organization_type is not None:
        payload["organization_type"] = organization_type

    response = client.post(
        "/api/v1/organizations/",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 201

    return response.json()


def seed_membership(
    db_session: Session,
    organization_id: object,
    user_id: object,
    role: str,
) -> None:
    db_session.add(
        OrganizationMembership(
            organization_id=uuid.UUID(str(organization_id)),
            user_id=uuid.UUID(str(user_id)),
            role=role,
        )
    )
    db_session.commit()


def test_create_organization(client: TestClient) -> None:
    headers = create_actor(client)
    payload = build_organization_payload()

    response = client.post(
        "/api/v1/organizations/",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 201

    body = response.json()

    assert body["name"] == payload["name"]
    assert body["slug"] == payload["slug"]
    assert body["organization_type"] == "supplier"
    assert body["is_active"] is True
    assert body["id"] is not None
    assert body["created_at"] is not None
    assert body["updated_at"] is not None


def test_create_organization_makes_creator_first_administrator(
    client: TestClient,
    db_session: Session,
) -> None:
    """Onboarding must produce the organization and its administrator together.

    An organization without an active administrator could not be administered
    by anyone and would violate the last-active-administrator invariant from
    the moment it exists. See ADR 0006.
    """
    creator = create_user(client)
    headers = authorization_headers(creator["id"])

    organization = create_organization(client, headers)

    membership = db_session.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id
            == uuid.UUID(str(organization["id"])),
        )
    )

    assert membership is not None
    assert membership.user_id == uuid.UUID(str(creator["id"]))
    assert membership.role == "organization_admin"
    assert membership.is_active is True


def test_require_authentication_for_every_organization_route(
    client: TestClient,
) -> None:
    headers = create_actor(client)
    organization = create_organization(client, headers)
    endpoint = f"/api/v1/organizations/{organization['id']}"

    responses = [
        client.post("/api/v1/organizations/", json=build_organization_payload()),
        client.get("/api/v1/organizations/"),
        client.get(endpoint),
        client.patch(endpoint, json={"name": "Renamed Organization"}),
        client.post(f"{endpoint}/deactivate"),
    ]

    for response in responses:
        assert response.status_code == 401


def test_reject_organization_access_from_another_tenant(
    client: TestClient,
) -> None:
    owner_headers = create_actor(client)
    organization = create_organization(client, owner_headers)
    outsider_headers = create_actor(client)
    endpoint = f"/api/v1/organizations/{organization['id']}"

    responses = [
        client.get(endpoint, headers=outsider_headers),
        client.patch(
            endpoint,
            json={"name": "Hijacked Organization"},
            headers=outsider_headers,
        ),
        client.post(f"{endpoint}/deactivate", headers=outsider_headers),
    ]

    for response in responses:
        assert response.status_code == 403
        assert response.json() == {"detail": "Not enough permissions"}


def test_list_only_returns_organizations_the_caller_belongs_to(
    client: TestClient,
) -> None:
    owner_headers = create_actor(client)
    organization = create_organization(client, owner_headers)
    outsider_headers = create_actor(client)
    create_organization(client, outsider_headers)

    response = client.get("/api/v1/organizations/", headers=owner_headers)

    assert response.status_code == 200

    body = response.json()

    assert [item["id"] for item in body] == [organization["id"]]


def test_reject_organization_mutation_without_permission(
    client: TestClient,
    db_session: Session,
) -> None:
    owner_headers = create_actor(client)
    organization = create_organization(client, owner_headers)
    viewer = create_user(client)
    seed_membership(db_session, organization["id"], viewer["id"], "viewer")
    viewer_headers = authorization_headers(viewer["id"])
    endpoint = f"/api/v1/organizations/{organization['id']}"

    read_response = client.get(endpoint, headers=viewer_headers)
    update_response = client.patch(
        endpoint,
        json={"name": "Renamed Organization"},
        headers=viewer_headers,
    )
    deactivate_response = client.post(
        f"{endpoint}/deactivate",
        headers=viewer_headers,
    )

    assert read_response.status_code == 200
    assert update_response.status_code == 403
    assert deactivate_response.status_code == 403


def test_reject_duplicate_slug(client: TestClient) -> None:
    headers = create_actor(client)
    payload = build_organization_payload()

    first_response = client.post(
        "/api/v1/organizations/",
        json=payload,
        headers=headers,
    )

    second_response = client.post(
        "/api/v1/organizations/",
        json=payload,
        headers=headers,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {
        "detail": "Organization slug already exists",
    }


def test_reject_invalid_slug(client: TestClient) -> None:
    headers = create_actor(client)

    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Invalid Organization",
            "slug": "Invalid Organization",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_get_organization(client: TestClient) -> None:
    headers = create_actor(client)
    organization = create_organization(client, headers)

    response = client.get(
        f"/api/v1/organizations/{organization['id']}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] == organization["id"]


def test_update_organization(client: TestClient) -> None:
    headers = create_actor(client)
    organization = create_organization(client, headers)

    response = client.patch(
        f"/api/v1/organizations/{organization['id']}",
        json={
            "name": "Updated Organization",
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Organization"
    assert response.json()["slug"] == organization["slug"]


def test_reject_empty_update(client: TestClient) -> None:
    headers = create_actor(client)
    organization = create_organization(client, headers)

    response = client.patch(
        f"/api/v1/organizations/{organization['id']}",
        json={},
        headers=headers,
    )

    assert response.status_code == 422


def test_deactivate_organization(client: TestClient) -> None:
    headers = create_actor(client)
    organization = create_organization(client, headers)
    endpoint = f"/api/v1/organizations/{organization['id']}/deactivate"

    first_response = client.post(endpoint, headers=headers)
    second_response = client.post(endpoint, headers=headers)

    assert first_response.status_code == 200
    assert first_response.json()["is_active"] is False

    assert second_response.status_code == 200
    assert second_response.json()["is_active"] is False


def test_conceal_unknown_organization_as_forbidden(client: TestClient) -> None:
    """An unknown organization is indistinguishable from one the caller cannot
    see: both resolve no active membership, so both answer ``403``."""
    headers = create_actor(client)
    unknown_id = uuid.uuid4()

    response = client.get(
        f"/api/v1/organizations/{unknown_id}",
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Not enough permissions",
    }


def test_create_buyer_organization(client: TestClient) -> None:
    headers = create_actor(client)
    payload = build_organization_payload()
    payload["organization_type"] = "buyer"

    response = client.post(
        "/api/v1/organizations/",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["organization_type"] == "buyer"


def test_expand_organization_type_to_both(client: TestClient) -> None:
    headers = create_actor(client)
    organization = create_organization(client, headers)

    response = client.patch(
        f"/api/v1/organizations/{organization['id']}",
        json={"organization_type": "both"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["organization_type"] == "both"


def test_reject_narrowing_organization_type(client: TestClient) -> None:
    headers = create_actor(client)
    organization = create_organization(client, headers, organization_type="both")

    response = client.patch(
        f"/api/v1/organizations/{organization['id']}",
        json={"organization_type": "buyer"},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Organization type can only be expanded to both"
    }


def test_reject_invalid_organization_type(client: TestClient) -> None:
    headers = create_actor(client)
    payload = build_organization_payload()
    payload["organization_type"] = "invalid"

    response = client.post(
        "/api/v1/organizations/",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 422
