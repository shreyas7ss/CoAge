# Decisions Log

Record every deviation from the docs or non-obvious choice here (date, decision, reason).
This file doubles as raw material for the project report.

| Date | Decision | Reason |
|---|---|---|
| 2026-11-08 | Copied `Instructions/` into canonical layout: `CLAUDE.md` at root, numbered docs under `docs/` | All internal references (`docs/09-BUILD-PLAN.md`, etc.) and `CLAUDE.md` must resolve for the workflow to be self-consistent |
| 2026-11-08 | Backend deps managed with `uv` + `pyproject.toml` (no `requirements.txt`) | `uv` is available and faster; docs allow "uv or pip" |
| 2026-11-08 | Application uses **synchronous** SQLAlchemy 2.x (`psycopg` v3) | Simpler Alembic + test setup; LangGraph's Postgres checkpointer will use its own async connection in later phases |
| 2026-11-08 | Test DB fixture uses in-memory SQLite (not Postgres) for the default `pytest` run | Keeps `pytest -q` green with no Docker and no API key; Postgres integration tests will opt in later |
| 2026-11-08 | Next.js 15.5.29 + React 18.3 + Tailwind 3.4 | Kept React 18 compatibility while moving from the unsupported Next.js 14 line to the patched 15.5 maintenance release |
| 2026-11-08 | Runtime `.env` lives at `backend/.env` (template remains at root `.env.example`) | Backend reads `.env` from its working directory; root template copied down |
| 2026-11-08 | Docker Desktop daemon not started in build sandbox; DB steps deferred to user's machine | `docker info` reports daemon pipe missing; compose file + offline migration verified instead |
| 2026-11-08 | Enums stored as VARCHAR (`native_enum=False`) instead of Postgres native `ENUM` types | Portable across SQLite (tests) and Postgres; avoids `ALTER TYPE` friction when the enum evolves |
| 2026-11-08 | Verified LangGraph **1.2.20** API before writing graph code (rule #10): `interrupt`/`Command` from `langgraph.types`; `InMemorySaver` from `langgraph.checkpoint.memory`; `PostgresSaver.from_conn_string` is a context manager with sync `.setup()` | Docs show older snippets; installed API differs (no top-level `AsyncPostgresSaver`) |
| 2026-11-08 | JSON columns (`grading_packages.content`, `questions.mcq_*`) use SQLAlchemy `JSON` (Postgres `JSON`) rather than `JSONB` | Keeps models portable to SQLite tests; no JSONB-specific querying is needed |
| 2026-11-08 | Setup graph adapted: `parse_questions`/`classify_question_types` handled in the service/upload layer (question type is required at creation); topic tagging folded into the AI draft | The spec lists them as graph nodes but they duplicate CRUD/upload work already done in the API |
| 2026-11-08 | Added `POST /assignments/{id}/package/start` (faculty) to trigger drafting | Spec's `decision` endpoint only *resumes*; a start trigger is needed for the first review |
| 2026-11-08 | Draft package stored as `grading_packages.version = 0` (mutable); approved versions start at 1 and are immutable | Matches "never mutate an approved package; create N+1" while keeping one editable draft row |
| 2026-11-08 | Seed data is deterministic synthetic demo content for 20 students, three assignments, and ten topics; seeded AI/final marks and feedback are explicitly labeled synthetic | Provides repeatable UI and analytics scenarios without representing generated data as real student work or faculty labels |
| 2026-11-08 | Seeded correction memories are derived from synthetic AI/final mark differences and faculty-note examples | Makes the co-learning memory UI and optional calibration comparison demonstrable; these corrections are not real faculty feedback |
| 2026-11-08 | Calibration reads paired AI/final marks from approved evaluations by default; `--run-ai` optionally re-scores reviewed submissions with an in-memory graph checkpointer | Lets the report run without an API key while keeping fresh model calls opt-in and preventing calibration runs from changing grades |
| 2026-11-08 | Calibration reports require an explicit provenance label for any claim that marks are faculty-reviewed; the default provenance is unknown | Seeded final marks are synthetic and must not be reported as faculty calibration |
| 2026-11-08 | Authenticity similarity uses deterministic 256-dimensional lexical hashing plus a phrase-overlap gate; no AI-authorship percentage is exposed | Local embeddings avoid an external embedding service and the signal is limited to review evidence, not a misconduct finding |
| 2026-11-08 | Process logging emits a student-opted-in aggregate session summary after submission rather than a 30-second streaming cadence | The process-events endpoint requires a persisted submission ID; only counts and timing fields are sent, never answer text |
| 2026-11-08 | The assignment creation screen is a compact single-question form, while the API accepts bulk question editing | Keeps the first UI workflow small; multi-question editing remains available through the typed API |
| 2026-11-08 | Completeness views use enrollment plus submission records to return per-student state; reminder delivery remains a UI/API follow-up | The current product has no notification transport configured |

