"""Faculty-only analytics endpoints, backed by deterministic metric functions."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.analytics import metrics
from app.analytics.service import approved_evaluation_rows, score_rows, topic_cell_scores
from app.core.config import settings
from app.core.deps import require_course_faculty, require_faculty
from app.db.session import get_db
from app.models.analytics import FollowupCheck, TopicMastery, TopicMasteryEvent
from app.models.assignment import Assignment, Question
from app.models.course import Course, Enrollment, Topic
from app.models.enums import EvalStatus
from app.models.submission import Evaluation, Submission
from app.models.user import User

router = APIRouter(tags=["analytics"])


def _course(db: Session, course_id: uuid.UUID, faculty: User) -> Course:
    return require_course_faculty(db, course_id, faculty)


def _student_analytics(db: Session, course: Course, student_id: uuid.UUID) -> dict:
    topics = db.query(Topic).filter_by(course_id=course.id).all()
    mastery_rows = (
        db.query(TopicMastery, Topic)
        .join(Topic, Topic.id == TopicMastery.topic_id)
        .filter(TopicMastery.student_id == student_id, Topic.course_id == course.id)
        .all()
    )
    mastery_by_topic = {
        row.topic_id: {
            "topic_id": str(row.topic_id),
            "mastery": float(row.mastery),
            "confidence": float(row.confidence),
            "n_events": row.n_events,
        }
        for row, _topic in mastery_rows
    }
    topic_values = [
        {
            "mastery": mastery_by_topic.get(topic.id, {}).get("mastery"),
            "weight": float(topic.weight),
        }
        for topic in topics
    ]
    subject = metrics.subject_understanding(topic_values)
    events = (
        db.query(TopicMasteryEvent)
        .join(Topic, Topic.id == TopicMasteryEvent.topic_id)
        .filter(TopicMasteryEvent.student_id == student_id, Topic.course_id == course.id)
        .order_by(TopicMasteryEvent.created_at, TopicMasteryEvent.id)
        .all()
    )
    per_assignment: dict[uuid.UUID, list[float]] = defaultdict(list)
    submission_assignment = {
        submission.id: assignment.id
        for submission, assignment in db.query(Submission, Assignment)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .filter(Submission.student_id == student_id, Assignment.course_id == course.id)
        .all()
    }
    for event in events:
        assignment_id = submission_assignment.get(event.submission_id)
        if assignment_id:
            per_assignment[assignment_id].append(float(event.score))
    assignment_scores = [
        sum(values) / len(values)
        for _assignment_id, values in sorted(
            per_assignment.items(),
            key=lambda item: min(
                event.created_at
                for event in events
                if submission_assignment.get(event.submission_id) == item[0]
            ),
        )
    ]
    trend = metrics.mastery_trend(assignment_scores)
    assignments = db.query(Assignment).filter_by(course_id=course.id).all()
    now = datetime.now(UTC)
    due_assignments = [a for a in assignments if a.deadline <= now]
    submissions = (
        db.query(Submission)
        .filter(
            Submission.student_id == student_id,
            Submission.assignment_id.in_([a.id for a in due_assignments]),
        )
        .all()
        if due_assignments
        else []
    )
    submitted_ids = {s.assignment_id for s in submissions}
    missed = len(due_assignments) - len(submitted_ids)
    on_time = sum(not s.is_late for s in submissions)
    late = sum(s.is_late for s in submissions)
    return {
        "student_id": str(student_id),
        **subject,
        "topics": [
            mastery_by_topic.get(
                t.id, {"topic_id": str(t.id), "mastery": None, "confidence": 0.0, "n_events": 0}
            )
            | {"name": t.name}
            for t in topics
        ],
        "trend": trend,
        "flags": metrics.student_flags(
            list(mastery_by_topic.values()), missed, trend, settings.weak_topic_threshold
        ),
        "submission_reliability": metrics.submission_reliability(
            on_time, late, missed, len(due_assignments)
        ),
    }


@router.get("/courses/{course_id}/analytics/heatmap")
def analytics_heatmap(
    course_id: uuid.UUID, faculty: User = Depends(require_faculty), db: Session = Depends(get_db)
) -> dict:
    course = _course(db, course_id, faculty)
    evaluations = approved_evaluation_rows(db, course.id)
    values = topic_cell_scores(db, evaluations)
    topics = db.query(Topic).filter_by(course_id=course.id).order_by(Topic.name).all()
    assignments = (
        db.query(Assignment).filter_by(course_id=course.id).order_by(Assignment.deadline).all()
    )
    cells = []
    for topic in topics:
        for assignment in assignments:
            cell = metrics.heatmap_cell(values.get((topic.id, assignment.id), []))
            cells.append(
                {
                    "topic_id": str(topic.id),
                    "topic": topic.name,
                    "assignment_id": str(assignment.id),
                    "assignment": assignment.title,
                    **cell,
                }
            )
    enrollment_count = db.query(Enrollment).filter_by(course_id=course.id).count()
    completeness_rows = []
    for assignment in assignments:
        submissions = db.query(Submission).filter_by(assignment_id=assignment.id).all()
        submitted = sum(sub.submitted_at is not None for sub in submissions)
        late = sum(sub.submitted_at is not None and sub.is_late for sub in submissions)
        completeness_rows.append(
            {
                "assignment_id": str(assignment.id),
                "title": assignment.title,
                **metrics.completeness(submitted, late, max(0, enrollment_count - submitted)),
            }
        )
    return {"course_id": str(course.id), "cells": cells, "completeness": completeness_rows}


@router.get("/courses/{course_id}/analytics/topics")
def analytics_topics(
    course_id: uuid.UUID, faculty: User = Depends(require_faculty), db: Session = Depends(get_db)
) -> dict:
    course = _course(db, course_id, faculty)
    topics = db.query(Topic).filter_by(course_id=course.id).order_by(Topic.name).all()
    students = [
        row[0] for row in db.query(Enrollment.student_id).filter_by(course_id=course.id).all()
    ]
    mastery = (
        db.query(TopicMastery).filter(TopicMastery.student_id.in_(students)).all()
        if students
        else []
    )
    by_topic: dict[uuid.UUID, list[float]] = defaultdict(list)
    for row in mastery:
        by_topic[row.topic_id].append(float(row.mastery))
    results = []
    for topic in topics:
        stats = metrics.below_threshold(by_topic[topic.id], settings.weak_topic_threshold)
        results.append(
            {
                "topic_id": str(topic.id),
                "name": topic.name,
                **stats,
                "weak_topic_alert": stats["n"] >= 8
                and stats["fraction"] is not None
                and stats["fraction"] >= 0.4,
            }
        )
    evaluations = approved_evaluation_rows(db, course.id)
    rows = score_rows(db, [e.id for e, _s, _a in evaluations])
    misconceptions = metrics.misconception_counts(
        (
            str(criterion.topic_id) if criterion and criterion.topic_id else None,
            score.matched_misconception,
        )
        for score, criterion, _question in rows
    )
    return {"course_id": str(course.id), "topics": results, "top_misconceptions": misconceptions}


@router.get("/courses/{course_id}/analytics/distribution")
def analytics_distribution(
    course_id: uuid.UUID,
    assignment_id: uuid.UUID | None = None,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> dict:
    course = _course(db, course_id, faculty)
    if assignment_id is not None:
        assignment = db.get(Assignment, assignment_id)
        if assignment is None or assignment.course_id != course.id:
            raise HTTPException(status_code=404, detail="Assignment not found")
    rows = approved_evaluation_rows(db, course.id, assignment_id)
    scores = [
        float(e.final_total or 0) / float(a.max_marks)
        for e, _s, a in rows
        if float(a.max_marks) > 0
    ]
    return metrics.score_distribution(scores)


@router.get("/assignments/{assignment_id}/analytics/questions")
def analytics_questions(
    assignment_id: uuid.UUID,
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> dict:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _course(db, assignment.course_id, faculty)
    evaluations = approved_evaluation_rows(db, assignment.course_id, assignment.id)
    eval_by_submission = {s.id: e.id for e, s, _a in evaluations}
    data: dict[uuid.UUID, dict[uuid.UUID, dict[str, float]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    misconceptions: dict[uuid.UUID, list[tuple[str | None, str | None]]] = defaultdict(list)
    for score, _criterion, question in score_rows(db, list(eval_by_submission.values())):
        if question is None or score.final_awarded is None:
            continue
        submission_id = next(s.id for _e, s, _a in evaluations if _e.id == score.evaluation_id)
        data[question.id][submission_id]["awarded"] = data[question.id][submission_id].get(
            "awarded", 0
        ) + float(score.final_awarded)
        data[question.id][submission_id]["max"] = data[question.id][submission_id].get(
            "max", 0
        ) + float(score.max_marks or 0)
        misconceptions[question.id].append((None, score.matched_misconception))
    output = []
    for question in (
        db.query(Question).filter_by(assignment_id=assignment.id).order_by(Question.position)
    ):
        rows = []
        for submission_id, student_scores in data[question.id].items():
            maximum = student_scores.get("max", 0)
            if maximum <= 0:
                continue
            other_awarded = sum(
                scores["awarded"]
                for qid, students_for_q in data.items()
                if qid != question.id
                and (scores := students_for_q.get(submission_id))
                and scores.get("max", 0) > 0
            )
            other_max = sum(
                scores["max"]
                for qid, students_for_q in data.items()
                if qid != question.id
                and (scores := students_for_q.get(submission_id))
                and scores.get("max", 0) > 0
            )
            other_total = other_awarded / other_max if other_max else 0.0
            rows.append({"ratio": student_scores["awarded"] / maximum, "other_total": other_total})
        output.append(
            {
                "question_id": str(question.id),
                "position": question.position,
                **metrics.item_analysis(rows),
                "misconceptions": metrics.misconception_counts(misconceptions[question.id]),
            }
        )
    return {"assignment_id": str(assignment.id), "questions": output}


@router.get("/courses/{course_id}/analytics/students")
def analytics_students(
    course_id: uuid.UUID, faculty: User = Depends(require_faculty), db: Session = Depends(get_db)
) -> dict:
    course = _course(db, course_id, faculty)
    student_ids = [
        row[0] for row in db.query(Enrollment.student_id).filter_by(course_id=course.id).all()
    ]
    return {
        "course_id": str(course.id),
        "students": [_student_analytics(db, course, student_id) for student_id in student_ids],
    }


@router.get("/students/{student_id}/analytics")
def analytics_student(
    student_id: uuid.UUID,
    course_id: uuid.UUID = Query(...),
    faculty: User = Depends(require_faculty),
    db: Session = Depends(get_db),
) -> dict:
    course = _course(db, course_id, faculty)
    if db.query(Enrollment).filter_by(course_id=course.id, student_id=student_id).first() is None:
        raise HTTPException(status_code=404, detail="Student not enrolled in this course")
    return _student_analytics(db, course, student_id)


@router.get("/courses/{course_id}/analytics/ai-quality")
def analytics_ai_quality(
    course_id: uuid.UUID, faculty: User = Depends(require_faculty), db: Session = Depends(get_db)
) -> dict:
    course = _course(db, course_id, faculty)
    evaluations = approved_evaluation_rows(db, course.id)
    score_models = [
        score
        for score, _criterion, _question in score_rows(db, [e.id for e, _s, _a in evaluations])
    ]
    rows = [
        {
            "ai_awarded": float(s.ai_awarded) if s.ai_awarded is not None else None,
            "final_awarded": float(s.final_awarded) if s.final_awarded is not None else None,
            "max_marks": float(s.max_marks) if s.max_marks is not None else None,
            "confidence": float(s.confidence) if s.confidence is not None else None,
        }
        for s in score_models
    ]
    return metrics.agreement_metrics(rows)


@router.get("/courses/{course_id}/analytics/understanding-gap")
def analytics_understanding_gap(
    course_id: uuid.UUID, faculty: User = Depends(require_faculty), db: Session = Depends(get_db)
) -> dict:
    course = _course(db, course_id, faculty)
    rows = (
        db.query(FollowupCheck, Submission, Assignment, Evaluation)
        .join(Submission, Submission.id == FollowupCheck.submission_id)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .join(Evaluation, Evaluation.submission_id == Submission.id)
        .filter(
            Assignment.course_id == course.id,
            FollowupCheck.answered_at.is_not(None),
            FollowupCheck.score.is_not(None),
            Evaluation.status == EvalStatus.approved,
        )
        .order_by(Assignment.deadline, FollowupCheck.answered_at)
        .all()
    )
    by_student: dict[uuid.UUID, list[dict]] = defaultdict(list)
    for check, submission, assignment, evaluation in rows:
        if not assignment.max_marks or check.score is None:
            continue
        submission_score = float(evaluation.final_total or 0) / float(assignment.max_marks)
        followup_score = float(check.score)
        by_student[submission.student_id].append(
            {
                "assignment_id": str(assignment.id),
                "submission_id": str(submission.id),
                "submission_score": submission_score,
                "followup_score": followup_score,
                "gap": metrics.understanding_gap(submission_score, followup_score),
                "answered_at": check.answered_at.isoformat() if check.answered_at else None,
            }
        )
    students = []
    for student_id, gaps in by_student.items():
        students.append(
            {
                "student_id": str(student_id),
                "gaps": gaps,
                "trend": gaps[-1]["gap"] - gaps[0]["gap"] if len(gaps) > 1 else None,
            }
        )
    return {"course_id": str(course.id), "available": bool(students), "students": students}
