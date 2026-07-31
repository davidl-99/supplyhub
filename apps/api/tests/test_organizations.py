import uuid

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
    payload = build_organization_payload()

    response = client.post(
        "/api/v1/organizations/",
        json=payload,
    )

    assert response.status_code == 201

    return response.json()


def test_create_organization(client: TestClient) -> None:
    payload = build_organization_payload()

    response = client.post(
        "/api/v1/organizations/",
        json=payload,
    )

    assert response.status_code == 201

    body = response.json()

    assert body["name"] == payload["name"]
    assert body["slug"] == payload["slug"]
    assert body["is_active"] is True
    assert body["id"] is not None
    assert body["created_at"] is not None
    assert body["updated_at"] is not None


def test_reject_duplicate_slug(client: TestClient) -> None:
    payload = build_organization_payload()

    first_response = client.post(
        "/api/v1/organizations/",
        json=payload,
    )

    second_response = client.post(
        "/api/v1/organizations/",
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json() == {
        "detail": "Organization slug already exists",
    }


def test_reject_invalid_slug(client: TestClient) -> None:
    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": "Invalid Organization",
            "slug": "Invalid Organization",
        },
    )

    assert response.status_code == 422


def test_get_organization(client: TestClient) -> None:
    organization = create_organization(client)

    response = client.get(
        f"/api/v1/organizations/{organization['id']}",
    )

    assert response.status_code == 200
    assert response.json()["id"] == organization["id"]


def test_update_organization(client: TestClient) -> None:
    organization = create_organization(client)

    response = client.patch(
        f"/api/v1/organizations/{organization['id']}",
        json={
            "name": "Updated Organization",
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Organization"
    assert response.json()["slug"] == organization["slug"]


def test_reject_empty_update(client: TestClient) -> None:
    organization = create_organization(client)

    response = client.patch(
        f"/api/v1/organizations/{organization['id']}",
        json={},
    )

    assert response.status_code == 422


def test_deactivate_organization(client: TestClient) -> None:
    organization = create_organization(client)
    endpoint = f"/api/v1/organizations/{organization['id']}/deactivate"

    first_response = client.post(endpoint)
    second_response = client.post(endpoint)

    assert first_response.status_code == 200
    assert first_response.json()["is_active"] is False

    assert second_response.status_code == 200
    assert second_response.json()["is_active"] is False


def test_get_unknown_organization(client: TestClient) -> None:
    unknown_id = uuid.uuid4()

    response = client.get(
        f"/api/v1/organizations/{unknown_id}",
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Organization not found",
    }
