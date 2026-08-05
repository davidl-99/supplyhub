import uuid

from fastapi.testclient import TestClient


def create_organization(
    client: TestClient,
    *,
    name: str = "Warehouse Organization",
    slug: str | None = None,
    organization_type: str = "supplier",
) -> dict[str, object]:
    organization_slug = slug or f"warehouse-{uuid.uuid4().hex}"
    response = client.post(
        "/api/v1/organizations/",
        json={
            "name": name,
            "slug": organization_slug,
            "organization_type": organization_type,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_warehouse(
    client: TestClient,
    organization_id: str,
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
    )
    assert response.status_code == 201
    return response.json()


def test_create_warehouse(client: TestClient) -> None:
    organization = create_organization(client)

    response = client.post(
        "/api/v1/warehouses/",
        json={
            "organization_id": organization["id"],
            "code": "BOG-01",
            "name": "Bogota Distribution Center",
            "address": "100 Logistics Avenue",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["organization_id"] == organization["id"]
    assert body["code"] == "BOG-01"
    assert body["is_active"] is True


def test_reject_warehouse_for_buyer_organization(client: TestClient) -> None:
    organization = create_organization(client, organization_type="buyer")

    response = client.post(
        "/api/v1/warehouses/",
        json={
            "organization_id": organization["id"],
            "code": "BUYER-01",
            "name": "Buyer Warehouse",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Organization cannot manage warehouses"}


def test_reject_duplicate_code_in_same_organization(client: TestClient) -> None:
    organization = create_organization(client)
    organization_id = str(organization["id"])
    create_warehouse(client, organization_id, code="MAIN")

    response = client.post(
        "/api/v1/warehouses/",
        json={
            "organization_id": organization_id,
            "code": "MAIN",
            "name": "Another Warehouse",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Warehouse code already exists for this organization"
    }


def test_allow_same_code_in_different_organizations(client: TestClient) -> None:
    first_organization = create_organization(client)
    second_organization = create_organization(client)

    first = create_warehouse(client, str(first_organization["id"]), code="MAIN")
    second = create_warehouse(client, str(second_organization["id"]), code="MAIN")

    assert first["code"] == second["code"]
    assert first["organization_id"] != second["organization_id"]


def test_reject_warehouse_for_unknown_or_inactive_organization(
    client: TestClient,
) -> None:
    unknown_response = client.post(
        "/api/v1/warehouses/",
        json={
            "organization_id": str(uuid.uuid4()),
            "code": "MAIN",
            "name": "Main Warehouse",
        },
    )
    assert unknown_response.status_code == 404

    organization = create_organization(client)
    client.post(f"/api/v1/organizations/{organization['id']}/deactivate")
    inactive_response = client.post(
        "/api/v1/warehouses/",
        json={
            "organization_id": organization["id"],
            "code": "MAIN",
            "name": "Main Warehouse",
        },
    )
    assert inactive_response.status_code == 409
    assert inactive_response.json() == {"detail": "Organization is inactive"}


def test_list_and_search_warehouses(client: TestClient) -> None:
    organization = create_organization(client)
    organization_id = str(organization["id"])
    create_warehouse(
        client,
        organization_id,
        code="BOG-01",
        name="Bogota Warehouse",
    )
    create_warehouse(
        client,
        organization_id,
        code="MED-01",
        name="Medellin Warehouse",
    )

    response = client.get(
        "/api/v1/warehouses/",
        params={"organization_id": organization_id, "search": "bogota"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["code"] == "BOG-01"


def test_update_warehouse(client: TestClient) -> None:
    organization = create_organization(client)
    warehouse = create_warehouse(client, str(organization["id"]))

    response = client.patch(
        f"/api/v1/warehouses/{warehouse['id']}",
        json={"code": "SECONDARY", "name": "Secondary Warehouse", "address": None},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "SECONDARY"
    assert body["name"] == "Secondary Warehouse"
    assert body["address"] is None


def test_reject_empty_warehouse_update(client: TestClient) -> None:
    organization = create_organization(client)
    warehouse = create_warehouse(client, str(organization["id"]))

    response = client.patch(
        f"/api/v1/warehouses/{warehouse['id']}",
        json={},
    )

    assert response.status_code == 422


def test_deactivate_warehouse_is_idempotent(client: TestClient) -> None:
    organization = create_organization(client)
    warehouse = create_warehouse(client, str(organization["id"]))
    endpoint = f"/api/v1/warehouses/{warehouse['id']}/deactivate"

    first_response = client.post(endpoint)
    second_response = client.post(endpoint)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["is_active"] is False
    assert second_response.json()["is_active"] is False


def test_get_unknown_warehouse(client: TestClient) -> None:
    response = client.get(f"/api/v1/warehouses/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Warehouse not found"}
