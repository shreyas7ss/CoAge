# 05: Analytics: Exact Metric Definitions

Implement as **pure functions** in `backend/app/analytics/` (inputs: plain data structures / DataFrames; outputs: numbers/dicts). No LLM calls, no DB access inside the pure functions (a thin service layer queries the DB and calls them). All thresholds come from config with these defaults.

## 1. Notation

- `c` = rubric criterion, `m_c` = max marks, `a_c` = final awarded marks
- `w_{c,t}` = weight linking criterion `c` to topic `t` (default 1.0)
- Scores normalised to 0..1 unless stated

## 2. Per-submission topic score

```
topic_score(t, s) = Σ_c [ (a_c / m_c) * w_{c,t} ]  /  Σ_c w_{c,t}      over criteria c tagged with topic t in submission s
```
Return `None` if no criteria map to `t`. Uses **final** (faculty-approved) marks only.

## 3. Student topic mastery (recency-weighted)

Evidence arrives as `topic_mastery_events` (`score`, `evidence_weight`, time-ordered).

```
mastery_0   = score_0
mastery_n   = α * score_n + (1 - α) * mastery_{n-1}      # α = 0.4 default
confidence  = min(1.0, n_events / 5)
```
Store `mastery`, `confidence`, `n_events` in `topic_mastery`. Always recomputable from events.

**Subject understanding %** (per student, per course):
```
subject_pct = Σ_t (mastery_t * weight_t) / Σ_t weight_t         over topics t that have ≥ 1 event
```
Report `coverage = topics_with_evidence / total_topics` alongside, because 80% on 2 of 10 topics is not 80% understanding.

**Trend:** `mastery_now - mastery_k_events_ago` (k=3; if fewer events, `None`). Label ↑ if > +0.05, ↓ if < −0.05, else →.

## 4. Student-level flags

Defaults (config-driven):
- `WEAK_TOPIC_THRESHOLD = 0.50`, `WATCH_THRESHOLD = 0.60`
- **at_risk** if ANY: ≥ 2 topics with `mastery < 0.40` and confidence ≥ 0.4; ≥ 2 missed submissions; mastery trend ↓ across 3 consecutive assignments.
- **Submission reliability** = `on_time / (assignments_due)`; also count `late`, `missed`.

## 5. Class-level metrics (faculty dashboard)

- **Heatmap:** matrix topic × assignment (or topic × student) of average topic score; cells with `n < 3` shown as "low data".
- **% below threshold per topic:** `count(mastery_t < WEAK_TOPIC_THRESHOLD) / count(students with evidence on t)`; alert when ≥ 40%.
- **Score distribution:** histogram buckets (10%), mean, median, std dev, and a bimodality hint (e.g., mean ≈ midpoint with high std).
- **Completeness:** per assignment: submitted, late, missing, % submitted.
- **Top misconceptions:** counts of `matched_misconception` per topic/question, top 5.
- **Improvement:** class mean topic score by assignment (time series).

## 6. Question quality (classical item analysis)

For each question `q` across students who attempted it (need n ≥ 10 to report, else "insufficient data"):

```
difficulty(q)     = mean over students of (marks_q / max_q)             # 0..1; higher = easier
discrimination(q) = Pearson r between student's (marks_q / max_q) and their total normalised score on all OTHER questions
```
Interpretation labels (defaults, tunable): difficulty `<0.30` very hard, `0.30-0.85` acceptable, `>0.85` very easy. Discrimination `>0.30` good, `0.10-0.30` fair, `<0.10` poor, `<0` problem (investigate rubric or key).
Also report **distractor/misconception frequencies** for MCQs and misconception counts for written questions.

References: https://www.washington.edu/assessment/scanning-scoring/scoring/item-analysis/ and https://specialconnections.ku.edu/assessment/quality_test_construction/teacher_tools/item_analysis

## 7. AI-quality metrics (co-learning evidence)

Per criterion, per assignment type, per week:
- **agreement rate** = share of criterion scores with `final == ai` (or within 5% of max)
- **MAE** = mean |final − ai| / max_marks
- **override rate** = share where faculty changed the mark
- **confidence calibration**: bucket AI confidence (0-0.5, 0.5-0.7, 0.7-0.85, 0.85-1.0) and report agreement rate per bucket (high-confidence buckets should agree more)
- **review time** (if captured): median seconds between review open and decision
- **trend over time:** agreement vs. number of stored corrections (shows the memory helping)
Optionally add quadratic-weighted Cohen's kappa for rubric scores (verify the formula/source before citing in the report).

## 8. Understanding gap (links to authenticity)

```
understanding_gap(student, assignment) = normalised_submission_score − followup_check_score
```
Only computed when a follow-up check exists. Show faculty as a **trend over several assignments** (a single large gap is weak evidence). Never auto-penalise.

## 9. Alert rules (deterministic)

| Kind | Trigger |
|---|---|
| `due_soon_low_rate` | < 60% submitted and deadline within 24h |
| `missing` | enrolled student, deadline passed, no submission |
| `overdue_review` | evaluation `awaiting_review` for > 3 days |
| `weak_topic` | ≥ 40% of students below `WEAK_TOPIC_THRESHOLD` on a topic (n ≥ 8) |
| `at_risk` | rules in §4 |
Alerts are deduplicated: don't create a new open alert with the same `(kind, target)`.

## 10. API surface for analytics (see `07-API-SPEC.md`)

All endpoints compute from stored data; cache heavy aggregates (e.g., materialized view or Redis-free TTL cache) and invalidate when an evaluation is finalized.
