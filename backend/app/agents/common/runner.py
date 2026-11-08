"""Graph runner: a thin interface to start/resume LangGraph threads."""

from typing import Any

from langgraph.types import Command

from app.agents.common.checkpointer import get_checkpointer
from app.agents.common.llm import get_llm

_runtime: dict[str, Any] = {}


def configure_runtime(checkpointer: Any = None, llm_factory: Any = None) -> None:
    """Configure (or reset) the checkpointer / LLM factory used by the runner.

    Tests call this with an ``InMemorySaver`` and a fake LLM factory so the same
    checkpointer is reused across ``start``/``resume`` calls.
    """
    _runtime["checkpointer"] = checkpointer
    _runtime["llm_factory"] = llm_factory
    _runtime["graphs"] = {}


def _build_graph(graph_name: str) -> Any:
    graphs = _runtime.setdefault("graphs", {})
    if graph_name not in graphs:
        checkpointer = _runtime.get("checkpointer") or get_checkpointer()
        llm_factory = _runtime.get("llm_factory") or get_llm
        if graph_name == "setup":
            from app.agents.setup.graph import build_setup_graph

            graphs[graph_name] = build_setup_graph(
                checkpointer=checkpointer, llm_factory=llm_factory
            )
        elif graph_name == "evaluation":
            from app.agents.evaluation.graph import build_evaluation_graph

            graphs[graph_name] = build_evaluation_graph(
                checkpointer=checkpointer, llm_factory=llm_factory
            )
        elif graph_name == "feedback":
            from app.agents.feedback.graph import build_feedback_graph

            graphs[graph_name] = build_feedback_graph(llm_factory=llm_factory)
        elif graph_name == "monitoring":
            from app.agents.monitoring.graph import build_monitoring_graph

            graphs[graph_name] = build_monitoring_graph(llm_factory=llm_factory)
        else:
            raise ValueError(f"unknown graph: {graph_name}")
    return graphs[graph_name]


def _interrupt_values(result: dict) -> list[Any]:
    values: list[Any] = []
    for interrupt in result.get("__interrupt__") or []:
        values.append(getattr(interrupt, "value", interrupt))
    return values


def _to_result(result: dict) -> dict:
    interrupts = _interrupt_values(result)
    if interrupts:
        return {"status": "interrupted", "interrupt": interrupts, "state": result}
    return {"status": "finished", "state": result}


def start(graph_name: str, thread_id: str, input_data: dict) -> dict:
    graph = _build_graph(graph_name)
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(input_data, config)
    return _to_result(result)


def resume(graph_name: str, thread_id: str, resume_value: Any) -> dict:
    graph = _build_graph(graph_name)
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(Command(resume=resume_value), config)
    return _to_result(result)
