"""Phase 0 smoke tests: health endpoint and test DB fixture."""

from sqlalchemy import text


def test_health_endpoint(client) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_endpoint(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["app"] == "colearn"


def test_db_fixture_is_usable(db_session) -> None:
    result = db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1
