"""Create an honest MAE/agreement report from approved evaluations.

Default mode compares persisted AI marks against the final marks saved by a reviewer.
Use ``--run-ai`` to re-score those same reviewed submissions with/without correction memory.
The latter makes real model calls, needs configured LLM credentials, and does not mutate grades.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.orm import Session

from app.agents.common import runner
from app.analytics.service import approved_evaluation_rows
from app.db.session import SessionLocal
from app.models.assignment import Assignment, RubricCriterion
from app.models.submission import CriterionScore, Evaluation, Submission
from app.services.evaluation_service import build_input_state

CONFIDENCE_BUCKETS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.01)]


def pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) < 2 or len(x) != len(y):
        return None
    mean_x, mean_y = statistics.mean(x), statistics.mean(y)
    dx, dy = [v - mean_x for v in x], [v - mean_y for v in y]
    denominator = math.sqrt(sum(v * v for v in dx) * sum(v * v for v in dy))
    return sum(a * b for a, b in zip(dx, dy, strict=True)) / denominator if denominator else None


def ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda pair: pair[1])
    output = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        average_rank = (start + 1 + end) / 2
        for index, _value in ordered[start:end]:
            output[index] = average_rank
        start = end
    return output


def metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [row for row in rows if row["max_marks"] > 0]
    if not usable:
        return {"n": 0, "submissions": 0}
    errors = [abs(r["ai_mark"] - r["faculty_mark"]) / r["max_marks"] for r in usable]
    exact = [abs(r["ai_mark"] - r["faculty_mark"]) <= 1e-9 for r in usable]
    within_10 = [abs(r["ai_mark"] - r["faculty_mark"]) <= 0.1 * r["max_marks"] for r in usable]
    by_submission: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in usable:
        by_submission[row["submission_id"]].append(row)
    totals = [
        (
            sum(r["ai_mark"] for r in group) / sum(r["max_marks"] for r in group),
            sum(r["faculty_mark"] for r in group) / sum(r["max_marks"] for r in group),
        )
        for group in by_submission.values()
    ]
    ai_totals, faculty_totals = [pair[0] for pair in totals], [pair[1] for pair in totals]
    return {
        "n": len(usable),
        "submissions": len(by_submission),
        "normalized_mae": statistics.mean(errors),
        "exact_agreement": statistics.mean(exact),
        "within_10pct": statistics.mean(within_10),
        "pearson_totals": pearson(ai_totals, faculty_totals),
        "spearman_totals": pearson(ranks(ai_totals), ranks(faculty_totals)),
    }


def score_rows_for_evaluation(db: Session, evaluation: Evaluation) -> list[dict[str, Any]]:
    rows = (
        db.query(CriterionScore, RubricCriterion)
        .outerjoin(RubricCriterion, RubricCriterion.id == CriterionScore.criterion_id)
        .filter(CriterionScore.evaluation_id == evaluation.id)
        .all()
    )
    return [
        {
            "submission_id": str(evaluation.submission_id),
            "evaluation_id": str(evaluation.id),
            "criterion_id": str(score.criterion_id or score.id),
            "criterion": criterion.description if criterion else "deterministic question score",
            "ai_mark": float(score.ai_awarded or 0),
            "faculty_mark": float(score.final_awarded or 0),
            "max_marks": float(score.max_marks or (criterion.marks if criterion else 0)),
            "confidence": float(score.confidence) if score.confidence is not None else None,
            "mode": "stored",
        }
        for score, criterion in rows
        if score.ai_awarded is not None and score.final_awarded is not None
    ]


def rerun_submission(
    db: Session,
    submission: Submission,
    assignment: Any,
    evaluation: Evaluation,
    *,
    include_memory: bool,
    run_id: str,
) -> list[dict[str, Any]]:
    state = build_input_state(db, submission, assignment)
    if not include_memory:
        for criteria in state["criteria_by_qid"].values():
            for criterion in criteria:
                criterion["few_shots"] = []
    state["authenticity"] = {"concern_level": "insufficient_evidence", "signals": [], "caveats": []}
    result = runner.start(
        "evaluation",
        f"calibration-{run_id}-{submission.id}",
        state,
    )
    if result["status"] != "interrupted":
        raise RuntimeError(f"Evaluation {evaluation.id} did not reach the review checkpoint")
    predicted = {
        str(row.get("criterion_id")): row for row in result["interrupt"][0]["criterion_scores"]
    }
    approved_scores = (
        db.query(CriterionScore, RubricCriterion)
        .outerjoin(RubricCriterion, RubricCriterion.id == CriterionScore.criterion_id)
        .filter(CriterionScore.evaluation_id == evaluation.id)
        .all()
    )
    output = []
    for score, criterion in approved_scores:
        if score.final_awarded is None:
            continue
        prediction = predicted.get(str(score.criterion_id))
        if prediction is None:
            continue
        output.append(
            {
                "submission_id": str(submission.id),
                "evaluation_id": str(evaluation.id),
                "criterion_id": str(score.criterion_id or score.id),
                "criterion": criterion.description if criterion else "criterion",
                "ai_mark": float(prediction.get("ai_awarded", 0)),
                "faculty_mark": float(score.final_awarded),
                "max_marks": float(score.max_marks or (criterion.marks if criterion else 0)),
                "confidence": float(prediction["confidence"])
                if prediction.get("confidence") is not None
                else None,
                "mode": "with_memory" if include_memory else "without_memory",
            }
        )
    return output


def calibration_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for low, high in CONFIDENCE_BUCKETS:
        group = [
            row
            for row in rows
            if row.get("confidence") is not None and low <= row["confidence"] < high
        ]
        output.append(
            {
                "range": f"{low:.0%}-{min(high, 1.0):.0%}",
                "n": len(group),
                "exact_agreement": (
                    statistics.mean(
                        abs(row["ai_mark"] - row["faculty_mark"]) <= 1e-9 for row in group
                    )
                    if group
                    else None
                ),
            }
        )
    return output


def markdown_report(
    rows: list[dict[str, Any]],
    *,
    label_source: str,
    ran_ai: bool,
    correction_memory: bool,
    course_label: str,
) -> str:
    summary = metric_summary(rows)
    report = [
        "# Grading calibration report",
        "",
        f"- Generated: {datetime.now(UTC).isoformat()}",
        f"- Scope: {course_label}",
        f"- Label provenance: {label_source}",
        f"- Fresh model run: {'yes' if ran_ai else 'no; compares stored evaluations'}",
        "- Correction memory: "
        + (
            "included"
            if correction_memory
            else "excluded for fresh run; stored mode may reflect its original prompt"
        ),
        f"- Faculty-marked criterion rows: {summary.get('n', 0)} "
        f"across {summary.get('submissions', 0)} submissions",
        "",
        "Seeded course data are synthetic and are not real faculty labels. "
        "Do not treat a report on seeded data as model validation.",
        "",
        "## Aggregate metrics",
        "",
        "| Metric | Result |",
        "|---|---:|",
    ]
    for label, key in [
        ("Normalized MAE", "normalized_mae"),
        ("Exact agreement", "exact_agreement"),
        ("Within 10% of criterion marks", "within_10pct"),
        ("Pearson correlation of normalized totals", "pearson_totals"),
        ("Spearman correlation of normalized totals", "spearman_totals"),
    ]:
        value = summary.get(key)
        formatted = "n/a" if value is None else f"{value:.4f}"
        report.append(f"| {label} | {formatted} |")

    report.extend(
        [
            "",
            "## Agreement by criterion",
            "",
            "| Criterion | n | Exact agreement | Normalized MAE |",
            "|---|---:|---:|---:|",
        ]
    )
    by_criterion: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_criterion[row["criterion"]].append(row)
    for criterion, group in sorted(by_criterion.items()):
        stats = metric_summary(group)
        report.append(
            f"| {criterion.replace('|', '/')} | {stats.get('n', 0)} | "
            f"{stats.get('exact_agreement', 0):.4f} | {stats.get('normalized_mae', 0):.4f} |"
        )

    report.extend(
        [
            "",
            "## Confidence calibration",
            "",
            "| Confidence | n | Exact agreement |",
            "|---|---:|---:|",
        ]
    )
    for bucket in calibration_table(rows):
        value = bucket["exact_agreement"]
        report.append(
            f"| {bucket['range']} | {bucket['n']} | {'n/a' if value is None else f'{value:.4f}'} |"
        )
    report.extend(
        [
            "",
            "## Limitations",
            "",
            "This is an observational comparison, not a controlled model study. Fresh re-scoring "
            "may vary with model version, prompt, and temperature. Synthetic seed labels are "
            "illustrative only. Report sample size and label provenance with any results shared "
            "outside this project.",
            "",
        ]
    )
    return "\n".join(report)


def collect(db: Session, args: argparse.Namespace) -> tuple[list[dict[str, Any]], str]:
    evaluations = []
    courses = db.query(Assignment.course_id).distinct().all()
    course_ids = [row[0] for row in courses]
    for course_id in course_ids:
        evaluations.extend(approved_evaluation_rows(db, course_id, args.assignment_id))
    if args.course_id:
        evaluations = [row for row in evaluations if row[2].course_id == args.course_id]
    eligible = []
    for evaluation, submission, assignment in evaluations:
        if args.run_ai and evaluation.package_version != assignment.active_package_version:
            continue
        scores = score_rows_for_evaluation(db, evaluation)
        if any(row["faculty_mark"] is not None and row["max_marks"] > 0 for row in scores):
            eligible.append((evaluation, submission, assignment, scores))
    eligible = eligible[: args.limit]
    if not eligible:
        raise RuntimeError("No approved evaluations with paired AI/final marks were found.")

    course_names = sorted({assignment.title for _e, _s, assignment, _rows in eligible})
    course_label = ", ".join(course_names)
    if not args.run_ai:
        return [
            row for _evaluation, _submission, _assignment, scores in eligible for row in scores
        ], course_label

    runner.configure_runtime(checkpointer=InMemorySaver())
    results: list[dict[str, Any]] = []
    for evaluation, submission, _assignment, _scores in eligible:
        if args.correction_memory in {"both", "off"}:
            results.extend(
                rerun_submission(
                    db,
                    submission,
                    _assignment,
                    evaluation,
                    include_memory=False,
                    run_id="without-memory",
                )
            )
        if args.correction_memory in {"both", "on"}:
            results.extend(
                rerun_submission(
                    db,
                    submission,
                    _assignment,
                    evaluation,
                    include_memory=True,
                    run_id="with-memory",
                )
            )
    return results, course_label


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-id", type=uuid.UUID, help="Limit to a course UUID")
    parser.add_argument("--assignment-id", type=uuid.UUID, help="Limit to an assignment UUID")
    parser.add_argument(
        "--limit", type=int, default=24, help="Maximum reviewed submissions (default: 24)"
    )
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    parser.add_argument(
        "--run-ai", action="store_true", help="Re-score samples using the configured LLM"
    )
    parser.add_argument(
        "--correction-memory",
        choices=("off", "on", "both"),
        default="both",
        help="Use correction memories for fresh model runs (default: both paired runs)",
    )
    parser.add_argument(
        "--label-source",
        default="unknown; set explicitly (for example, faculty-reviewed or synthetic-seed)",
        help="Document how final marks were produced; seeded grades are synthetic.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SessionLocal() as db:
        rows, course_label = collect(db, args)
    if args.run_ai:
        selected_modes = {row["mode"] for row in rows}
        modes = sorted(selected_modes)
        outputs = []
        for mode in modes:
            subset = [row for row in rows if row["mode"] == mode]
            suffix = f"-{mode}" if len(modes) > 1 else ""
            outputs.append((suffix, subset, mode == "with_memory"))
    else:
        outputs = [("-stored", rows, False)]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for suffix, subset, memory_used in outputs:
        report = markdown_report(
            subset,
            label_source=args.label_source,
            ran_ai=args.run_ai,
            correction_memory=memory_used,
            course_label=course_label,
        )
        md_path = args.output_dir / f"calibration-{stamp}{suffix}.md"
        csv_path = args.output_dir / f"calibration-{stamp}{suffix}.csv"
        md_path.write_text(report, encoding="utf-8")
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            fields = [
                "submission_id",
                "evaluation_id",
                "criterion_id",
                "criterion",
                "ai_mark",
                "faculty_mark",
                "max_marks",
                "confidence",
                "mode",
            ]
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(subset)
        print(f"Wrote {md_path} and {csv_path}")


if __name__ == "__main__":
    main()
