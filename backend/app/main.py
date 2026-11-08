"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api import assignments, auth, courses, submissions
from app.api.health import router as health_router
from app.core.config import settings

app = FastAPI(
    title="Human-AI Co-Learning Agent",
    version="0.1.0",
    description="Dual-role educational platform with LangGraph evaluation agents.",
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(courses.router, prefix=settings.api_v1_prefix)
app.include_router(assignments.router, prefix=settings.api_v1_prefix)
app.include_router(submissions.router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"app": "colearn", "docs": "/docs", "health": f"{settings.api_v1_prefix}/health"}
