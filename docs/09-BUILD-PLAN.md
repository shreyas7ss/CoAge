# 09: Build Plan (phased checklist)

Work **one phase at a time**. Before each phase: post a plan. After: run tests, tick boxes, add a "Demo steps" note. Do not start the next phase until the current one passes its acceptance criteria.

---

## Phase 0: Scaffolding
- [x] Monorepo layout from `CLAUDE.md`; `.env.example`; `.gitignore`; README stub
- [x] `docker-compose.yml` with Postgres 16 + pgvector
- [x] FastAPI app skeleton, config via Pydantic Settings, health endpoint
- [x] SQLAlchemy + Alembic wired; first empty migration runs
- [x] pytest setup with a test DB fixture; `ruff` + type checker configured
- [x] Next.js app scaffolded with `/login`, `/student`, `/faculty` placeholders

**Accept:** `docker compose up -d db`, `alembic upgrade head`, `pytest -q`, both dev servers start.

**Demo steps:** `pytest -q` → 3 passed; `ruff check app tests` + `mypy app` clean; `alembic upgrade head --sql` emits valid Postgres DDL; `uvicorn app.main:app` serves `GET /api/v1/health` → `{"status":"ok"}`; frontend `tsc --noEmit` clean. (Docker Desktop daemon was not running in the build sandbox, so `docker compose up -d db` and live `alembic upgrade head` are manual steps — verified offline instead.)

## Phase 1: Auth, roles, courses, topics
- [x] Models + migrations for users, courses, enrollments, topics (see `03-DATA-MODEL.md`)
- [x] JWT login, password hashing, `/auth/me`
- [x] RBAC dependencies; faculty owns courses; students see enrolled only
- [x] Courses/topics/enrollment endpoints
- [x] Seed script v0: 1 faculty, 15 students, 1 course with ~8 topics
- [x] RBAC tests: student cannot call faculty routes; student A cannot read student B

**Accept:** all RBAC tests green; Swagger shows the routes.

**Demo steps:** `pytest -q` → 21 passed (auth, RBAC matrix, seed idempotency, OpenAPI route check); `ruff` + `mypy` clean. Login as `faculty@example.com` / `faculty-pass` after `python scripts/seed.py`.

## Phase 2: Assignments + Setup graph
- [x] Models/migrations: assignments, questions, grading_packages, rubric_criteria
- [x] Assignment/question CRUD; question-paper upload and parsing (PDF/text)
- [x] `agents/common`: llm factory, Postgres checkpointer, runner, prompts loader
- [x] Setup graph (`04-LANGGRAPH-AGENTS.md` §1) with `interrupt()` faculty review
- [x] Package validation (marks sum, topics valid); lock + versioning; publish endpoint
- [x] Tests with FakeLLM: draft → interrupt → resume (approve/edit) → locked package v1; edit creates v2

**Accept:** create assignment via API, graph pauses, decision resumes, package locked, students cannot see reference answers.

**Demo steps:** `pytest -q` → 35 passed (setup-graph interrupt/resume/reject-loop/validation + service lock/versioning + assignments RBAC/CRUD + end-to-end package flow with FakeLLM); `ruff` + `mypy` clean; `alembic upgrade head --sql` emits 9 tables. Verified against installed LangGraph 1.2.20 (`interrupt`/`Command` from `langgraph.types`, `InMemorySaver`, `PostgresSaver` context manager).

## Phase 3: Submissions + Evaluation graph (core)
- [ ] Models/migrations: submissions, submission_answers, evaluations, criterion_scores
- [ ] Submission upload, late detection, status machine, background job runner
- [ ] Parsing (PDF/docx/text → per-question answers; fallback: single answer block mapped by question markers)
- [ ] Evaluation graph: load → injection_check → route → deterministic MCQ grader → `score_criterion` fan-out (Send) → aggregate → topic scores → confidence gate → feedback draft → `interrupt()` faculty review → finalize
- [ ] Self-consistency scoring + range validation + retry; `needs_manual` fallback
- [ ] Review queue + evaluation detail + decision endpoints (resume graph)
- [ ] Tests: routing, fan-out reducer, interrupt/resume, injection text doesn't change marks, invalid LLM output handled

**Accept:** upload a submission, evaluation reaches `pending_review`, faculty decision resumes and sets `graded`; marks always equal code-computed sums.

## Phase 4: Analytics
- [ ] `app/analytics/` pure functions per `05-ANALYTICS.md` (topic score, mastery EMA, subject %, trend, flags, class metrics, item analysis, agreement metrics)
- [ ] `topic_mastery_events` written at finalize; `topic_mastery` roll-up service
- [ ] Analytics endpoints (heatmap, topics, distribution, questions, students, ai-quality)
- [ ] Unit tests reproducing the worked examples in `10-TESTING-EVAL.md`

**Accept:** worked examples pass exactly; endpoints return data on seeded DB.

## Phase 5: Feedback + Monitoring graphs
- [ ] Feedback graph (`04` §4): personalized, cites student's own answers, practice suggestions, validation; release flow
- [ ] Monitoring graph (`04` §6) with deterministic nodes; alert dedupe; scheduler (APScheduler) + manual trigger endpoint
- [ ] Alerts endpoints + resolve
- [ ] Tests: each monitoring node without an LLM; dedupe; feedback never leaks authenticity/reference data

**Accept:** seeded "missing submissions" and "weak topic" scenarios produce the expected alerts.

## Phase 6: Co-learning memory + Authenticity module
- [x] `correction_memory` writes at finalize; retrieval of top-k few-shots in `score_criterion` (pgvector)
- [x] Authenticity signals: S2 baseline drift, S4 similarity, S5 alignment, S1 follow-up questions + interrupt + scoring; optional S3 process events; concern-level function
- [x] Authenticity endpoints (faculty only) + follow-up endpoints (student)
- [x] Tests: drift on synthetic authors, similarity clusters, table-driven concern levels, follow-up pass caps concern at medium, no authenticity data in student responses

**Accept:** demo shows a flagged submission with an evidence list; marks unchanged by it.

## Phase 7: Frontend
- [x] Typed API client generated from OpenAPI; httpOnly cookie auth + role routing
- [x] Student: courses, assignment/submit/status tracker, result, mastery, timed follow-ups
- [x] Faculty: assignment creation and package review, completeness board, review queue + review screen, analytics (heatmap, topics, distribution, question quality), alerts, AI-quality, authenticity panel
- [x] Polling states, empty/loading/error states, "low data" handling

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
