# Human-AI Co-Learning Agent

A dual-role (Student / Faculty) educational platform where LangGraph agents evaluate
submissions, compute per-topic and per-subject comprehension percentages, raise alerts,
and give diagnostic feedback — with faculty approval in the loop.

> **Status:** Phase 0 scaffolding. See `docs/09-BUILD-PLAN.md` for the phased checklist.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x + Alembic, Pydantic v2
- **Agents:** LangGraph (Python) + Postgres checkpointer, `langchain-anthropic` (Claude)
- **DB:** PostgreSQL 16 + `pgvector`
- **Jobs:** APScheduler (monitoring graph)
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind
- **Auth:** JWT, role-based access control (`student`, `faculty`)

## Layout

```
backend/     FastAPI app (app/api, app/core, app/db, app/models, app/schemas,
             app/services, app/analytics, app/agents, app/prompts)
frontend/    Next.js app (/student, /faculty route trees)
docs/        PRD, architecture, data model, agent specs, build plan
docker-compose.yml
.env.example
```

## Getting started

```bash
cp .env.example backend/.env     # optional; defaults already match docker-compose
docker compose up -d db          # Postgres + pgvector
cd backend && uv sync            # creates .venv and installs deps
cd backend && alembic upgrade head
cd backend && uv run uvicorn app.main:app --reload
cd frontend && pnpm install && pnpm dev
```

See `docs/09-BUILD-PLAN.md` for per-phase demo steps.
