# 09: Build Plan (phased checklist)

Work **one phase at a time**. Before each phase: post a plan. After: run tests, tick boxes, add a "Demo steps" note. Do not start the next phase until the current one passes its acceptance criteria.

---

## Phase 0: Scaffolding
- [ ] Monorepo layout from `CLAUDE.md`; `.env.example`; `.gitignore`; README stub
- [ ] `docker-compose.yml` with Postgres 16 + pgvector
- [ ] FastAPI app skeleton, config via Pydantic Settings, health endpoint
- [ ] SQLAlchemy + Alembic wired; first empty migration runs
- [ ] pytest setup with a test DB fixture; `ruff` + type checker configured
- [ ] Next.js app scaffolded with `/login`, `/student`, `/faculty` placeholders

**Accept:** `docker compose up -d db`, `alembic upgrade head`, `pytest -q`, both dev servers start.

## Phase 1: Auth, roles, courses, topics
- [ ] Models + migrations for users, courses, enrollments, topics (see `03-DATA-MODEL.md`)
- [ ] JWT login, password hashing, `/auth/me`
- [ ] RBAC dependencies; faculty owns courses; students see enrolled only
- [ ] Courses/topics/enrollment endpoints
- [ ] Seed script v0: 1 faculty, 15 students, 1 course with ~8 topics
- [ ] RBAC tests: student cannot call faculty routes; student A cannot read student B

**Accept:** all RBAC tests green; Swagger shows the routes.

## Phase 2: Assignments + Setup graph
- [ ] Models/migrations: assignments, questions, grading_packages, rubric_criteria
- [ ] Assignment/question CRUD; question-paper upload and parsing (PDF/text)
- [ ] `agents/common`: llm factory, Postgres checkpointer, runner, prompts loader
- [ ] Setup graph (`04-LANGGRAPH-AGENTS.md` §1) with `interrupt()` faculty review
- [ ] Package validation (marks sum, topics valid); lock + versioning; publish endpoint
- [ ] Tests with FakeLLM: draft → interrupt → resume (approve/edit) → locked package v1; edit creates v2

**Accept:** create assignment via API, graph pauses, decision resumes, package locked, students cannot see reference answers.

## Phase 3: Submissions + Evaluation graph (core)
- [x] Models/migrations: submissions, submission_answers, evaluations, criterion_scores
- [x] Submission upload, late detection, status machine, background job runner
- [x] Parsing (PDF/docx/text → per-question answers; fallback: single answer block mapped by question markers)
- [x] Evaluation graph: load → injection_check → route → deterministic MCQ grader → `score_criterion` fan-out (Send) → aggregate → topic scores → confidence gate → feedback draft → `interrupt()` faculty review → finalize
- [x] Self-consistency scoring + range validation + retry; `needs_manual` fallback
- [x] Review queue + evaluation detail + decision endpoints (resume graph)
- [x] Tests: routing, fan-out reducer, interrupt/resume, injection text doesn't change marks, invalid LLM output handled

**Accept:** upload a submission, evaluation reaches `pending_review`, faculty decision resumes and sets `graded`; marks always equal code-computed sums.

**Demo steps:** Upload a text, PDF, or DOCX answer as an enrolled student; confirm the response is accepted and the background evaluation appears in the faculty review queue; inspect criterion/topic scores and injection flags; approve or edit scores; release the result and fetch it as that student.

## Phase 4: Analytics
- [x] `app/analytics/` pure functions per `05-ANALYTICS.md` (topic score, mastery EMA, subject %, trend, flags, class metrics, item analysis, agreement metrics)
- [x] `topic_mastery_events` written at finalize; `topic_mastery` roll-up service
- [x] Analytics endpoints (heatmap, topics, distribution, questions, students, ai-quality, understanding gap)
- [x] Unit tests reproducing the worked examples in `10-TESTING-EVAL.md`

**Accept:** worked examples pass exactly; endpoints return data on seeded DB.

**Demo steps:** Approve an evaluation and verify its final criterion marks create topic mastery events; inspect the course heatmap, topic weakness, score distribution, question item analysis, student profiles, and AI quality; add answered follow-up checks in Phase 6 and verify understanding-gap trends.

## Phase 5: Feedback + Monitoring graphs
- [x] Feedback graph (`04` §4): personalized, cites student's own answers, practice suggestions, validation; release flow
- [x] Monitoring graph (`04` §6) with deterministic nodes; alert dedupe; scheduler (APScheduler) + manual trigger endpoint
- [x] Alerts endpoints + resolve
- [x] Tests: each monitoring node without an LLM; dedupe; feedback never leaks authenticity/reference data

**Accept:** seeded "missing submissions" and "weak topic" scenarios produce the expected alerts.

**Demo steps:** Approve and release an evaluation to generate guarded student feedback; run course monitoring manually or let the six-hour scheduler run; inspect missing, low-submission, overdue-review, at-risk, and weak-topic alerts; resolve an alert and rerun monitoring to confirm it is deduplicated.

## Phase 6: Co-learning memory + Authenticity module
- [ ] `correction_memory` writes at finalize; retrieval of top-k few-shots in `score_criterion` (pgvector)
- [ ] Authenticity branch (`06-AUTHENTICITY.md`): S2 baseline drift, S4 similarity, S5 alignment, S1 follow-up questions + interrupt + scoring; optional S3 process events; concern-level function
- [ ] Authenticity endpoints (faculty only) + follow-up endpoints (student)
- [ ] Tests: drift on synthetic authors, similarity clusters, table-driven concern levels, follow-up pass caps concern at medium, no authenticity data in student responses

**Accept:** demo shows a flagged submission with an evidence list; marks unchanged by it.

## Phase 7: Frontend
- [ ] Typed API client from OpenAPI; auth + role routing
- [ ] Student: courses, assignment/submit/status tracker, result, mastery, follow-ups
- [ ] Faculty: creation wizard, package review, completeness board, review queue + review screen, analytics (heatmap, topics, distribution, question quality), alerts, AI-quality, authenticity panel
- [ ] Polling states, empty/loading/error states, "low data" handling

**Accept:** end-to-end happy path through the UI for both roles on seeded data.

## Phase 8: Seed data, evaluation, polish
- [ ] `scripts/seed.py`: 1 course, ~10 topics, 3 assignments, 15-20 students with varied synthetic submissions (strong, average, weak, missing, late, near-duplicates, AI-style generic answers)
- [ ] Calibration script: run the AI on faculty-graded samples, output MAE, agreement, calibration table (`10-TESTING-EVAL.md`)
- [ ] README: architecture diagram, setup, demo walkthrough, known limitations (esp. authenticity)
- [ ] `docs/DECISIONS.md` finalized; cleanup, lint, type-check

**Accept:** a fresh clone → `docker compose up` + seed + demo script works in under 10 minutes.

---

## Stretch (only if time remains)
- Code-assignment grading in a sandbox (Docker, no network, CPU/time limits)
- Auto-approve policy once agreement ≥ threshold
- Email/Telegram notifications for alerts and results
- Plagiarism check against external sources
- Export analytics to CSV/PDF

## Demo storyline (keep updated)
1. Faculty creates a subject + topics → assignment → AI drafts package → faculty approves.
2. Students submit (one late, a few missing).
3. Evaluation runs; faculty reviews a low-confidence item, edits a score.
4. Student sees marks, topic breakdown, personalized feedback.
5. Heatmap shows a weak topic; alerts list missing students.
6. Authenticity panel shows a medium concern with evidence from a failed understanding check.
7. AI-quality page shows agreement improving after corrections.
