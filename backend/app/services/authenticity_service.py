"""Signal computation and faculty-only authenticity report persistence."""

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.agents.authenticity.signals import (
    EMBEDDING_DIMENSIONS,
    concern_level,
    cosine_similarity,
    hashing_embedding,
    neutral_signal,
    raised_signal,
    style_drift,
    style_features,
    trigram_jaccard,
    unavailable_signal,
)
from app.core.config import settings
from app.models.analytics import FollowupCheck
from app.models.assignment import Assignment, Question, RubricCriterion
from app.models.authenticity import AuthenticityReport, ProcessEvent, WritingBaseline
from app.models.course import Course, Topic
from app.models.submission import Submission, SubmissionAnswer
from app.models.user import User

URL_RE = re.compile(r"https?://[^\s]+", re.I)
WORD_RE = re.compile(r"[A-Za-z]{4,}")


def _answers(db: Session, submission: Submission) -> list[SubmissionAnswer]:
    return db.query(SubmissionAnswer).filter_by(submission_id=submission.id).all()


def _style_signal(db: Session, submission: Submission, text: str) -> dict:
    baseline = db.get(WritingBaseline, submission.student_id)
    words = len(text.split())
    if words < 150 or baseline is None or baseline.n_samples < 2:
        samples = baseline.n_samples if baseline else 0
        return unavailable_signal(
            "S2", f"Style baseline is insufficient ({samples} qualifying samples).", 2
        )
    drift = style_drift(style_features(text), baseline.features)
    if drift is None:
        return unavailable_signal("S2", "No comparable writing features were available.", 2)
    if drift > settings.authenticity_style_drift_threshold:
        return raised_signal(
            "S2", f"Writing style differs from the student's baseline (drift {drift:.2f}).", 2
        )
    return neutral_signal(
        "S2", f"Writing style is within the student's baseline range (drift {drift:.2f}).", 2
    )


def _process_signal(db: Session, submission: Submission, text: str, enabled: bool) -> dict:
    if not enabled:
        return unavailable_signal("S3", "Process logging is not enabled for this course.", 2)
    rows = db.query(ProcessEvent).filter_by(submission_id=submission.id).all()
    if not rows:
        return unavailable_signal("S3", "No process event data was recorded.", 2)
    word_count = len(WORD_RE.findall(text))
    paste_pct = max((float(row.meta.get("paste_size_pct", 0)) for row in rows), default=0)
    active_seconds = sum(float(row.meta.get("active_seconds", 0)) for row in rows)
    draft_saves = sum(int(row.meta.get("draft_saves", 0)) for row in rows)
    reasons = []
    if paste_pct >= 0.70:
        reasons.append("a single paste supplied at least 70% of the final answer")
    if active_seconds and active_seconds < max(60, word_count * 0.3):
        reasons.append("recorded active writing time was unusually short for the answer length")
    if draft_saves == 0 and word_count >= 300:
        reasons.append("no draft saves were recorded for a long answer")
    if reasons:
        return raised_signal("S3", "; ".join(reasons) + ".", 2)
    return neutral_signal("S3", "Recorded process activity did not meet the review thresholds.", 2)


def _similarity_signal(
    db: Session, submission: Submission, answers: list[SubmissionAnswer]
) -> dict:
    answer_text = {row.question_id: row.answer_text for row in answers}
    if not answers or sum(len(text.split()) for text in answer_text.values()) < 30:
        return unavailable_signal(
            "S4", "Answer text is too short for a reliable similarity comparison.", 2
        )
    peers: list[tuple[uuid.UUID, float, str]] = []
    for row in answers:
        query_vector = row.embedding or hashing_embedding(row.answer_text, EMBEDDING_DIMENSIONS)
        query = (
            db.query(SubmissionAnswer, Submission)
            .join(Submission, Submission.id == SubmissionAnswer.submission_id)
            .filter(
                Submission.assignment_id == submission.assignment_id,
                Submission.student_id != submission.student_id,
                SubmissionAnswer.question_id == row.question_id,
                SubmissionAnswer.embedding.is_not(None),
            )
        )
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            distance = SubmissionAnswer.embedding.cosine_distance(query_vector).label("distance")
            peer_rows = (
                db.query(SubmissionAnswer, Submission, distance)
                .join(Submission, Submission.id == SubmissionAnswer.submission_id)
                .filter(
                    Submission.assignment_id == submission.assignment_id,
                    Submission.student_id != submission.student_id,
                    SubmissionAnswer.question_id == row.question_id,
                    SubmissionAnswer.embedding.is_not(None),
                )
                .order_by(distance)
                .limit(10)
                .all()
            )
            peers.extend(
                (peer_submission.id, 1 - float(distance_value), peer_answer.answer_text)
                for peer_answer, peer_submission, distance_value in peer_rows
            )
        else:
            peers.extend(
                (
                    peer_submission.id,
                    cosine_similarity(query_vector, peer_answer.embedding or []),
                    peer_answer.answer_text,
                )
                for peer_answer, peer_submission in query.all()
            )
    if not peers:
        return unavailable_signal("S4", "No comparable class answers are available.", 2)
    matches = [
        peer
        for peer in peers
        if peer[1] >= settings.authenticity_similarity_threshold
        and any(trigram_jaccard(answer, peer[2]) >= 0.75 for answer in answer_text.values())
    ]
    if matches:
        ids = sorted({str(peer[0]) for peer in matches})
        return {
            **raised_signal(
                "S4",
                f"A highly similar answer structure was found in {len(ids)} other submission(s).",
                2,
            ),
            "similar_submission_ids": ids,
        }
    return neutral_signal("S4", "No unusually similar answer structures were found.", 2)


