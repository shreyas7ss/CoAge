"""Feedback graph safety and deterministic preprocessing tests."""

from app.agents.feedback.graph import build_feedback_graph
from app.schemas.llm import FeedbackGeneration
from tests.fake_llm import FakeLLM


def _fake(text: str = "You identified the key idea in your explanation.") -> FakeLLM:
    return FakeLLM(
        {
            FeedbackGeneration: lambda: FeedbackGeneration(
                feedback=text,
                misconceptions=["Confuses collisions with data loss"],
                suggested_practice=["Explain chaining", "Compare probing strategies"],
            )
        }
    )


def test_feedback_uses_student_answer_and_not_reference_answer() -> None:
    llm = _fake()
    graph = build_feedback_graph(llm_factory=lambda: llm)
    result = graph.invoke(
        {
            "submission_id": "s1",
            "context": [{"question": "Define a collision"}],
            "results": [{"final_awarded": 3, "max_marks": 5}],
            "answers": [
                {"question_id": "q1", "answer": "Name: Ada Lovelace. I define a collision."}
            ],
            "reference_answers": [
                "This long private reference answer must not reach the LLM. " * 2
            ],
            "weak_topics": ["Hashing"],
            "alerts": [],
        }
    )
    assert result["feedback"] == "You identified the key idea in your explanation."
    assert len(result["suggested_practice"]) == 2
    prompt = next(prompt for schema, prompt in llm.prompts if schema is FeedbackGeneration)
    assert "[name]" in prompt
    assert "This long private reference answer" not in prompt
    assert "STUDENT_ANSWER" in prompt


def test_feedback_validator_falls_back_if_authenticity_is_mentioned() -> None:
    graph = build_feedback_graph(
        llm_factory=lambda: _fake("The authenticity signals look unusual.")
    )
    result = graph.invoke(
        {
            "answers": [],
            "results": [],
            "weak_topics": ["Hashing"],
            "reference_answers": [],
            "alerts": [],
        }
    )
    assert result["validation_errors"]
    assert "authenticity" not in result["feedback"].lower()
    assert len(result["suggested_practice"]) == 2
