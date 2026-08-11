import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.identity import User

PASSWORD = "correct-horse-battery-staple"


def create_user(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/users/",
        json={
            "email": f"auth-{uuid.uuid4().hex}@example.com",
            "full_name": "Authenticated User",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )


def test_login_and_get_current_user(client: TestClient) -> None:
    user = create_user(client)

    token_response = login(client, user["email"])
    token = token_response.json()["access_token"]
    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert token_response.status_code == 200
    assert token_response.json()["token_type"] == "bearer"
    assert me_response.status_code == 200
    assert me_response.json()["id"] == user["id"]
    assert me_response.json()["email"] == user["email"]


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("unknown@example.com", PASSWORD),
        (None, "incorrect-password"),
    ],
)
def test_reject_invalid_login(
    client: TestClient,
    email: str | None,
    password: str,
) -> None:
    user = create_user(client)

    response = login(client, email or user["email"], password)

    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect email or password"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_reject_invalid_access_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_reject_expired_access_token(client: TestClient) -> None:
    user = create_user(client)
    token = create_access_token(
        uuid.UUID(str(user["id"])),
        expires_delta=timedelta(seconds=-1),
    )

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_reject_token_for_inactive_user(
    client: TestClient,
    db_session: Session,
) -> None:
    user_data = create_user(client)
    token = login(client, user_data["email"]).json()["access_token"]
    user = db_session.get(User, uuid.UUID(str(user_data["id"])))
    assert user is not None
    user.is_active = False
    db_session.commit()

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
