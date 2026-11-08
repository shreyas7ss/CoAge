"""Auth unit and API tests."""

import uuid

from app.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.enums import UserRole
from tests.helpers import make_user


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_roundtrip() -> None:
    uid = uuid.uuid4()
    token = create_access_token(uid, "student")
    payload = decode_token(token)
    assert payload["sub"] == str(uid)
    assert payload["role"] == "student"


def test_login_returns_token_and_me(client, db_session) -> None:
    make_user(db_session, role=UserRole.student, email="s1@example.com")
    resp = client.post(
        "/api/v1/auth/login", json={"email": "s1@example.com", "password": "password"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "student"
    assert body["user"]["email"] == "s1@example.com"
    assert body["token_type"] == "bearer"

    me_resp = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "s1@example.com"


def test_login_wrong_password(client, db_session) -> None:
    make_user(db_session, role=UserRole.student, email="s1@example.com")
    resp = client.post(
        "/api/v1/auth/login", json={"email": "s1@example.com", "password": "bad"}
    )
    assert resp.status_code == 401


def test_me_requires_auth(client) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401
