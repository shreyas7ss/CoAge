"""FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from app.api import alerts, analytics, assignments, auth, courses, submissions
from app.api.health import router as health_router
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.course import Course
from app.services.monitoring_service import run_monitoring

logger = logging.getLogger(__name__)


def _scheduled_monitoring_run() -> None:
    db = SessionLocal()
    try:
        for (course_id,) in db.query(Course.id).all():
            try:
                run_monitoring(db, course_id)
            except Exception:
                logger.exception("Scheduled monitoring failed for course %s", course_id)
                db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    scheduler = None
    if settings.monitoring_scheduler_enabled:
        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(
            _scheduled_monitoring_run,
            "interval",
            hours=max(1, settings.monitoring_interval_hours),
            id="course-monitoring",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


app = FastAPI(
    title="Human-AI Co-Learning Agent",
    version="0.1.0",
    description="Dual-role educational platform with LangGraph evaluation agents.",
    lifespan=lifespan,
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(courses.router, prefix=settings.api_v1_prefix)
app.include_router(assignments.router, prefix=settings.api_v1_prefix)
app.include_router(submissions.router, prefix=settings.api_v1_prefix)
app.include_router(analytics.router, prefix=settings.api_v1_prefix)
app.include_router(alerts.router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"app": "colearn", "docs": "/docs", "health": f"{settings.api_v1_prefix}/health"}
