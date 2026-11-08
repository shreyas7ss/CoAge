# 07: API Specification (REST, FastAPI)

Base path `/api/v1`. JSON everywhere except file upload (`multipart/form-data`). Auth: `Authorization: Bearer <JWT>`. Standard error shape: `{"detail": "...", "code": "..."}`. Pagination: `?limit=&offset=`. Generate OpenAPI automatically and keep the frontend types in sync.

Legend: **F** = faculty only, **S** = student only, **A** = any authenticated user (scoped by ownership).

## Auth
| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/auth/login` | public | email + password → `{access_token, role, user}` |
| GET | `/auth/me` | A | current user |

## Courses and topics
| Method | Path | Role |
|---|---|---|
| GET | `/courses` | A (faculty: owned; student: enrolled) |
| POST | `/courses` | F |
| GET/POST | `/courses/{id}/topics` | A / F |
| PATCH/DELETE | `/topics/{id}` | F |
| POST | `/courses/{id}/enrollments` | F (bulk by emails/roll nos) |

## Assignments and grading package
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/courses/{id}/assignments` | A | students see published only |
| POST | `/courses/{id}/assignments` | F | creates draft; starts setup graph if `auto_draft=true` |
| GET | `/assignments/{id}` | A | students never receive reference answers/rubric details |
| PATCH | `/assignments/{id}` | F | only while draft/unlocked |
| POST | `/assignments/{id}/questions` | F | bulk create/replace |
| POST | `/assignments/{id}/question-paper` | F | upload file → parse_questions |
| GET | `/assignments/{id}/package?version=` | F | draft/approved packages |
| PUT | `/assignments/{id}/package/draft` | F | faculty edits draft |
| POST | `/assignments/{id}/package/decision` | F | `{approved, package?, comments?}` → **resumes setup graph** |
| POST | `/assignments/{id}/publish` | F | requires approved package; notifies students |

## Submissions
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/assignments/{id}/my-submission` | S | status + (after release) marks/feedback |
| POST | `/assignments/{id}/submissions` | S | upload; marks `is_late`; enqueues evaluation; optional `ai_disclosure` |
| POST | `/submissions/{id}/process-events` | S | opt-in counts/timing only |
| GET | `/assignments/{id}/submissions` | F | list with status, late flag, evaluation state |
| GET | `/assignments/{id}/completeness` | F | submitted / late / missing counts + lists |

## Review (faculty)
| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/courses/{id}/review-queue` | F | filter by assignment, flagged, confidence; sorted by priority |
| GET | `/evaluations/{id}` | F | per-criterion scores, evidence, confidence, flags, authenticity summary |
| POST | `/evaluations/{id}/decision` | F | `{final_scores:{criterion_id:marks}, feedback?, approve:true, comment?}` → **resumes evaluation graph** |
| POST | `/evaluations/{id}/release` | F | sets `released_at`; triggers feedback graph |
| POST | `/assignments/{id}/release-all` | F | release all approved |
| POST | `/evaluations/{id}/retry` | F | resume/restart after failure |

## Student results
| Method | Path | Role |
|---|---|---|
| GET | `/me/submissions` | S (status per assignment) |
| GET | `/submissions/{id}/result` | S (only if released) marks, per-question/topic breakdown, feedback |
| GET | `/me/mastery?course_id=` | S (topic mastery %, subject %, trend, weak topics, practice) |
| POST | `/submissions/{id}/appeal` | S (comment for faculty) |

## Understanding check
| Method | Path | Role |
|---|---|---|
| GET | `/me/followups` | S (pending checks with time limit) |
| POST | `/followups/{id}/answers` | S → resumes evaluation graph's authenticity branch |

## Analytics (faculty)
| Method | Path | Notes |
|---|---|---|
| GET | `/courses/{id}/analytics/heatmap` | topic × assignment matrix |
| GET | `/courses/{id}/analytics/topics` | mastery stats, % below threshold, top misconceptions |
| GET | `/courses/{id}/analytics/distribution?assignment_id=` | histogram + summary |
| GET | `/assignments/{id}/analytics/questions` | difficulty, discrimination, misconception counts |
| GET | `/courses/{id}/analytics/students` | per-student subject %, trend, flags |
| GET | `/students/{sid}/analytics?course_id=` | single student profile (faculty view) |
| GET | `/courses/{id}/analytics/ai-quality` | agreement, MAE, override rate, calibration |
| GET | `/courses/{id}/analytics/understanding-gap` | per-student trend |

## Authenticity (faculty only)
| Method | Path |
|---|---|
| GET | `/submissions/{id}/authenticity` |
| POST | `/submissions/{id}/authenticity/request-check` |
| POST | `/submissions/{id}/authenticity/review` (`{no_concern|note}`) |

## Alerts
| Method | Path | Role |
|---|---|---|
| GET | `/courses/{id}/alerts?status=open` | F |
| POST | `/alerts/{id}/resolve` | F |
| POST | `/courses/{id}/monitoring/run` | F (manual trigger of monitoring graph) |

## Contract rules
- Students must **never** receive: reference answers, rubric text, other students' data, authenticity data, raw AI scores before release.
- Every write that resumes a graph returns `202 Accepted` with `{status: "queued" | "interrupted" | "finished"}`.
- All timestamps ISO-8601 UTC. IDs are UUID strings.
- Write RBAC tests for every route group (student cannot call F routes; student A cannot read student B).
