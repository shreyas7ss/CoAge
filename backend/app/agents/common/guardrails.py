"""Guardrails: untrusted-data wrapping, anonymization, injection heuristics, validation."""

import copy
import re

UNTRUSTED_START = "<<<STUDENT_ANSWER"
UNTRUSTED_END = "STUDENT_ANSWER>>>"


def wrap_untrusted(text: str) -> str:
    """Wrap untrusted student text in clear delimiters for prompt injection defence."""
    return f"{UNTRUSTED_START}\n{text}\n{UNTRUSTED_END}"


def strip_identifiers(text: str) -> str:
    """Remove name/email/roll-number patterns before any LLM call (anonymization)."""
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[email]", text)
    text = re.sub(r"\broll\s*no\.?\s*[:#-]?\s*[A-Za-z0-9-]+", "[roll_no]", text, flags=re.I)
    text = re.sub(r"\b(?:name|student)\s*:\s*[^\n]+", "[name]", text, flags=re.I)
    return text


def sanitize_submission(text: str) -> str:
    """Anonymize and remove common explicit grading instructions from student data."""
    text = strip_identifiers(text)
    directive = re.compile(
        r"\b(?:ignore\s+(?:all\s+)?(?:previous\s+)?instructions?|"
        r"disregard\s+(?:all\s+)?(?:previous\s+)?instructions?|"
        r"give\s+(?:me\s+)?full\s+marks?|award\s+(?:me\s+)?full\s+marks?|"
        r"you\s+are\s+now|system\s+prompt)\b[^.!?\n]*[.!?]?",
        re.IGNORECASE,
    )
    return directive.sub("[grading instruction removed]", text)


INJECTION_MARKERS = (
    "ignore previous instructions",
    "ignore all instructions",
    "ignore the instructions",
    "disregard",
    "give full marks",
    "award full marks",
    "system prompt",
    "you are now",
    "roleplay",
)


def detect_injection(text: str) -> list[str]:
    """Cheap heuristic injection detection. Returns matched markers (never obeyed)."""
    lower = text.lower()
    return [marker for marker in INJECTION_MARKERS if marker in lower]


def validate_range(value: float, minimum: float, maximum: float) -> bool:
    """Validate that an LLM-returned number falls within ``[minimum, maximum]``."""
    return minimum <= value <= maximum


def validate_package(
    package: dict, questions: list[dict], topics: list[dict]
) -> tuple[list[str], dict]:
    """Deterministic grading-package validation with a single marks auto-repair.

    Returns ``(errors, repaired_package)``. Checks that every criterion has a valid
    topic and that each question's criterion marks sum exactly to its ``max_marks``
    (rescaling once if the total is positive).
    """
    errors: list[str] = []
    topic_ids = {t["id"] for t in topics}
    max_by_qid = {q["q_id"]: float(q["max_marks"]) for q in questions}
    repaired = copy.deepcopy(package)

    for question in repaired.get("questions", []):
        qid = question.get("q_id")
        if qid not in max_by_qid:
            errors.append(f"Question {qid!r} does not match any assignment question")
            continue
        max_marks = max_by_qid[qid]
        rubric = question.get("rubric") or []
        if not rubric:
            errors.append(f"Question {qid}: no rubric criteria")
            continue
        for criterion in rubric:
            topic = criterion.get("topic")
            if not topic or topic not in topic_ids:
                errors.append(
                    f"Question {qid}: criterion {criterion.get('criterion')!r} has an invalid topic"
                )
        marks = [float(criterion.get("marks") or 0) for criterion in rubric]
        total = sum(marks)
        if abs(total - max_marks) > 1e-6:
            if total > 0:
                scaled = [round(m * max_marks / total, 2) for m in marks]
                scaled[-1] = round(scaled[-1] + (max_marks - sum(scaled)), 2)
                for criterion, mark in zip(rubric, scaled, strict=False):
                    criterion["marks"] = mark
                errors.append(f"Question {qid}: criteria marks auto-adjusted to sum to {max_marks}")
            else:
                errors.append(f"Question {qid}: criteria marks sum to zero")

    return errors, repaired
