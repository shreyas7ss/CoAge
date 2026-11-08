"""Pgvector-backed correction retrieval plus faculty correction writes."""

from sqlalchemy.orm import Session

from app.agents.authenticity.signals import (
    EMBEDDING_DIMENSIONS,
    cosine_similarity,
    criterion_signature,
    hashing_embedding,
)
from app.agents.common.guardrails import sanitize_submission
from app.models.assignment import Question, RubricCriterion
from app.models.authenticity import CorrectionMemory
from app.models.submission import CriterionScore, Evaluation, Submission, SubmissionAnswer


def retrieve_corrections(
    db: Session, description: str, question_type: str, answer: str, limit: int = 3
) -> list[dict]:
    signature = criterion_signature(description, question_type)
    query_vector = hashing_embedding(f"{description}\n{answer}", EMBEDDING_DIMENSIONS)
    query = db.query(CorrectionMemory).filter_by(criterion_signature=signature)
    if db.get_bind().dialect.name == "postgresql":
        distance = CorrectionMemory.embedding.cosine_distance(query_vector)
        memories = query.order_by(distance).limit(limit).all()
    else:
        memories = query.all()
        memories.sort(
            key=lambda row: cosine_similarity(query_vector, row.embedding or []), reverse=True
        )
        memories = memories[:limit]
    return [
        {
            "student_text_snippet": row.student_text_snippet,
            "ai_awarded": float(row.ai_awarded),
            "final_awarded": float(row.final_awarded),
            "faculty_note": row.faculty_note,
        }
        for row in memories
    ]


def write_correction_memories(
    db: Session,
    evaluation: Evaluation,
    submission: Submission,
    criterion_notes: dict[str, str] | None = None,
) -> int:
    notes = criterion_notes or {}
    rows = (
        db.query(CriterionScore, RubricCriterion, Question)
        .join(RubricCriterion, RubricCriterion.id == CriterionScore.criterion_id)
        .join(Question, Question.id == RubricCriterion.question_id)
        .filter(CriterionScore.evaluation_id == evaluation.id)
        .all()
    )
    saved = 0
    for score, criterion, question in rows:
        ai = float(score.ai_awarded or 0)
        final = float(score.final_awarded or 0)
        note = (notes.get(str(criterion.id)) or score.faculty_note or "").strip()
        if abs(final - ai) <= 1e-9 and not note:
            continue
        answer = (
            db.query(SubmissionAnswer)
            .filter_by(submission_id=submission.id, question_id=question.id)
            .first()
        )
        snippet = sanitize_submission(answer.answer_text if answer else "")[:1000]
        if not snippet:
            continue
        description = criterion.description
        qtype = question.qtype.value
        db.add(
            CorrectionMemory(
                criterion_signature=criterion_signature(description, qtype),
                question_type=qtype,
                student_text_snippet=snippet,
                ai_awarded=ai,
                final_awarded=final,
                faculty_note=note or None,
                embedding=hashing_embedding(f"{description}\n{snippet}", EMBEDDING_DIMENSIONS),
            )
        )
        saved += 1
    return saved
