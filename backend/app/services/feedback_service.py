"""Load private student context and persist release-ready feedback."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.agents.common import runner
from app.agents.feedback.graph import feedback_validation_errors
from app.models.analytics import TopicMastery
from app.models.assignment import Assignment, GradingPackage, Question, RubricCriterion
from app.models.communication import Feedback
from app.models.course import Topic
from app.models.submission import CriterionScore, Evaluation, Submission, SubmissionAnswer


def build_feedback_state(db: Session, evaluation: Evaluation, submission: Submission) -> dict:
    assignment = db.get(Assignment, submission.assignment_id)
    if assignment is None:
        raise ValueError("submission assignment not found")
    questions = (
        db.query(Question).filter_by(assignment_id=assignment.id).order_by(Question.position).all()
    )
    answers = {
        answer.question_id: answer.answer_text
        for answer in db.query(SubmissionAnswer).filter_by(submission_id=submission.id).all()
    }
    package = (
        db.query(GradingPackage)
        .filter_by(assignment_id=assignment.id, version=evaluation.package_version)
        .first()
    )
    package_questions = (package.content or {}).get("questions", []) if package else []
    references = [
        str(row.get("reference_answer", ""))
        for row in package_questions
        if row.get("reference_answer")
    ]
    criterion_rows = (
        db.query(CriterionScore, RubricCriterion, Topic)
        .outerjoin(RubricCriterion, RubricCriterion.id == CriterionScore.criterion_id)
        .outerjoin(Topic, Topic.id == RubricCriterion.topic_id)
        .filter(CriterionScore.evaluation_id == evaluation.id)
        .all()
    )
    results = []
    misconceptions = []
    topic_names = set()
    for score, criterion, topic in criterion_rows:
        misconception = score.matched_misconception
        if misconception:
            misconceptions.append(misconception)
        if topic:
            topic_names.add(topic.name)
        results.append(
            {
                "criterion": criterion.description if criterion else "Question score",
                "final_awarded": float(score.final_awarded or 0),
                "max_marks": float(score.max_marks or (criterion.marks if criterion else 0)),
                "evidence": score.evidence or "",
                "matched_misconception": misconception,
                "topic": topic.name if topic else None,
            }
        )
    mastery = (
        db.query(TopicMastery)
        .join(Topic, Topic.id == TopicMastery.topic_id)
        .filter(
            TopicMastery.student_id == submission.student_id,
            Topic.course_id == assignment.course_id,
            TopicMastery.mastery < 0.6,
        )
        .all()
    )
    topic_by_id = {
        topic.id: topic.name
        for topic in db.query(Topic).filter_by(course_id=assignment.course_id).all()
    }
    weak_topics = [topic_by_id[row.topic_id] for row in mastery if row.topic_id in topic_by_id]
    return {
        "submission_id": str(submission.id),
        "context": [
            {"question_id": str(q.id), "question": q.prompt, "topics": sorted(topic_names)}
            for q in questions
        ],
        "results": results,
        "answers": [{"question_id": str(q.id), "answer": answers.get(q.id, "")} for q in questions],
        "reference_answers": references,
        "detected_misconceptions": list(dict.fromkeys(misconceptions)),
        "weak_topics": weak_topics,
    }


def generate_and_release_feedback(
    db: Session, evaluation: Evaluation, submission: Submission
) -> Feedback:
    existing = db.query(Feedback).filter_by(submission_id=submission.id).first()
    if existing is not None and existing.released_at is not None:
        evaluation.released_at = existing.released_at
        return existing
    state = build_feedback_state(db, evaluation, submission)
    result = runner.start("feedback", f"feedback-{submission.id}", state)
    if result["status"] != "finished":
        raise RuntimeError("feedback graph did not finish")
    final = result["state"]
    feedback_text = evaluation.feedback_draft or final["feedback"]
    if evaluation.feedback_draft:
        errors = feedback_validation_errors(feedback_text, state["reference_answers"])
        if errors:
            raise ValueError("faculty feedback failed safety validation: " + "; ".join(errors))
    released_at = datetime.now(UTC)
    if existing is None:
        existing = Feedback(
            submission_id=submission.id,
            text=feedback_text,
            misconceptions=final.get("misconceptions", []),
            suggested_practice=final.get("suggested_practice", []),
            released_at=released_at,
        )
        db.add(existing)
    else:
        existing.text = feedback_text
        existing.misconceptions = final.get("misconceptions", [])
        existing.suggested_practice = final.get("suggested_practice", [])
        existing.released_at = released_at
    evaluation.released_at = released_at
    db.flush()
    return existing
