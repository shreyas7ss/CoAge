"""Ensure the OpenAPI schema exposes the Phase 1 route groups."""

PHASE1_PATHS = [
    "/api/v1/health",
    "/api/v1/auth/login",
    "/api/v1/auth/me",
    "/api/v1/courses",
    "/api/v1/courses/{course_id}/topics",
    "/api/v1/courses/{course_id}/enrollments",
    "/api/v1/topics/{topic_id}",
]


def test_openapi_has_phase1_routes(client) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    for path in PHASE1_PATHS:
        assert path in paths, f"missing route: {path}"
