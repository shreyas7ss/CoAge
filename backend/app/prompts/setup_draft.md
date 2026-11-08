# Assignment setup prompt

You are helping a faculty member build a grading package for an assignment.

Given the questions and the course's topic list, draft, for **each** question:
- a reference answer (what a correct answer must contain),
- acceptable alternatives (a short note that different correct methods earn credit),
- common misconceptions (list),
- a rubric: 3-5 specific criteria, each with a short ``criterion`` description,
  a ``marks`` value, and exactly one ``topic`` chosen ONLY from the provided topic list.

Constraints:
- The rubric ``marks`` for each question must be designed to sum to that question's ``max_marks``.
- Choose ``topic`` ids ONLY from the list below; never invent a topic id.
- MCQ and code questions do not need a long reference answer; a short key answer is fine.

Course topics (id → name):
[[TOPICS]]

Questions:
[[QUESTIONS]]

Return the structured result.
