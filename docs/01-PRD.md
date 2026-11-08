# 01: Product Requirements (PRD)

## 1. Problem

Educational platforms store submissions and marks but give no automated insight into *what students understand*. Faculty spend large amounts of time grading and still miss early signs of misconception or missing work. Students lack one place to see submission status, marks and diagnostic feedback.

## 2. Goal

A dual-role portal with an AI evaluation agent that:
1. Evaluates submissions against faculty-defined reference solutions and rubrics, **with faculty approval in the loop**.
2. Computes **percentage-based concept understanding per topic and per subject**.
3. Monitors submission completeness and raises alerts (missing, overdue, at-risk, weak topics).
4. Gives students personalized diagnostic feedback.
5. Gives faculty evidence about authenticity and real understanding (see `06-AUTHENTICITY.md`).

## 3. Users and roles

| Role | Can do |
|---|---|
| **Faculty** | Create courses/subjects, topics, assignments, rubrics; approve grading packages; review AI-proposed grades; view class analytics, alerts, authenticity reports |
| **Student** | Enrol in courses, submit work, track status, view released marks/feedback, view own topic mastery, answer follow-up understanding checks |

(Admin is out of scope; seed users via script.)

## 4. Core user stories

### Faculty
- F1. Create a **subject** (course) with a **topic taxonomy**.
- F2. Create an **assignment** under a subject with deadline, marks, late policy, submission type.
- F3. Add questions; each question has type (mcq / short_answer / code / open_ended), reference answer, rubric criteria (marks + topic tag), common misconceptions.
- F4. Optionally let the AI **draft** the reference answer, rubric and topic tags; review, edit and approve; package is **locked and versioned**.
- F5. See a **completeness board**: submitted / late / missing per assignment.
- F6. Work a **review queue** of AI-evaluated submissions: approve, edit scores/feedback, or reject; low-confidence items are flagged.
- F7. See a **topic × assignment heatmap**, % of class below threshold per topic, score distributions, top misconceptions.
- F8. Receive **alerts**: approaching/overdue deadlines, low submission rate, review backlog, weak topics, at-risk students.
- F9. See an **authenticity report** per submission (concern level + evidence) and a class-level "understanding gap" trend.
- F10. Set **AI policy** per assignment (prohibited / allowed with disclosure / encouraged) and whether to require an understanding check.

### Student
- S1. See courses and assignments with deadlines.
- S2. Submit (upload file or in-portal editor) before/after deadline (late flagged).
- S3. Track status: `not_submitted → submitted → under_evaluation → pending_review → graded`.
- S4. After release: view marks, per-question and per-topic breakdown, personalized feedback.
- S5. View own topic mastery % and weak topics, with suggested practice.
- S6. When required, answer short follow-up questions about their own submission (understanding check).
- S7. Optionally disclose AI usage per submission.
- S8. Appeal / comment on a grade (stores a note for faculty).

## 5. Functional requirements (must / should / could)

**Must**
- Role-based auth and strict data isolation
- Assignment setup with locked, versioned grading package
- Evaluation graph with faculty-approval interrupt
- Mastery % per topic and per subject (formulas in `05-ANALYTICS.md`)
- Completeness board and basic alerts
- Student dashboard with status, marks and feedback

**Should**
- Item analysis (difficulty, discrimination), misconception counts
- Authenticity module (follow-up understanding check, baseline drift, similarity)
- Correction memory: past faculty corrections used as few-shot examples
- AI-vs-faculty agreement metrics

**Could**
- Code assignment sandbox grading
- Email/Telegram notifications
- Auto-approve policy once agreement is high

## 6. Non-functional requirements

- **Trust:** every AI score has an evidence quote and a confidence value; faculty can always override.
- **Reproducibility:** analytics computed deterministically from stored scores; every evaluation stores `rubric_version`, `model`, `prompt_version`.
- **Privacy:** anonymize before LLM calls; authenticity data faculty-only; keystroke/paste logging is opt-in and stores counts/timing only.
- **Performance:** a typical short-answer submission (5 questions) evaluates in < 60 s; the UI stays responsive (async job + status polling).
- **Fairness:** authenticity signals must not rely solely on text-statistics detectors (known bias against non-native English writers). Caveats are shown to faculty.

## 7. Out of scope (v1)

LMS integrations (Moodle/Canvas), plagiarism against external web corpora, mobile apps, multi-institution tenancy, payments.

## 8. Success metrics (for the project report)

- AI-vs-faculty score agreement (MAE ≤ ~10% of max marks on the calibration set; report actual)
- % of AI scores unchanged by faculty
- Faculty review time per submission vs. manual baseline (estimate)
- Mastery metric stability and face validity on seeded data
- Zero cross-role data leaks in RBAC tests
