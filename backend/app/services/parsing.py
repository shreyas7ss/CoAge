"""Question-paper and submission parsing (PDF/docx/text)."""

import io
import re

from docx import Document
from pypdf import PdfReader

_QUESTION_RE = re.compile(r"(?:^|\n)\s*(?:Q(?:uestion)?\s*\d+[.:)]|\d+\s*[.)]\s)", re.I)


def extract_text_from_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_text_from_docx(content: bytes) -> str:
    doc = Document(io.BytesIO(content))
    return "\n".join(paragraph.text for paragraph in doc.paragraphs)


def _looks_like_mcq(text: str) -> bool:
    return bool(re.search(r"(?:^|\n)\s*[A-D][.)]\s", text))


def parse_submission_answers(text: str, questions: list[dict]) -> dict[str, str]:
    """Map submission text to per-question answers (best-effort).

    ``questions`` is ``[{q_id, position}]``. Splits on question markers (``Q1.``,
    ``Question 2``, ``3)``). Fallback: a single question gets the whole text; with
    multiple questions and no markers, the whole text goes to the first question.
    """
    answers = {q["q_id"]: "" for q in questions}
    if not questions:
        return answers
    if len(questions) == 1:
        answers[questions[0]["q_id"]] = text.strip()
        return answers

    marker_re = re.compile(r"(?:^|\n)\s*(?:Q(?:uestion)?\s*(\d+)[.:)]|\b(\d+)\s*[.)]\s)", re.I)
    matches = list(marker_re.finditer(text))
    if not matches:
        answers[questions[0]["q_id"]] = text.strip()
        return answers

    by_position = {q["position"]: q["q_id"] for q in questions}
    for i, match in enumerate(matches):
        number = int(match.group(1) or match.group(2))
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        q_id = by_position.get(number)
        if q_id and body:
            answers[q_id] = body
    return answers


def parse_questions(text: str) -> list[dict]:
    """Best-effort split of a question paper into ``{position, prompt, qtype}``.

    Splits on markers like ``Q1.`` / ``Question 2:`` / ``3)``. ``qtype`` defaults
    to ``open_ended`` (or ``mcq`` when lettered options are detected); ``max_marks``
    is left for faculty to set.
    """
    matches = list(_QUESTION_RE.finditer(text))
    if not matches:
        body = text.strip()
        return [{"position": 1, "prompt": body, "qtype": "open_ended"}] if body else []

    questions: list[dict] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            questions.append(
                {
                    "position": i + 1,
                    "prompt": body,
                    "qtype": "mcq" if _looks_like_mcq(body) else "open_ended",
                }
            )
    return questions
