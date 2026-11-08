"""Create a deterministic, end-to-end demo course with varied synthetic work.

Run from ``backend/`` after ``alembic upgrade head`` with ``uv run python -m scripts.seed``.
The demo account passwords are for local development only. All generated student work and
grades are synthetic and must not be presented as real learner or faculty data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.agents.authenticity.signals import hashing_embedding
from app.analytics.service import write_mastery_events
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.analytics import FollowupCheck
from app.models.assignment import Assignment, GradingPackage, Question, RubricCriterion
from app.models.communication import Feedback
from app.models.course import Course, Enrollment, Topic
from app.models.enums import AiPolicy, EvalStatus, QuestionType, SubmissionStatus, UserRole
from app.models.submission import CriterionScore, Evaluation, Submission, SubmissionAnswer
from app.models.user import User
from app.services.correction_memory_service import write_correction_memories

FACULTY_EMAIL = "faculty@example.com"
STUDENT_COUNT = 20
COURSE_CODE = "CS210"
TOPICS = [
    "Introduction to Hashing",
    "Hash Functions",
    "Collision Resolution",
    "Open Addressing",
    "Chaining",
    "Load Factor and Rehashing",
    "Applications of Hashing",
    "Complexity Analysis",
    "Hash Tables and Security",
    "Choosing a Data Structure",
]

ASSIGNMENT_SPECS = [
    {
        "title": "Hash table foundations",
        "description": "Explain how hash tables store and retrieve key-value pairs.",
        "days_from_now": -8,
        "submitted_through": 18,
        "late_students": {17, 18},
        "released_through": 8,
        "awaiting_review": {13, 17},
        "failed": {14},
        "running": set(),
        "questions": [
            ("Explain how a hash function supports key lookup in a hash table.", 1),
            ("What is a collision, and how can chaining resolve one?", 2),
        ],
    },
    {
        "title": "Collision handling",
        "description": "Compare collision-resolution strategies and their trade-offs.",
        "days_from_now": -3,
        "submitted_through": 16,
        "late_students": {15, 16},
        "released_through": 5,
        "awaiting_review": {9},
        "failed": set(),
        "running": {10},
        "questions": [
            ("Compare linear probing with separate chaining.", 3),
            ("How does load factor affect lookup performance?", 5),
        ],
    },
    {
        "title": "Applications and trade-offs",
        "description": "Apply hashing concepts to a practical design choice.",
        "days_from_now": 6,
        "submitted_through": 8,
        "late_students": set(),
        "released_through": 4,
        "awaiting_review": {5},
        "failed": set(),
        "running": {6},
        "questions": [
            ("Describe a practical use of a hash table and its expected lookup cost.", 6),
            ("When would a different data structure be a better choice?", 9),
        ],
    },
]

STUDENT_NAMES = [
    "Maya Chen",
    "Ravi Shah",
    "Amara Okafor",
    "Leo Martin",
    "Priya Nair",
    "Mateo Silva",
    "Aisha Khan",
    "Noah Williams",
    "Elena Petrova",
    "Arjun Mehta",
    "Sofia Garcia",
    "Ethan Brown",
    "Zara Ali",
    "Owen Davis",
    "Lina Haddad",
    "Kabir Rao",
    "Nia Johnson",
    "Theo Fischer",
    "Mina Park",
    "Samir Das",
]


def learner_profile(index: int) -> str:
    if index <= 4:
        return "strong"
    if index <= 10:
        return "average"
    if index <= 14:
        return "weak"
    if index <= 16:
        return "near_duplicate"
    return "generic"


def answers_for(profile: str, assignment_index: int) -> list[str]:
    topics = [
        ("hash functions", "collisions"),
        ("linear probing", "load factor"),
        ("caches", "data structure choices"),
    ][assignment_index]
    if profile == "strong":
        return [
            (
                f"A hash function maps a key to an array index. The table stores the key with its "
                f"value, then applies the same function during lookup. A good distribution keeps "
                f"buckets balanced, so average lookup is close to O(1). For {topics[0]}, the index "
                "is only a starting point and the stored key still needs to be checked."
            ),
            (
                "A collision occurs when distinct keys map to the same index. Separate chaining "
                "keeps a small collection at that bucket and compares keys there. Its expected "
                "lookup remains close to O(1) when keys distribute well and load stays controlled."
            ),
        ]
    if profile == "average":
        return [
            (
                f"A hash function turns a key into an index so the value can be found quickly. It "
                f"should spread values around the table. This is useful for {topics[0]} because "
                "different keys can still end up at one index."
            ),
            (
                "A collision is when two keys use the same place. Chaining keeps more than one "
                "item there. The program checks the items to find the right key, so it can take "
                "longer when the table gets crowded."
            ),
        ]
    if profile == "weak":
        return [
            (
                "Hashing is a way to put information somewhere. It is useful because computers "
                "can find things fast. The details depend on the program and the data."
            ),
            (
                "A collision means there is a problem with the data. A table can try another place "
                "or keep the values together. More items can make it slower."
            ),
        ]
    if profile == "near_duplicate":
        return [
            (
                "A hash function maps each key to a table index. The table stores the key with its "
                "value and uses the same function when looking it up. A good distribution keeps "
                "buckets balanced so average lookup is close to O(1). Distinct keys may still land "
                "at the same index."
            ),
            (
                "A collision happens when distinct keys map to one index. Separate chaining keeps "
                "a small collection at that bucket and compares keys there. Its expected lookup "
                "stays close to O(1) when keys are distributed well and load remains controlled."
            ),
        ]
    return [
        (
            "In today's world, technology is very important and data can be useful in many ways. "
            "There are many different things to consider, and the best solution depends on the "
            "situation. Overall, this topic has advantages and disadvantages."
        ),
        (
            "This concept is important because it can make a system better. There are different "
            "approaches and each one has benefits. In conclusion, the choice depends on the "
            "requirements and what the user needs."
        ),
    ]


def marks_for(
    profile: str, assignment_index: int, student_index: int
) -> tuple[list[float], list[float]]:
    marks = {
        "strong": ([5.0, 4.5], [4.5, 4.5]),
        "average": ([3.5, 3.0], [4.0, 3.5]),
        "weak": ([1.5, 1.0], [2.5, 2.0]),
        "near_duplicate": ([3.0, 3.0], [4.0, 4.0]),
        "generic": ([2.0, 1.5], [3.0, 2.5]),
    }
    faculty_marks, ai_marks = marks[profile]
    adjustment = ((student_index + assignment_index) % 3) * 0.25
    return (
        [max(0.0, mark - adjustment) for mark in faculty_marks],
        [min(5.0, mark + adjustment / 2) for mark in ai_marks],
    )


def get_or_create_user(
    db: Session, email: str, name: str, role: UserRole, roll_no: str | None = None
) -> User:
    user = db.query(User).filter_by(email=email).first()
    if user is not None:
        return user
    user = User(
        email=email,
        password_hash=hash_password("faculty-pass" if role == UserRole.faculty else "student-pass"),
        full_name=name,
        role=role,
        roll_no=roll_no,
        native_english=False if role == UserRole.student and roll_no in {"R005", "R011"} else None,
    )
    db.add(user)
    db.flush()
    return user


def seed_topics(db: Session, course: Course) -> list[Topic]:
    rows: list[Topic] = []
    for index, name in enumerate(TOPICS):
        row = db.query(Topic).filter_by(course_id=course.id, name=name).first()
        if row is None:
            row = Topic(course_id=course.id, name=name, weight=1.25 if index < 4 else 1.0)
            db.add(row)
            db.flush()
        rows.append(row)
    return rows


def seed_assignment(
    db: Session,
    faculty: User,
    course: Course,
    students: list[User],
    topics: list[Topic],
    spec: dict,
    assignment_index: int,
) -> tuple[Assignment, int]:
    assignment = db.query(Assignment).filter_by(course_id=course.id, title=spec["title"]).first()
    if assignment is not None:
        return assignment, 0

    now = datetime.now(UTC)
    assignment = Assignment(
        course_id=course.id,
        title=spec["title"],
        description=spec["description"],
        deadline=now + timedelta(days=spec["days_from_now"]),
        allow_late=True,
        late_penalty_pct=10.0,
        max_marks=10,
        grade_weight=1.0,
        ai_policy=AiPolicy.allowed_with_disclosure,
        require_understanding_check=True,
        status="published",
        active_package_version=1,
    )
    db.add(assignment)
    db.flush()

    questions: list[Question] = []
    rubric_rows: list[RubricCriterion] = []
    package_questions = []
    for position, (prompt, topic_index) in enumerate(spec["questions"], start=1):
        question = Question(
            assignment_id=assignment.id,
            position=position,
            prompt=prompt,
            qtype=QuestionType.open_ended,
            max_marks=5,
        )
        db.add(question)
        db.flush()
        criterion = RubricCriterion(
            question_id=question.id,
            package_version=1,
            description=f"Accurately explains the key idea in question {position}.",
            marks=5,
            topic_id=topics[topic_index].id,
            topic_weight=1.0,
        )
        db.add(criterion)
        db.flush()
        questions.append(question)
        rubric_rows.append(criterion)
        package_questions.append(
            {
                "q_id": str(question.id),
                "reference_answer": (
                    "A correct explanation connects the operation to the relevant hash-table "
                    "concept, describes the main trade-off, and accounts for collisions or load."
                ),
                "rubric": [
                    {
                        "criterion": criterion.description,
                        "marks": 5,
                        "topic": str(topics[topic_index].id),
                        "misconceptions": ["Assumes collisions cannot happen"],
                    }
                ],
            }
        )
    db.add(
        GradingPackage(
            assignment_id=assignment.id,
            version=1,
            status="approved",
            content={"questions": package_questions},
            approved_by=faculty.id,
            approved_at=now - timedelta(days=10 - assignment_index),
        )
    )

    created = 0
    for student_index, student in enumerate(students, start=1):
        if student_index > spec["submitted_through"]:
            continue
        profile = learner_profile(student_index)
        response_texts = answers_for(profile, assignment_index)
        is_late = student_index in spec["late_students"]
        if spec["days_from_now"] < 0:
            deadline = assignment.deadline
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            submitted_at = (
                deadline + timedelta(hours=2) if is_late else deadline - timedelta(hours=2)
            )
        else:
            submitted_at = now - timedelta(hours=2)
        submission = Submission(
            assignment_id=assignment.id,
            student_id=student.id,
            submitted_at=submitted_at,
            is_late=is_late,
            status=SubmissionStatus.submitted,
            ai_disclosure="Used a spellchecker for grammar." if student_index % 6 == 0 else None,
        )
        db.add(submission)
        db.flush()
        for question, answer in zip(questions, response_texts, strict=True):
            db.add(
                SubmissionAnswer(
                    submission_id=submission.id,
                    question_id=question.id,
                    answer_text=answer,
                    embedding=hashing_embedding(answer),
                )
            )

        if student_index in spec["failed"]:
            submission.status = SubmissionStatus.needs_attention
            db.add(
                Evaluation(
                    submission_id=submission.id,
                    package_version=1,
                    model="synthetic-demo",
                    ai_total=None,
                    final_total=None,
                    confidence=0.2,
                    status=EvalStatus.failed,
                    faculty_comment="Synthetic demo: evaluation needs another look.",
                )
            )
            created += 1
            continue
        if student_index in spec["running"]:
            submission.status = SubmissionStatus.under_evaluation
            db.add(
                Evaluation(
                    submission_id=submission.id,
                    package_version=1,
                    model="synthetic-demo",
                    confidence=0.58,
                    status=EvalStatus.running,
                )
            )
            created += 1
            continue
        if student_index in spec["awaiting_review"]:
            eval_status = EvalStatus.awaiting_review
            submission.status = SubmissionStatus.pending_review
        else:
            eval_status = EvalStatus.approved
            submission.status = SubmissionStatus.graded

        final_marks, ai_marks = marks_for(profile, assignment_index, student_index)
        confidence = {
            "strong": 0.87,
            "average": 0.68,
            "weak": 0.54,
            "near_duplicate": 0.76,
            "generic": 0.62,
        }[profile]
        released = eval_status == EvalStatus.approved and student_index <= spec["released_through"]
        evaluation = Evaluation(
            submission_id=submission.id,
            package_version=1,
            model="synthetic-demo",
            prompt_version="seed-v1",
            ai_total=sum(ai_marks),
            final_total=sum(final_marks),
            confidence=confidence,
            status=eval_status,
            reviewed_by=faculty.id if eval_status == EvalStatus.approved else None,
            reviewed_at=now - timedelta(days=1) if eval_status == EvalStatus.approved else None,
            released_at=now - timedelta(hours=12) if released else None,
            faculty_comment="Synthetic faculty label for demo data."
            if eval_status == EvalStatus.approved
            else None,
            feedback_draft="Synthetic feedback used for the seeded demo.",
        )
        db.add(evaluation)
        db.flush()
        for index, criterion in enumerate(rubric_rows):
            db.add(
                CriterionScore(
                    evaluation_id=evaluation.id,
                    criterion_id=criterion.id,
                    ai_awarded=ai_marks[index],
                    final_awarded=final_marks[index]
                    if eval_status == EvalStatus.approved
                    else None,
                    max_marks=5,
                    evidence=response_texts[index][:180],
                    matched_misconception=(
                        "Treats a collision as impossible"
                        if profile == "weak" and index == 0
                        else None
                    ),
                    confidence=max(0.2, confidence - index * 0.04),
                    needs_manual=eval_status == EvalStatus.awaiting_review,
                    faculty_note=(
                        "Synthetic note: distinguish the hash index from the stored key."
                        if eval_status == EvalStatus.approved
                        and ai_marks[index] != final_marks[index]
                        else None
                    ),
                )
            )
        if eval_status == EvalStatus.approved:
            write_mastery_events(db, submission, evaluation)
            write_correction_memories(db, evaluation, submission)
        if released:
            db.add(
                Feedback(
                    submission_id=submission.id,
                    text=(
                        "Synthetic demo feedback: explain how the hash function maps a key, "
                        "then connect collisions and load factor to lookup cost."
                    ),
                    misconceptions=(
                        ["A collision means the hash function failed"] if profile == "weak" else []
                    ),
                    suggested_practice=[
                        "Trace two keys through a collision-resolution example.",
                        "Compare expected lookup cost at different load factors.",
                    ],
                    released_at=evaluation.released_at,
                )
            )
        created += 1

    if assignment_index == 0:
        # Include one confident understanding check and one low-scoring check.
        for student_index, score in ((1, 0.9), (13, 0.32)):
            followup_submission = (
                db.query(Submission)
                .filter_by(assignment_id=assignment.id, student_id=students[student_index - 1].id)
                .first()
            )
            if (
                followup_submission is not None
                and db.query(FollowupCheck).filter_by(submission_id=followup_submission.id).first()
                is None
            ):
                db.add(
                    FollowupCheck(
                        submission_id=followup_submission.id,
                        questions=[
                            "Why can two different keys map to the same index?",
                            "How does chaining resolve that collision?",
                        ],
                        answers=[
                            "The hash function maps both keys to one bucket.",
                            "The bucket stores multiple entries and compares keys.",
                        ],
                        score=score,
                        issued_at=now - timedelta(days=1),
                        answered_at=now - timedelta(hours=20),
                        time_limit_sec=420,
                        thread_id=f"seed-followup-{followup_submission.id}",
                        retake_count=0,
                        attempt_history=[],
                    )
                )
    return assignment, created


def seed(db: Session) -> None:
    faculty = get_or_create_user(db, FACULTY_EMAIL, "Dr. Ada Lovelace", UserRole.faculty)
    course = db.query(Course).filter_by(code=COURSE_CODE, faculty_id=faculty.id).first()
    if course is None:
        course = Course(
            faculty_id=faculty.id,
            code=COURSE_CODE,
            name="Data Structures",
            term="Fall 2026",
        )
        db.add(course)
        db.flush()

    topics = seed_topics(db, course)
    students = [
        get_or_create_user(
            db,
            f"student{index}@example.com",
            STUDENT_NAMES[index - 1],
            UserRole.student,
            roll_no=f"R{index:03d}",
        )
        for index in range(1, STUDENT_COUNT + 1)
    ]
    for student in students:
        if (
            db.query(Enrollment).filter_by(course_id=course.id, student_id=student.id).first()
            is None
        ):
            db.add(Enrollment(course_id=course.id, student_id=student.id))

    new_submissions = 0
    for index, spec in enumerate(ASSIGNMENT_SPECS):
        _assignment, created = seed_assignment(db, faculty, course, students, topics, spec, index)
        new_submissions += created
    db.commit()
    print(
        f"Seeded/verified 1 faculty, {len(students)} students, 1 course, "
        f"{len(topics)} topics, {len(ASSIGNMENT_SPECS)} assignments; "
        f"created {new_submissions} synthetic submissions/evaluations."
    )
    print(f"Faculty login: {FACULTY_EMAIL} / faculty-pass")
    print("Student login: student1@example.com through student20@example.com / student-pass")
    print("All seeded submissions and faculty marks are synthetic demo data.")
    print("Seeded rubric corrections populate the co-learning memory with synthetic examples.")


if __name__ == "__main__":
    with SessionLocal() as session:
        seed(session)
