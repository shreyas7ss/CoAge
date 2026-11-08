# Decisions Log

Record every deviation from the docs or non-obvious choice here (date, decision, reason).
This file doubles as raw material for the project report.

| Date | Decision | Reason |
|---|---|---|
| 2026-11-08 | Copied `Instructions/` into canonical layout: `CLAUDE.md` at root, numbered docs under `docs/` | All internal references (`docs/09-BUILD-PLAN.md`, etc.) and `CLAUDE.md` must resolve for the workflow to be self-consistent |
| 2026-11-08 | Backend deps managed with `uv` + `pyproject.toml` (no `requirements.txt`) | `uv` is available and faster; docs allow "uv or pip" |
| 2026-11-08 | Application uses **synchronous** SQLAlchemy 2.x (`psycopg` v3) | Simpler Alembic + test setup; LangGraph's Postgres checkpointer will use its own async connection in later phases |
| 2026-11-08 | Test DB fixture uses in-memory SQLite (not Postgres) for the default `pytest` run | Keeps `pytest -q` green with no Docker and no API key; Postgres integration tests will opt in later |
| 2026-11-08 | Pinned Next.js 14.2 + React 18 + Tailwind 3.4 | Stable, well-understood versions for App Router; upgradeable later |
| 2026-11-08 | Runtime `.env` lives at `backend/.env` (template remains at root `.env.example`) | Backend reads `.env` from its working directory; root template copied down |
| 2026-11-08 | Docker Desktop daemon not started in build sandbox; DB steps deferred to user's machine | `docker info` reports daemon pipe missing; compose file + offline migration verified instead |
| 2026-11-08 | Enums stored as VARCHAR (`native_enum=False`) instead of Postgres native `ENUM` types | Portable across SQLite (tests) and Postgres; avoids `ALTER TYPE` friction when the enum evolves |
| 2026-11-08 | Verified LangGraph **1.2.20** API before writing graph code (rule #10): `interrupt`/`Command` from `langgraph.types`; `InMemorySaver` from `langgraph.checkpoint.memory`; `PostgresSaver.from_conn_string` is a context manager with sync `.setup()` | Docs show older snippets; installed API differs (no top-level `AsyncPostgresSaver`) |
| 2026-11-08 | JSON columns (`grading_packages.content`, `questions.mcq_*`) use SQLAlchemy `JSON` (Postgres `JSON`) rather than `JSONB` | Keeps models portable to SQLite tests; no JSONB-specific querying is needed |
| 2026-11-08 | Setup graph adapted: `parse_questions`/`classify_question_types` handled in the service/upload layer (question type is required at creation); topic tagging folded into the AI draft | The spec lists them as graph nodes but they duplicate CRUD/upload work already done in the API |
| 2026-11-08 | Added `POST /assignments/{id}/package/start` (faculty) to trigger drafting | Spec's `decision` endpoint only *resumes*; a start trigger is needed for the first review |
| 2026-11-08 | Draft package stored as `grading_packages.version = 0` (mutable); approved versions start at 1 and are immutable | Matches "never mutate an approved package; create N+1" while keeping one editable draft row |

