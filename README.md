# Human-AI Co-Learning Agent

A dual-role (Student / Faculty) educational platform where LangGraph agents evaluate
submissions, compute per-topic and per-subject comprehension percentages, raise alerts,
and give diagnostic feedback — with faculty approval in the loop.

> **Status:** Phases 0–7 implemented. See `docs/09-BUILD-PLAN.md` for the phased checklist.

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

The student and faculty portals use a Next.js server-side session cookie and proxy API
requests to FastAPI. Set `BACKEND_API_URL` in `frontend/.env.local` when the backend is
not at `http://localhost:8000/api/v1`. To refresh generated API types after changing
backend schemas, run `uv run python -m scripts.export_openapi` from `backend/`, then
`pnpm api:types` from `frontend/`.
