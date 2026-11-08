"""Pure analytics functions. Inputs are plain values; no database or LLM access."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any


def topic_score(criteria: Iterable[dict[str, Any]], topic_id: str) -> float | None:
    """Weighted score ratio from faculty-final criterion marks for one topic."""
    tagged = [c for c in criteria if str(c.get("topic_id")) == str(topic_id)]
    total_weight = 0.0
    weighted_score = 0.0
    for criterion in tagged:
        maximum = float(criterion.get("max_marks") or 0)
        weight = float(criterion.get("topic_weight") or 1.0)
        final = criterion.get("final_awarded")
        if maximum <= 0 or final is None or weight <= 0:
            continue
        total_weight += weight
        weighted_score += (float(final) / maximum) * weight
    return weighted_score / total_weight if total_weight else None


def mastery_ema(scores: Sequence[float], alpha: float = 0.4) -> dict[str, float | int]:
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    if not scores:
        return {"mastery": 0.0, "confidence": 0.0, "n_events": 0}
    mastery = float(scores[0])
    for score in scores[1:]:
        mastery = alpha * float(score) + (1 - alpha) * mastery
    return {
        "mastery": mastery,
        "confidence": min(1.0, len(scores) / 5),
        "n_events": len(scores),
    }


def subject_understanding(topics: Sequence[dict[str, Any]]) -> dict[str, float | None]:
    total_weight = sum(float(t.get("weight", 1.0)) for t in topics if t.get("mastery") is not None)
    if total_weight <= 0:
        return {"subject_pct": None, "coverage": 0.0}
    weighted = sum(
        float(t["mastery"]) * float(t.get("weight", 1.0))
        for t in topics
        if t.get("mastery") is not None
    )
    return {
        "subject_pct": weighted / total_weight,
        "coverage": sum(t.get("mastery") is not None for t in topics) / len(topics)
        if topics
        else 0.0,
    }


def mastery_trend(
    history: Sequence[float], k: int = 3, threshold: float = 0.05
) -> dict[str, float | str | None]:
    if len(history) < k + 1:
        return {"change": None, "label": "insufficient_data"}
    change = float(history[-1]) - float(history[-k - 1])
    label = "up" if change > threshold else "down" if change < -threshold else "flat"
    return {"change": change, "label": label}


def student_flags(
    mastery_rows: Sequence[dict[str, Any]],
    missed: int,
    trend: dict[str, Any],
    weak_threshold: float = 0.5,
) -> dict[str, Any]:
    weak = [
        row
        for row in mastery_rows
        if float(row.get("mastery", 1)) < 0.4 and float(row.get("confidence", 0)) >= 0.4
    ]
    at_risk = len(weak) >= 2 or missed >= 2 or trend.get("label") == "down"
    return {
        "at_risk": at_risk,
        "weak_topic_ids": [
            str(row["topic_id"])
            for row in mastery_rows
            if float(row.get("mastery", 1)) < weak_threshold
        ],
        "missed_submissions": missed,
        "trend": trend.get("label"),
    }


def submission_reliability(
    on_time: int, late: int, missed: int, assignments_due: int
) -> dict[str, float | int]:
    return {
        "on_time": on_time,
        "late": late,
        "missed": missed,
        "assignments_due": assignments_due,
        "reliability": on_time / assignments_due if assignments_due else 0.0,
    }


def heatmap_cell(scores: Sequence[float], minimum_n: int = 3) -> dict[str, Any]:
    return {
        "score": statistics.mean(scores) if scores else None,
        "n": len(scores),
        "low_data": len(scores) < minimum_n,
    }


def below_threshold(values: Sequence[float], threshold: float = 0.5) -> dict[str, Any]:
    count = sum(value < threshold for value in values)
    n = len(values)
    return {"below": count, "n": n, "fraction": count / n if n else None}


def score_distribution(scores: Sequence[float]) -> dict[str, Any]:
    buckets = [0] * 10
    for score in scores:
        index = min(9, max(0, int(float(score) * 10)))
        buckets[index] += 1
    mean = statistics.mean(scores) if scores else None
    stddev = statistics.pstdev(scores) if len(scores) > 1 else 0.0 if scores else None
    return {
        "n": len(scores),
        "buckets": [
            {"from": i / 10, "to": (i + 1) / 10, "count": count} for i, count in enumerate(buckets)
        ],
        "mean": mean,
        "median": statistics.median(scores) if scores else None,
        "stddev": stddev,
        "bimodality_hint": bool(
            mean is not None and abs(mean - 0.5) <= 0.15 and stddev is not None and stddev >= 0.25
        ),
    }


def completeness(submitted: int, late: int, missing: int) -> dict[str, int | float]:
    due = submitted + missing
    return {
        "submitted": submitted,
        "late": late,
        "missing": missing,
        "assignments_due": due,
        "submission_rate": submitted / due if due else 0.0,
    }


def apply_late_penalty(total: float, penalty_pct: float) -> float:
    if not 0 <= penalty_pct <= 100:
        raise ValueError("penalty_pct must be within [0, 100]")
    return round(total * (1 - penalty_pct / 100), 2)


def difficulty_index(ratios: Sequence[float]) -> float | None:
    return statistics.mean(ratios) if ratios else None


def pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) != len(y) or len(x) < 2:
        return None
    mean_x, mean_y = statistics.mean(x), statistics.mean(y)
    dx, dy = [v - mean_x for v in x], [v - mean_y for v in y]
    denominator = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    return sum(a * b for a, b in zip(dx, dy, strict=True)) / denominator if denominator else None


def item_analysis(rows: Sequence[dict[str, Any]], minimum_n: int = 10) -> dict[str, Any]:
    """Rows contain normalized question score and normalized other-question total."""
    n = len(rows)
    if n < minimum_n:
        return {"n": n, "status": "insufficient_data", "difficulty": None, "discrimination": None}
    ratios = [float(row["ratio"]) for row in rows]
    other = [float(row["other_total"]) for row in rows]
    difficulty = difficulty_index(ratios)
    assert difficulty is not None
    discrimination = pearson(ratios, other)
    diff_label = (
        "very_hard" if difficulty < 0.30 else "very_easy" if difficulty > 0.85 else "acceptable"
    )
    disc_label = (
        "problem"
        if discrimination is not None and discrimination < 0
        else "good"
        if discrimination is not None and discrimination > 0.30
        else "fair"
        if discrimination is not None and discrimination >= 0.10
        else "poor"
    )
    return {
        "n": n,
        "status": "ok",
        "difficulty": difficulty,
        "difficulty_label": diff_label,
        "discrimination": discrimination,
        "discrimination_label": disc_label,
    }


def misconception_counts(
    values: Iterable[tuple[str | None, str | None]], limit: int = 5
) -> list[dict[str, Any]]:
    counts = Counter((topic, misconception) for topic, misconception in values if misconception)
    return [
        {"topic_id": key[0], "misconception": key[1], "count": count}
        for key, count in counts.most_common(limit)
    ]


def agreement_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    usable = [
        r
        for r in rows
        if r.get("ai_awarded") is not None
        and r.get("final_awarded") is not None
        and float(r.get("max_marks") or 0) > 0
    ]
    n = len(usable)
    if not n:
        return {
            "n": 0,
            "agreement_rate": None,
            "within_5pct_rate": None,
            "mae": None,
            "override_rate": None,
            "calibration": [],
        }
    exact = [float(r["ai_awarded"]) == float(r["final_awarded"]) for r in usable]
    within = [
        abs(float(r["ai_awarded"]) - float(r["final_awarded"])) <= 0.05 * float(r["max_marks"])
        for r in usable
    ]
    mae = statistics.mean(
        abs(float(r["ai_awarded"]) - float(r["final_awarded"])) / float(r["max_marks"])
        for r in usable
    )
    buckets = [(0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.000001)]
    calibration = []
    for low, high in buckets:
        group = [
            r
            for r in usable
            if r.get("confidence") is not None and low <= float(r["confidence"]) < high
        ]
        calibration.append(
            {
                "from": low,
                "to": min(high, 1.0),
                "n": len(group),
                "agreement_rate": (
                    sum(float(r["ai_awarded"]) == float(r["final_awarded"]) for r in group)
                    / len(group)
                )
                if group
                else None,
            }
        )
    return {
        "n": n,
        "agreement_rate": sum(exact) / n,
        "within_5pct_rate": sum(within) / n,
        "mae": mae,
        "override_rate": 1 - sum(exact) / n,
        "calibration": calibration,
    }


def understanding_gap(submission_score: float, followup_score: float) -> float:
    return submission_score - followup_score
