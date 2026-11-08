# 03: Data Model

Source of truth for tables. Implement as SQLAlchemy models + Alembic migrations. Use UUID primary keys, `created_at`/`updated_at` timestamps (UTC) on every table.

## 1. Entity overview

```
users ─┬─ courses (faculty owns) ─┬─ topics (tree)
       │                          ├─ enrollments (students)
       │                          └─ assignments ─┬─ questions ─ rubric_criteria ─ (topic)
       │                                          └─ grading_packages (versioned)
       └─ submissions ─ submission_answers ─ evaluations ─ criterion_scores
                                    │             └─ topic_mastery_events → topic_mastery
                                    ├─ followup_checks
                                    ├─ authenticity_reports
                                    └─ feedback
alerts, agent_runs, correction_memory
```

## 2. Tables (DDL reference)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE user_role AS ENUM ('student','faculty');
CREATE TYPE question_type AS ENUM ('mcq','short_answer','code','open_ended');
CREATE TYPE ai_policy AS ENUM ('prohibited','allowed_with_disclosure','encouraged');
CREATE TYPE submission_status AS ENUM
  ('not_submitted','submitted','under_evaluation','pending_review','graded','needs_attention');
CREATE TYPE eval_status AS ENUM
  ('running','awaiting_review','approved','rejected','failed');

