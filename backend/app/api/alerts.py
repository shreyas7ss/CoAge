"""Faculty alert listing, resolution, and manual monitoring trigger."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import require_course_faculty, require_faculty
from app.db.session import get_db
from app.models.communication import Alert
from app.models.user import User
from app.services.monitoring_service import run_monitoring

router = APIRouter(tags=["alerts"])


def _alert_or_404(db: Session, alert_id: uuid.UUID) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


def _alert_payload(alert: Alert) -> dict:
    return {
        "id": str(alert.id),
        "course_id": str(alert.course_id),
        "kind": alert.kind,
        "target_student_id": str(alert.target_student_id) if alert.target_student_id else None,
        "target_assignment_id": str(alert.target_assignment_id)
        if alert.target_assignment_id
        else None,
        "topic_id": str(alert.topic_id) if alert.topic_id else None,
        "payload": alert.payload,
        "status": alert.status,
        "created_at": alert.created_at.isoformat(),
    }


@router.get("/courses/{course_id}/alerts")
def list_alerts(
    course_id: uuid.UUID,
    alert_status: Literal["open", "resolved", "all"] = Query("open", alias="status"),
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> list[dict]:
    require_course_faculty(db, course_id, faculty)
    query = db.query(Alert).filter(Alert.course_id == course_id)
    if alert_status != "all":
        query = query.filter(Alert.status == alert_status)
    return [_alert_payload(alert) for alert in query.order_by(Alert.created_at.desc()).all()]


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: uuid.UUID,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> dict:
    alert = _alert_or_404(db, alert_id)
    require_course_faculty(db, alert.course_id, faculty)
    alert.status = "resolved"
    db.commit()
    db.refresh(alert)
    return _alert_payload(alert)


@router.post("/courses/{course_id}/monitoring/run", status_code=status.HTTP_202_ACCEPTED)
def manual_monitoring(
    course_id: uuid.UUID,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> dict:
    require_course_faculty(db, course_id, faculty)
    result = run_monitoring(db, course_id)
    return {key: value for key, value in result.items() if key != "alerts"}
