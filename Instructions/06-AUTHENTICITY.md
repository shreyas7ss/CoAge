# 06: Authenticity & Understanding Module

## 1. Purpose and principles

Help faculty see **which students understand their own work** versus which may rely entirely on AI, using several independent signals and an **understanding check**, not a single detector score.

**Why not a plain "AI %" detector?** Text-statistics detectors give probability-style scores (not a measured share of AI text), can be evaded by simple rewriting, and are documented to be biased against non-native English writers. Evidence: Stanford HAI summary of the Liang et al. study: https://hai.stanford.edu/news/ai-detectors-biased-against-non-native-english-writers?sf184834105=1 ; overview: https://en.wikipedia.org/wiki/Artificial_intelligence_content_detection

**Hard rules**
1. Output a **concern level** (`low | medium | high | insufficient_evidence`) plus an **evidence list**. Never output "X% written by AI."
2. **Never change marks automatically.** Faculty-only visibility. Never shown in student feedback.
3. Each signal is explained in plain language with its limits.
4. Attach caveats automatically (few baseline samples, self-reported non-native English, code assignment, etc.).
5. Respect assignment `ai_policy`: if AI is `allowed_with_disclosure` or `encouraged`, the module reports *understanding* signals and checks disclosure consistency, not "AI use" as wrongdoing.
6. Process logging (paste/timing) is **opt-in per course**, disclosed to students, stores counts/timing only, never keystroke content.

## 2. Signals

| ID | Signal | Data needed | Strength weight |
|---|---|---|---|
| S1 | **Understanding check** (follow-up questions about the student's own answers) | `followup_checks` | 3 |
| S2 | **Baseline style drift** vs. the student's own prior submissions | ≥ 2 prior samples | 2 |
| S3 | **Process provenance** (large paste events, very short editing time, no drafts) | `process_events` (opt-in) | 2 |
| S4 | **Cross-student similarity** on the same question | embeddings | 2 |
| S5 | **Course alignment** (uses taught terminology/examples; real citations) | course materials index (optional) | 1 |
| S6 | Perplexity/burstiness detector (optional, off by default) | none | 0.5 (never alone) |
| S7 | Code only: commit history shape + "explain this function" check | repo/zip | 2 |

## 3. Signal implementations

### S1: Understanding check (strongest, most important)
Node `generate_followup_questions` (LLM): from the student's **own answers**, produce 2-3 short questions that require explaining/applying what they wrote (e.g., "In Q3 you used open addressing: what changes when the load factor exceeds 0.7?"). Constraints: answerable in 1-3 sentences; time-limited (default 5-8 min); not answerable by simply re-pasting; non-leading.
Flow: store in `followup_checks`; `interrupt()` waiting for the student's answers; resume → `score_followup_answers` (LLM against the student's own answers + reference, structured scores, same grader safeguards). Score is 0..1.
Interpretation: `followup_score` much lower than `submission_score` raises concern. Allow one retake/appeal path. Offer accommodations (extra time) via faculty flag.

### S2: Baseline style drift
Compute per-submission features (no LLM): mean/std sentence length, type-token ratio, average word length, punctuation rates (commas, semicolons, em-dashes, parentheses), function-word frequency vector (top ~100 English stopwords), paragraph length variance, passive-voice rate (heuristic), transition-word rate.
Baseline = mean/std of features over the student's previous samples (≥ 2, ≥ 150 words each) stored in `writing_baselines`. Drift = mean absolute z-score across features (cap per feature at 3). Raise signal if drift > 2.0 (configurable). Drop to "insufficient" when baseline is thin. Update the baseline **after** review, only with submissions faculty did not flag.

### S3: Process provenance
Client-side editor reports counts: paste events (+size bucket), revision count, active writing time, number of draft saves. Raise if: a single paste ≥ 70% of final length, or active time < X minutes for Y words, or zero drafts on a long answer. Absence of data = `not_available` (not suspicious).

### S4: Cross-student similarity
For each question, embed answers; compute cosine similarity within the class (pgvector). Flag pairs/clusters above 0.90 (tunable) **and** share unusual structure. Report the cluster ID and size, not other students' names to the student; faculty see names.

### S5: Course alignment
Check key terms/notation against the course topic list and (optionally) uploaded lecture notes; flag generic answers that miss taught terms; flag citations/URLs that don't resolve or look fabricated (verify format; don't fetch the web by default).

### S6: Optional detector
Perplexity/burstiness via a local small LM or a vendor API. **Off by default**; if enabled, weight is minimal and a bias caveat is always attached.

### S7: Code assignments
Signals: commit/edit history (one giant commit vs. incremental), comment/naming style vs. baseline, plus a short "explain what this function does and why" check.

## 4. Concern level (deterministic)

Each signal returns `{id, status: raised|neutral|not_available, detail, strength_weight}`.
```
score = Σ weight for signals with status == raised
available = number of signals not 'not_available' AND having meaningful data
if available < 2:             level = insufficient_evidence
elif score >= 6:              level = high
elif score >= 3:              level = medium
else:                         level = low
```
If S1 was performed and passed (followup_score ≥ 0.7), cap level at `medium` regardless of other signals. Thresholds in config.

## 5. Report shape (`authenticity_reports.signals` / API)

```json
{
  "concern_level": "medium",
  "signals": [
    {"id": "S1", "status": "raised", "detail": "Answered 1/3 follow-ups correctly; could not explain Q2's approach.", "weight": 3},
    {"id": "S2", "status": "raised", "detail": "Sentence length and vocabulary differ from A1/A2 (drift z=2.6).", "weight": 2},
    {"id": "S4", "status": "neutral", "detail": "No unusually similar answers."},
    {"id": "S3", "status": "not_available", "detail": "Process logging not enabled."}
  ],
  "caveats": ["Only 2 baseline samples", "Student self-reports non-native English; style signals less reliable"],
  "policy": {"ai_policy": "prohibited", "student_disclosure": null}
}
```

## 6. UI requirements (faculty)

- Compact badge in the review queue; click-through to the evidence list.
- Each signal expandable with plain-language explanation and limits.
- Buttons: "Request understanding check", "Mark as reviewed – no concern", "Add note".
- Class view: trend of `understanding_gap` per student (see `05-ANALYTICS.md` §8). No leaderboard of "most AI".

## 7. Fairness and testing

- Log concern-level rates by `native_english` flag (when provided) and by course; surface a warning if rates differ strongly.
- Unit tests: S2 drift on synthetic same-author vs. different-author texts; S4 similarity on seeded clusters; concern-level function with table-driven cases; S1 pass caps level at medium.
- Never use `native_english` to score; only to add a caveat.
- Document known limitations in the README and project report.
