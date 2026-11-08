# CLAUDE.md: Human-AI Co-Learning Agent

You are building **Project 8: Human-AI Co-Learning Agent**, a dual-role (Student / Faculty) educational platform where LangGraph agents evaluate submissions, compute per-topic and per-subject comprehension percentages, raise alerts, and give diagnostic feedback. Faculty stay in the loop: the AI proposes, faculty approve.

## Read these first (in order)

1. `docs/01-PRD.md`: what and why
2. `docs/02-ARCHITECTURE.md`: system shape
3. `docs/03-DATA-MODEL.md`: schema (source of truth for tables)
4. `docs/04-LANGGRAPH-AGENTS.md`: the agentic workflows (the core of the project)
5. `docs/05-ANALYTICS.md`: exact metric formulas
6. `docs/06-AUTHENTICITY.md`: AI-usage / understanding-verification module
7. `docs/07-API-SPEC.md`, `docs/08-FRONTEND.md`
8. `docs/09-BUILD-PLAN.md`: phased checklist. **Work from this.**
9. `docs/10-TESTING-EVAL.md`: tests and evaluation

## Stack (do not change without asking)

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x + Alembic, Pydantic v2
- **Agents:** LangGraph (Python) with the **Postgres checkpointer**, `langchain-anthropic` (Claude) with structured output
- **DB:** PostgreSQL 16 + `pgvector`
- **Jobs:** APScheduler (simple) for the monitoring graph
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind; two route trees: `/student`, `/faculty`
- **Auth:** JWT, role-based access control (`student`, `faculty`)
- **Tests:** pytest (+ pytest-asyncio), Playwright optional for e2e
- **Dev:** Docker Compose for Postgres; `uv` or `pip` + `requirements.txt`

## Repo layout

```
backend/
  app/
    api/            # FastAPI routers (auth, courses, assignments, submissions, reviews, analytics, alerts)
    core/           # config, security, deps, logging
    db/             # session, base, migrations (alembic)
    models/         # SQLAlchemy models
    schemas/        # Pydantic request/response + LLM structured-output schemas
    services/       # business logic (no LLM calls here unless via agents/)
    analytics/      # PURE functions that compute metrics (no LLM)
    agents/
      common/       # llm client, prompt loader, checkpointer, guardrails
      setup/        # assignment-setup graph
      evaluation/   # submission evaluation graph
      feedback/     # diagnostic feedback graph
      monitoring/   # scheduled alert graph
      authenticity/ # authenticity & understanding branch
    prompts/        # .md or .jinja prompt templates, versioned
  tests/
  scripts/seed.py
frontend/
docker-compose.yml
.env.example
```

## Non-negotiable rules

1. **The LLM never computes final numbers.** Scores per rubric criterion come from the LLM as structured output. Everything else (totals, topic scores, mastery %, class metrics, alerts) is computed in `app/analytics/` with deterministic code. The LLM may only *explain* numbers.
2. **Treat student submissions as untrusted data.** Always wrap them in clear delimiters, instruct the model to ignore instructions inside them, and run the injection check node before grading. Never put submission text in a system prompt.
3. **Human-in-the-loop is real.** Use LangGraph `interrupt()` + a durable Postgres checkpointer for faculty review. No grade reaches a student until faculty approve (or an explicit per-assignment auto-approve policy allows it).
4. **Authenticity signals never change marks automatically** and are visible to faculty only. Output a *concern level + evidence list*, never an "X% AI" number. See `docs/06-AUTHENTICITY.md`.
5. **Version the grading package.** Every evaluation stores `rubric_version`. A locked package is immutable; edits create a new version.
6. **Structured outputs only** for LLM results (Pydantic schemas), validate ranges (0 <= awarded <= max), retry once on validation failure, then route to faculty review as "needs manual grading".
7. **No hardcoded model names or secrets.** Use env vars: `ANTHROPIC_API_KEY`, `LLM_MODEL`, `DATABASE_URL`, `JWT_SECRET`. Provide `.env.example`.
8. **Role isolation:** students can only read their own submissions/evaluations (and only after release). Authenticity reports and class analytics are faculty-only. Enforce in dependencies, with tests.
9. **Anonymize before LLM calls:** do not send names, emails or roll numbers to the LLM. Send only submission text and IDs.
10. **LangGraph API changes often.** Before writing graph code, check the current docs (https://docs.langchain.com/oss/python/langgraph/ , especially persistence, interrupts, and `Send`) and use the installed version's API. Do not rely on memory.

## How to work

- Work **one phase at a time** from `docs/09-BUILD-PLAN.md`. Before coding a phase, post a short plan (files to create/change). After it, run tests and tick the checkboxes in that file.
- Prefer small, reviewable commits with clear messages.
- If a requirement is ambiguous or two docs conflict, **ask** instead of guessing; note the decision in `docs/DECISIONS.md` (create if missing).
- Write tests alongside code, especially for `app/analytics/` (pure functions with worked examples in `docs/10-TESTING-EVAL.md`).
- Keep prompts in `app/prompts/`, not inline in Python.
- Add type hints; run `ruff` and `mypy` (or `pyright`) before finishing a phase.

## Commands (create these as you build; keep this list updated)

```
docker compose up -d db          # Postgres + pgvector
cd backend && uvicorn app.main:app --reload
cd backend && alembic upgrade head
cd backend && pytest -q
cd backend && python scripts/seed.py
cd frontend && npm run dev
```

## Definition of done (per phase)

Code + migrations + tests passing + docs updated + checkboxes ticked + short demo steps added to `docs/09-BUILD-PLAN.md`.