def _alignment_signal(db: Session, assignment: Assignment, text: str) -> dict:
    topics = (
        db.query(Topic)
        .join(RubricCriterion, RubricCriterion.topic_id == Topic.id)
        .join(Question, Question.id == RubricCriterion.question_id)
        .filter(
            Question.assignment_id == assignment.id,
            RubricCriterion.package_version == assignment.active_package_version,
        )
        .distinct()
        .all()
    )
    if not topics:
        return unavailable_signal("S5", "No course topic mapping is available for alignment.", 1)
    normalized = text.lower()
    expected = [topic.name for topic in topics if len(topic.name.strip()) >= 3]
    missing = [name for name in expected if name.lower() not in normalized]
    malformed_urls = [
        url for url in URL_RE.findall(text) if not re.match(r"https?://[^.\s]+\.[^\s]+", url)
    ]
    reasons = []
    if expected and len(missing) / len(expected) >= 0.5:
        reasons.append("the answers do not use several of the topics taught for this assignment")
    if malformed_urls:
        reasons.append("one or more citations or URLs have a malformed format")
    if reasons:
        return raised_signal("S5", "; ".join(reasons) + ".", 1)
    return neutral_signal(
        "S5", "The answers use course topic terms and no malformed URL format was found.", 1
    )


def build_signals(
    db: Session, submission: Submission, assignment: Assignment
) -> tuple[list[dict], list[str], dict]:
    answer_rows = _answers(db, submission)
    text = "\n\n".join(row.answer_text for row in answer_rows)
    course = db.get(Course, assignment.course_id)
    student = db.get(User, submission.student_id)
    followup = (
        db.query(FollowupCheck)
        .filter(FollowupCheck.submission_id == submission.id, FollowupCheck.score.is_not(None))
        .order_by(FollowupCheck.answered_at.desc())
        .first()
    )
    if followup is None:
        s1 = unavailable_signal("S1", "No understanding check has been completed.", 3)
    else:
        score = float(followup.score or 0)
        s1 = (
            neutral_signal("S1", f"Follow-up check completed with a score of {score:.2f}.", 3)
            if score >= 0.7
            else raised_signal(
                "S1", f"Follow-up answers showed limited understanding (score {score:.2f}).", 3
            )
        )
    signals = [
        s1,
        _style_signal(db, submission, text),
        _process_signal(db, submission, text, bool(course and course.process_logging_enabled)),
        _similarity_signal(db, submission, answer_rows),
        _alignment_signal(db, assignment, text),
        unavailable_signal("S6", "Optional text detector is disabled.", 0.5),
    ]
    if any(
        q.qtype.value == "code"
        for q in db.query(Question).filter_by(assignment_id=assignment.id).all()
    ):
        signals.append(unavailable_signal("S7", "Code provenance checks are not configured.", 2))
    caveats = []
    baseline = db.get(WritingBaseline, submission.student_id)
    if baseline is None or baseline.n_samples < 5:
        caveats.append(
            f"Only {baseline.n_samples if baseline else 0} prior writing samples are available."
        )
    if student is not None and student.native_english is False:
        caveats.append(
            "The student self-reports non-native English; style signals may be less reliable."
        )
    if any(
        q.qtype.value == "code"
        for q in db.query(Question).filter_by(assignment_id=assignment.id).all()
    ):
        caveats.append("This assignment includes code; code provenance checks are not configured.")
    policy = {
        "ai_policy": assignment.ai_policy.value,
        "student_disclosure": submission.ai_disclosure,
        "interpretation": "understanding signals; AI use is permitted by the assignment policy"
        if assignment.ai_policy.value != "prohibited"
        else "understanding and provenance signals",
    }
    return signals, caveats, policy


def save_report(db: Session, submission: Submission, assignment: Assignment) -> AuthenticityReport:
    signals, caveats, policy = build_signals(db, submission, assignment)
    followup = next((s for s in signals if s["id"] == "S1" and s["status"] == "neutral"), None)
    report = db.query(AuthenticityReport).filter_by(submission_id=submission.id).first()
    if report is None:
        report = AuthenticityReport(
            submission_id=submission.id,
            concern_level="insufficient_evidence",
            signals=signals,
            caveats=caveats,
            policy=policy,
        )
        db.add(report)
    report.signals = signals
    report.caveats = caveats
    report.policy = policy
    report.concern_level = concern_level(signals, followup_passed=followup is not None)
    return report


def update_baseline(db: Session, student_id: uuid.UUID, text: str) -> bool:
    if len(text.split()) < 150:
        return False
    incoming = style_features(text)
    baseline = db.get(WritingBaseline, student_id)
    if baseline is None:
        baseline = WritingBaseline(
            student_id=student_id, features={}, n_samples=0, updated_at=datetime.now(UTC)
        )
        db.add(baseline)
    n = baseline.n_samples
    merged = {}
    for name, value in incoming.items():
        old = baseline.features.get(name, {"mean": value, "std": 0.0})
        old_mean, old_std = float(old.get("mean", value)), float(old.get("std", 0))
        new_mean = old_mean + (value - old_mean) / (n + 1)
        old_m2 = old_std * old_std * max(0, n - 1)
        new_m2 = old_m2 + (value - old_mean) * (value - new_mean)
        merged[name] = {"mean": new_mean, "std": (new_m2 / n) ** 0.5 if n > 0 else 0.0}
    baseline.features = merged
    baseline.n_samples = n + 1
    baseline.updated_at = datetime.now(UTC)
    return True


def update_baseline_for_submission(
    db: Session, submission: Submission, report: AuthenticityReport
) -> bool:
    if report.baseline_updated or report.concern_level != "low":
        return False
    text = "\n\n".join(row.answer_text for row in _answers(db, submission))
    changed = update_baseline(db, submission.student_id, text)
    if changed:
        report.baseline_updated = True
    return changed