CREATE TABLE users (
  id UUID PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
  full_name TEXT NOT NULL, role user_role NOT NULL, roll_no TEXT,
  native_english BOOLEAN,            -- optional, self-reported; used ONLY to add caveats, never to score
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE courses (               -- a "subject"
  id UUID PRIMARY KEY, faculty_id UUID REFERENCES users(id),
  code TEXT NOT NULL, name TEXT NOT NULL, term TEXT
);
CREATE TABLE enrollments (
  course_id UUID REFERENCES courses(id), student_id UUID REFERENCES users(id),
  PRIMARY KEY (course_id, student_id)
);
CREATE TABLE topics (
  id UUID PRIMARY KEY, course_id UUID REFERENCES courses(id),
  name TEXT NOT NULL, parent_id UUID REFERENCES topics(id),
  weight NUMERIC DEFAULT 1.0          -- weight within the subject understanding %
);

CREATE TABLE assignments (
  id UUID PRIMARY KEY, course_id UUID REFERENCES courses(id),
  title TEXT NOT NULL, description TEXT,
  deadline TIMESTAMPTZ NOT NULL, allow_late BOOLEAN DEFAULT true,
  late_penalty_pct NUMERIC DEFAULT 0, max_marks NUMERIC NOT NULL,
  grade_weight NUMERIC DEFAULT 0,
  ai_policy ai_policy DEFAULT 'prohibited',
  require_understanding_check BOOLEAN DEFAULT false,
  status TEXT DEFAULT 'draft',        -- draft | published | closed
  active_package_version INT,
  setup_thread_id TEXT
);

CREATE TABLE questions (
  id UUID PRIMARY KEY, assignment_id UUID REFERENCES assignments(id),
  position INT NOT NULL, prompt TEXT NOT NULL, qtype question_type NOT NULL,
  max_marks NUMERIC NOT NULL,
  mcq_options JSONB, mcq_correct JSONB,   -- for mcq
  test_cases JSONB                         -- for code
);

-- Versioned, lockable grading package (reference answers + rubric + misconceptions)
CREATE TABLE grading_packages (
  id UUID PRIMARY KEY, assignment_id UUID REFERENCES assignments(id),
  version INT NOT NULL, status TEXT NOT NULL,   -- draft | approved (locked)
  content JSONB NOT NULL,                       -- see §3
  approved_by UUID REFERENCES users(id), approved_at TIMESTAMPTZ,
  UNIQUE (assignment_id, version)
);

-- Denormalised criteria for analytics joins (copied from approved package)
CREATE TABLE rubric_criteria (
  id UUID PRIMARY KEY, question_id UUID REFERENCES questions(id),
  package_version INT NOT NULL, description TEXT NOT NULL,
  marks NUMERIC NOT NULL, topic_id UUID REFERENCES topics(id),
  topic_weight NUMERIC DEFAULT 1.0
);

CREATE TABLE submissions (
  id UUID PRIMARY KEY, assignment_id UUID REFERENCES assignments(id),
  student_id UUID REFERENCES users(id),
  submitted_at TIMESTAMPTZ, is_late BOOLEAN DEFAULT false,
  status submission_status DEFAULT 'not_submitted',
  file_uri TEXT, ai_disclosure TEXT,
  eval_thread_id TEXT,
  UNIQUE (assignment_id, student_id)
);
CREATE TABLE submission_answers (       -- per-question parsed answer
  id UUID PRIMARY KEY, submission_id UUID REFERENCES submissions(id),
  question_id UUID REFERENCES questions(id),
  answer_text TEXT, embedding vector(1024)   -- dimension must match chosen embedding model
);

CREATE TABLE evaluations (
  id UUID PRIMARY KEY, submission_id UUID REFERENCES submissions(id),
  package_version INT NOT NULL, model TEXT, prompt_version TEXT,
  ai_total NUMERIC, final_total NUMERIC, confidence NUMERIC,
  status eval_status DEFAULT 'running',
  reviewed_by UUID REFERENCES users(id), reviewed_at TIMESTAMPTZ,
  released_at TIMESTAMPTZ,             -- students see nothing until set
  faculty_comment TEXT
);
CREATE TABLE criterion_scores (
  id UUID PRIMARY KEY, evaluation_id UUID REFERENCES evaluations(id),
  criterion_id UUID REFERENCES rubric_criteria(id),
  ai_awarded NUMERIC, final_awarded NUMERIC, max_marks NUMERIC,
  evidence TEXT, matched_misconception TEXT, confidence NUMERIC,
  needs_manual BOOLEAN DEFAULT false,
  faculty_note TEXT
);

CREATE TABLE topic_mastery_events (
  id UUID PRIMARY KEY, student_id UUID REFERENCES users(id),
  topic_id UUID REFERENCES topics(id), submission_id UUID REFERENCES submissions(id),
  score NUMERIC NOT NULL,             -- 0..1
  evidence_weight NUMERIC DEFAULT 1.0, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE topic_mastery (
  student_id UUID, topic_id UUID, mastery NUMERIC, confidence NUMERIC,
  n_events INT, updated_at TIMESTAMPTZ, PRIMARY KEY (student_id, topic_id)
);

CREATE TABLE feedback (
  id UUID PRIMARY KEY, submission_id UUID REFERENCES submissions(id),
  text TEXT NOT NULL, misconceptions JSONB, suggested_practice JSONB,
  released_at TIMESTAMPTZ
);

CREATE TABLE followup_checks (          -- understanding check (see 06-AUTHENTICITY)
  id UUID PRIMARY KEY, submission_id UUID REFERENCES submissions(id),
  questions JSONB NOT NULL, answers JSONB, score NUMERIC,
  issued_at TIMESTAMPTZ, answered_at TIMESTAMPTZ, time_limit_sec INT
);
CREATE TABLE authenticity_reports (
  id UUID PRIMARY KEY, submission_id UUID REFERENCES submissions(id) UNIQUE,
  concern_level TEXT,                  -- low | medium | high | insufficient_evidence
  signals JSONB NOT NULL, caveats JSONB, created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE writing_baselines (        -- per-student style features from prior work
  student_id UUID PRIMARY KEY, features JSONB, n_samples INT, updated_at TIMESTAMPTZ
);
CREATE TABLE process_events (           -- opt-in, counts/timing only, no content
  id UUID PRIMARY KEY, submission_id UUID REFERENCES submissions(id),
  kind TEXT, count INT, meta JSONB, created_at TIMESTAMPTZ DEFAULT now()
);

-- Co-learning loop: faculty corrections reused as few-shot examples
CREATE TABLE correction_memory (
  id UUID PRIMARY KEY, criterion_signature TEXT, question_type question_type,
  student_text_snippet TEXT, ai_awarded NUMERIC, final_awarded NUMERIC,
  faculty_note TEXT, embedding vector(1024), created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE alerts (
  id UUID PRIMARY KEY, course_id UUID REFERENCES courses(id),
  kind TEXT NOT NULL,                  -- missing | overdue | low_submission_rate | review_backlog | weak_topic | at_risk
  target_student_id UUID, target_assignment_id UUID, topic_id UUID,
  payload JSONB, status TEXT DEFAULT 'open', created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE agent_runs (
  id UUID PRIMARY KEY, graph TEXT, thread_id TEXT, status TEXT,
  started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, tokens_in INT, tokens_out INT, error TEXT
);
```

Add indexes on every FK, plus `(assignment_id, status)` on submissions and `(student_id, topic_id)` on events. Keep `vector` dimension configurable in one constant.

## 3. `grading_packages.content` JSON shape

```json
{
  "questions": [
    {
      "q_id": "Q1",
      "type": "short_answer",
      "reference_answer": "…",
      "acceptable_alternatives": "Any correct approach earns credit for the relevant criterion.",
      "common_misconceptions": ["Thinks collisions mean data is lost"],
      "rubric": [
        {"criterion": "Defines a collision", "marks": 2, "topic": "hashing-basics", "topic_weight": 1.0},
        {"criterion": "Explains chaining correctly", "marks": 4, "topic": "collision-resolution"}
      ]
    }
  ]
}
```

On approval, copy criteria into `rubric_criteria` with the package version. **Never mutate an approved package**; create version N+1.

## 4. Status state machine (submissions)

```
not_submitted → submitted → under_evaluation → pending_review → graded
                                   └────────→ needs_attention (parse/LLM failure)
```
Transitions are done only by services (not by routers directly) and logged.

## 5. Data rules

- A student has at most one submission per assignment (resubmission = update before deadline, keeping history in `process_events` or a `submission_versions` table if added).
- `evaluations.final_total` is what students see; `ai_total` is kept for agreement metrics.
- Students see evaluations/feedback only where `released_at IS NOT NULL`.
- `users.native_english` is optional and only used to attach caveats to authenticity reports. It must never influence scoring or concern level.
