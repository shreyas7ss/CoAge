# 08: Frontend Specification

Next.js (App Router) + TypeScript + Tailwind. Generate a typed API client from the backend OpenAPI schema. Charts: Recharts. Tables: TanStack Table. Keep the UI clean and fast; no heavy component library required (shadcn/ui is fine).

## 1. Route structure

```
/login
/student
  /student/courses
  /student/courses/[courseId]                    # assignments list + status chips
  /student/assignments/[assignmentId]            # details, submit, status tracker
  /student/submissions/[submissionId]            # released result: marks, topic breakdown, feedback
  /student/mastery/[courseId]                    # topic mastery %, subject %, trend, practice
  /student/followups                             # pending understanding checks (timed)
/faculty
  /faculty/courses
  /faculty/courses/[courseId]                    # overview: alerts, completeness, quick stats
  /faculty/courses/[courseId]/topics
  /faculty/courses/[courseId]/assignments/new    # creation wizard
  /faculty/assignments/[assignmentId]            # setup/review package, publish, submissions
  /faculty/assignments/[assignmentId]/completeness
  /faculty/courses/[courseId]/review             # review queue
  /faculty/evaluations/[evaluationId]            # review screen
  /faculty/courses/[courseId]/analytics          # heatmap, topics, distribution, questions
  /faculty/students/[studentId]?courseId=        # student profile
  /faculty/courses/[courseId]/alerts
  /faculty/courses/[courseId]/ai-quality
```
Route groups enforce role: redirect to `/login` if unauthenticated; redirect to the correct home if the role mismatches. Never rely on the frontend for security; the API enforces RBAC.

## 2. Key screens

### Student
- **Assignment page:** deadline countdown, late warning, upload box or in-portal editor, optional AI-disclosure field, **status tracker** (`submitted → under evaluation → pending review → graded`).
- **Result page** (only when released): total, per-question marks, topic breakdown bars, AI-written feedback, misconceptions list, suggested practice, "appeal/comment" box.
- **Mastery page:** subject understanding % with coverage note, topic bars with trend arrows, weak topics highlighted, practice prompts.
- **Understanding check:** countdown timer, short text answers, autosave, clear explanation ("This checks that you can explain your own work").

### Faculty
- **Assignment creation wizard** (steps): 1 Basics → 2 Questions (manual or upload) → 3 Topic tagging → 4 Grading package (AI draft or upload) → 5 Review & approve (editable table: reference answer, criteria, marks, topic, misconceptions; validation shows marks sum) → 6 Publish.
- **Completeness board:** table of students with status chips (submitted/late/missing/evaluating/graded), filters, "remind" action (stub OK).
- **Review queue:** sortable by priority; badges: low-confidence, injection flag, authenticity concern, backlog age.
- **Review screen:** left = student answer per question; right = criterion cards with AI mark, **evidence quote**, confidence, misconception, editable final mark and note; bottom = feedback draft (editable), authenticity panel (collapsed by default), "Approve", "Approve & release", "Send back".
- **Analytics:** (1) topic × assignment heatmap, (2) % below threshold per topic with alert toggles, (3) score histogram, (4) question quality table (difficulty, discrimination with labels), (5) top misconceptions, (6) student table with subject %, trend, at-risk badge.
- **Alerts:** list grouped by kind, with resolve action.
- **AI quality:** agreement rate, MAE, override rate by criterion, calibration chart, agreement-over-time line.

## 3. UX rules

- Every number that comes from analytics shows a tooltip with its definition and sample size; show "low data" instead of misleading values when `n` is small.
- Authenticity UI uses neutral, careful language ("signals suggest review"), never "cheater", never an AI percentage; always display caveats.
- Students never see raw AI-vs-faculty data or authenticity info.
- Long-running actions show progress/polling states; resumed graph calls show "queued → running → done".
- Accessibility: keyboard navigation, labels, sufficient contrast, responsive down to tablet.

## 4. State and data fetching

- Use React Query (TanStack Query) with polling for submission/evaluation status (5-10 s while non-terminal).
- Store JWT in an httpOnly cookie via a Next route handler (preferred) or memory + refresh flow; avoid localStorage for tokens.
- Form validation with zod; share constraints (e.g., marks sum equals max) with server messages.

## 5. Optional process-logging editor (opt-in)

If the course enabled process logging, the in-portal editor posts aggregate events (paste count/size bucket, active time, draft saves) to `/submissions/{id}/process-events` every 30 s. Show a clear notice explaining what is and isn't recorded (counts/timing only, never content) and let students see it before they start.

## 6. Design

Simple, calm, high-density tables for faculty; friendly, encouraging tone for students. Use consistent status colors (green graded, amber pending, red missing/overdue, grey not started). Provide dark mode only if time permits.
