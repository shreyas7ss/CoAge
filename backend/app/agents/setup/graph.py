"""Graph A: Assignment Setup Graph.

Turns faculty input into an approved, locked, versioned grading package.

Flow (see docs/04-LANGGRAPH-AGENTS.md §1):
    draft_grading_package -> validate_package -> faculty_review (interrupt)
        -> lock_and_version -> END, with a bounded reject loop back to drafting.

The graph is *pure* (no DB access). The service layer loads questions/topics into
the input state and persists the finished package (versioning + rubric_criteria).
"""

import json
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents.common.guardrails import validate_package
from app.agents.common.prompts import load_prompt
from app.schemas.llm import DraftedPackage

MAX_REJECTIONS = 2


class SetupState(TypedDict, total=False):
    assignment_id: str
    course_topics: list[dict]  # [{id, name}]
    questions: list[dict]  # [{q_id, prompt, qtype, max_marks}]
    package_draft: dict | None
    skip_draft: bool  # faculty provided a full package; skip LLM drafting
    faculty_comments: str | None
    faculty_decision: dict | None  # {approved, package?, comments?}
    rejection_count: int
    validation_errors: list[str]
    final_package: dict | None
    status: str  # draft | approved


def _render_prompt(template: str, state: SetupState) -> str:
    text = template.replace(
        "[[TOPICS]]", json.dumps(state.get("course_topics", []), indent=2)
    ).replace("[[QUESTIONS]]", json.dumps(state.get("questions", []), indent=2))
    comments = state.get("faculty_comments")
    if comments:
        text += f"\n\nFaculty feedback to incorporate:\n{comments}\n"
    return text


def build_setup_graph(checkpointer: Any = None, llm_factory: Any = None):
    from app.agents.common.llm import get_llm

    llm_factory = llm_factory or get_llm

    def draft_grading_package(state: SetupState) -> dict:
        if state.get("skip_draft"):
            return {}
        structured = llm_factory().with_structured_output(DraftedPackage)
        template, _ = load_prompt("setup_draft")
        result = structured.invoke(_render_prompt(template, state))
        return {"package_draft": result.model_dump(), "faculty_comments": None}

    def validate_package_node(state: SetupState) -> dict:
        draft = state.get("package_draft")
        if draft is None:
            return {"package_draft": {"questions": []}, "validation_errors": ["No package draft"]}
        errors, repaired = validate_package(draft, state["questions"], state["course_topics"])
        return {"package_draft": repaired, "validation_errors": errors}

    def faculty_review(state: SetupState) -> dict:
        decision = interrupt(
            {
                "assignment_id": state["assignment_id"],
                "package": state["package_draft"],
                "validation_errors": state["validation_errors"],
            }
        )
        out: dict = {"faculty_decision": decision}
        if decision.get("approved"):
            out["status"] = "approved"
        else:
            out["rejection_count"] = state.get("rejection_count", 0) + 1
            if decision.get("package"):
                out["package_draft"] = decision["package"]
                out["skip_draft"] = True
                out["faculty_comments"] = None
            else:
                out["faculty_comments"] = decision.get("comments")
                out["skip_draft"] = False
        return out

    def lock_and_version(state: SetupState) -> dict:
        decision = state.get("faculty_decision") or {}
        if decision.get("approved"):
            final = decision.get("package") or state.get("package_draft")
            return {"final_package": final, "status": "approved"}
        return {"final_package": state.get("package_draft"), "status": "draft"}

    def route_after_review(
        state: SetupState,
    ) -> Literal["draft_grading_package", "lock_and_version"]:
        decision = state.get("faculty_decision") or {}
        if decision.get("approved"):
            return "lock_and_version"
        if state.get("rejection_count", 0) > MAX_REJECTIONS:
            return "lock_and_version"  # exhausted: end in draft
        return "draft_grading_package"

    builder = StateGraph(SetupState)
    builder.add_node("draft_grading_package", draft_grading_package)
    builder.add_node("validate_package", validate_package_node)
    builder.add_node("faculty_review", faculty_review)
    builder.add_node("lock_and_version", lock_and_version)

    builder.add_edge(START, "draft_grading_package")
    builder.add_edge("draft_grading_package", "validate_package")
    builder.add_edge("validate_package", "faculty_review")
    builder.add_conditional_edges(
        "faculty_review",
        route_after_review,
        {
            "draft_grading_package": "draft_grading_package",
            "lock_and_version": "lock_and_version",
        },
    )
    builder.add_edge("lock_and_version", END)

    return builder.compile(checkpointer=checkpointer)
