# Start Here: How to Use These Files with Claude Code

## Setup

1. Create an empty repo folder and copy this whole bundle into it (`CLAUDE.md` at the root, everything else under `docs/`).
2. Open the folder in Claude Code. It reads `CLAUDE.md` automatically.
3. Paste the kickoff prompts below **one phase at a time**. Review the diff and run the tests before moving on.

## Kickoff prompt (first message)

```
Read CLAUDE.md and every file in docs/ in the order listed. Then summarize the project back to me in
10 bullets, list any ambiguities or conflicts you found between the docs, and propose how you'd handle
each. Do not write code yet.
```

## Phase prompts

**Phase 0: Scaffolding**
```
Do Phase 0 from docs/09-BUILD-PLAN.md. Show me a plan of files first, then implement. Run the tests and
tick the checkboxes when done.
```

**Phase 1: Auth, roles, courses, topics**
```
Do Phase 1 from docs/09-BUILD-PLAN.md using docs/03-DATA-MODEL.md and docs/07-API-SPEC.md. Include
RBAC tests proving a student cannot access faculty endpoints or other students' data.
```

**Phase 2: Assignment setup graph**
```
Do Phase 2. First fetch the current LangGraph docs for interrupts and the Postgres checkpointer, confirm
the API for the installed version, then implement the assignment-setup graph from docs/04-LANGGRAPH-AGENTS.md
including the faculty-approval interrupt and package locking/versioning.
```

**Phase 3: Evaluation graph (core)**
```
Do Phase 3. Implement the evaluation graph exactly as specified in docs/04-LANGGRAPH-AGENTS.md: routing by
question type, per-criterion scoring with Send fan-out, injection check, confidence gate, faculty review
interrupt, finalize. Use a fake/mock LLM in tests; add one real-LLM smoke test behind an env flag.
```

**Phase 4: Analytics**
```
Do Phase 4. Implement app/analytics/ as pure functions per docs/05-ANALYTICS.md and make the worked examples
in docs/10-TESTING-EVAL.md pass as unit tests. Then add the analytics API endpoints.
```

**Phase 5: Feedback + monitoring graphs**
```
Do Phase 5: the feedback graph and the scheduled monitoring graph. Deadline/missing/at-risk detection must be
plain SQL/Python; use the LLM only to write digest and feedback text.
```

**Phase 6: Authenticity module**
```
Do Phase 6 following docs/06-AUTHENTICITY.md. Output concern levels plus evidence, never an AI percentage,
and never modify marks. Add the optional student follow-up interrupt.
```

**Phase 7: Frontend**
```
Do Phase 7 following docs/08-FRONTEND.md. Build student and faculty portals against the real API.
```

**Phase 8: Seed data, evaluation, polish**
```
Do Phase 8: seed script, calibration/evaluation script from docs/10-TESTING-EVAL.md, README with demo
walkthrough.
```

## Tips

- If Claude Code drifts, say: "Re-read CLAUDE.md rules 1-10 and fix your last change accordingly."
- Ask for a **plan before code** on every phase; it catches misunderstandings early.
- Keep `docs/DECISIONS.md` updated; it becomes useful material for your project report.
