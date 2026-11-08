# 02: Architecture

## 1. System overview

```
┌────────────────┐      ┌────────────────┐
│  Student UI    │      │  Faculty UI    │      Next.js (/student, /faculty)
└───────┬────────┘      └───────┬────────┘
        └───────────┬───────────┘
              REST (JWT, RBAC)
                    │
            ┌───────▼────────┐
            │    FastAPI     │  routers → services → db
            └───┬────────┬───┘
                │        │
     ┌──────────▼──┐  ┌──▼──────────────────┐
     │ PostgreSQL  │  │ Agent runtime        │
     │ + pgvector  │  │ (LangGraph graphs)   │
     │ + LangGraph │◄─┤ Postgres checkpointer│
     │ checkpoints │  └──┬───────────────────┘
     └─────────────┘     │
                         ├─ Setup graph        (assignment grading package)
                         ├─ Evaluation graph   (+ authenticity branch)
                         ├─ Feedback graph     (post-release diagnostics)
                         └─ Monitoring graph   (scheduled alerts)
                                   │
                              Claude API (structured output)

   APScheduler ──► triggers Monitoring graph, deadline scans, mastery roll-ups
   File storage ─► local ./storage (dev) / S3-compatible (prod)
```

## 2. Key design principles

1. **Portal vs. agent separation.** Portal code (CRUD, auth, dashboards) is ordinary FastAPI. Agents live in `app/agents/` and are invoked by services through a thin `run_graph()` / `resume_graph()` interface.
2. **Deterministic where possible.** Routing by question type, MCQ grading, test-case grading, deadline scans, and all metrics are plain code/SQL. The LLM is used only for: drafting grading packages, scoring rubric criteria on text, drafting feedback, generating follow-up questions, writing alert digests.
3. **Long-running + human-in-the-loop via checkpoints.** Faculty may review hours or days later. Each evaluation runs as a LangGraph **thread** (`thread_id = f"eval-{submission_id}"`); `interrupt()` pauses; the API resumes with `Command(resume=...)`.
4. **Everything is auditable.** Store per-criterion evidence, confidence, prompt/model versions, rubric version, faculty edits, and AI-vs-final deltas.
5. **Events → roll-ups.** Store `topic_mastery_events`; derive `topic_mastery` so formulas can change and be recomputed.

## 3. Async execution model

- `POST /submissions` stores the file and row, sets status `submitted`, enqueues an evaluation job (FastAPI `BackgroundTasks` or a simple worker loop reading an `agent_jobs` table).
- The worker runs the evaluation graph until it finishes or hits an interrupt, then updates `submissions.status` (`under_evaluation` → `pending_review`).
- Faculty action `POST /reviews/{evaluation_id}/decision` resumes the graph; on completion status becomes `graded` and mastery events are written.
- UI polls status endpoints (no websockets required for v1).

## 4. Graph ↔ API contract

| Event | Graph | thread_id | Interrupt? |
|---|---|---|---|
| Faculty creates assignment | setup | `setup-{assignment_id}` | Yes: package approval |
| Student submits | evaluation | `eval-{submission_id}` | Yes: faculty review; optional student follow-up |
| Faculty releases grade | feedback | `fb-{submission_id}` | No |
| Cron (hourly/daily) | monitoring | `mon-{course_id}-{date}` | No |

The API stores `thread_id` on the owning row so it can resume reliably.

## 5. Security model

- JWT access tokens; `role` claim in `{student, faculty}`.
- FastAPI dependencies `require_faculty`, `require_student`, `require_owner_or_faculty_of_course`.
- Students: only their own rows; evaluations visible only when `released_at IS NOT NULL`.
- Faculty: only courses they own.
- Authenticity and class analytics endpoints: faculty only.
- Uploaded files: validate type/size, store outside web root, never execute.
- Prompt-injection defenses in `agents/common/guardrails.py`.

## 6. Observability

- Structured logging (JSON) with `submission_id`, `thread_id`, `graph`, `node`.
- Optional LangSmith tracing via env var (`LANGSMITH_TRACING`); never required.
- `agent_runs` table: graph, thread_id, status, started_at, finished_at, token usage, error.

## 7. Configuration (env)

```
DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/colearn
ANTHROPIC_API_KEY=
LLM_MODEL=                # set by the developer; do not hardcode
LLM_TEMPERATURE=0         # scoring should be deterministic-ish
SELF_CONSISTENCY_RUNS=2   # per-criterion repeated scoring for confidence
JWT_SECRET=
STORAGE_DIR=./storage
CONFIDENCE_REVIEW_THRESHOLD=0.75
AUTO_APPROVE_ENABLED=false
```

## 8. Failure handling

- LLM validation failure → retry once with the validation error appended → else mark criterion `needs_manual` (confidence 0) and flag the review item.
- Parse failure (corrupt PDF) → status `needs_attention`, alert faculty.
- Graph crash → `agent_runs.status='failed'`; a retry endpoint resumes from the last checkpoint.
