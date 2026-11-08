"""Deterministic MCQ grading + self-consistency LLM scoring (no LLM totals)."""

import statistics

from app.agents.common.guardrails import validate_range
from app.core.config import settings


def _normalize_mcq_answer(answer: str, options: list) -> int | None:
    text = (answer or "").strip()
    if not text:
        return None
    if len(text) == 1 and text.isalpha():
        return ord(text.upper()) - ord("A")
    if text.isdigit():
        return int(text)
    for i, option in enumerate(options):
        if text.lower() == str(option).lower():
            return i
    return None


def grade_mcq(
    answer: str, mcq_correct: list | None, mcq_options: list | None, max_marks: float
) -> dict:
    """Deterministic MCQ grading (zero LLM calls)."""
    correct = list(mcq_correct or [])
    options = list(mcq_options or [])
    index = _normalize_mcq_answer(answer, options)
    correct_pick = index is not None and index in correct
    return {
        "ai_awarded": float(max_marks) if correct_pick else 0.0,
        "evidence": "Selected the correct option"
        if correct_pick
        else "Selected an incorrect option",
        "matched_misconception": None,
        "confidence": 1.0,
        "needs_manual": False,
    }


def score_with_self_consistency(structured, prompt: str, max_marks: float) -> dict:
    """Run self-consistency scoring, median aggregation, and range validation.

    Runs ``SELF_CONSISTENCY_RUNS`` times, takes the median ``awarded``, computes
    ``confidence = mean(self_reported) * (1 - normalized_disagreement)``, and
    validates the range ``[0, max_marks]`` (retrying once before ``needs_manual``).
    """
    results = []
    try:
        for _ in range(max(1, settings.self_consistency_runs)):
            results.append(structured.invoke(prompt))
    except Exception as exc:
        try:
            results = [
                structured.invoke(
                    f"{prompt}\nValidation error: {exc}. Return valid structured output."
                )
            ]
        except Exception:
            return _needs_manual()

    awarded_values = [float(r.awarded) for r in results]
    awarded = statistics.median(awarded_values)
    disagreement = (
        (max(awarded_values) - min(awarded_values)) / max_marks
        if len(awarded_values) >= 2 and max_marks > 0
        else 0.0
    )
    confidence = statistics.mean([float(r.confidence) for r in results]) * (1 - disagreement)
    best = min(results, key=lambda r: abs(float(r.awarded) - awarded))

    if not validate_range(awarded, 0.0, max_marks):
        retry = structured.invoke(
            prompt + "\n[validation error: awarded must be within [0, max_marks]]"
        )
        awarded = float(retry.awarded)
        confidence = float(retry.confidence)
        best = retry
        if not validate_range(awarded, 0.0, max_marks):
            return _needs_manual()

    return {
        "ai_awarded": awarded,
        "evidence": best.evidence,
        "matched_misconception": best.matched_misconception,
        "confidence": round(confidence, 4),
        "needs_manual": False,
    }


def _needs_manual() -> dict:
    return {
        "ai_awarded": 0.0,
        "evidence": "",
        "matched_misconception": None,
        "confidence": 0.0,
        "needs_manual": True,
    }
