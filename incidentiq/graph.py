"""LangGraph supervisor with retrieval, analysis, and citation specialists."""

from time import perf_counter
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph

from incidentiq.agents.analysis import analyze_incident
from incidentiq.agents.citation import validate_citations
from incidentiq.agents.retrieval import Retriever, default_retriever, retrieve_evidence
from incidentiq.config import Settings
from incidentiq.inference import InferenceProvider, get_provider
from incidentiq.schemas import AgentState, RetrievedEvidence


class WorkflowState(AgentState, total=False):
    stage: str
    started_at: float


def build_graph(
    retriever: Retriever | None = None,
    provider: InferenceProvider | None = None,
    checkpointer: Any | None = None,
    settings: Settings | None = None,
):
    """Compile the workflow; retain the returned graph for thread memory."""
    active_retriever = retriever or default_retriever
    active_provider = provider or get_provider(settings)

    def prepare(state: WorkflowState, config: RunnableConfig) -> dict[str, Any]:
        thread_id = config.get("configurable", {}).get("thread_id")
        if not thread_id or thread_id != state.get("thread_id"):
            raise ValueError("Pass the unchanged thread_id in state and config.configurable.thread_id")
        question = state.get("question", "").strip()
        if not question:
            raise ValueError("question must be nonempty")
        messages = list(state.get("messages") or [])
        messages.append({"role": "user", "content": question})
        return {
            "question": question, "messages": messages, "evidence": [], "answer": "",
            "citations": [], "abstained": False, "provider": active_provider.name,
            "specialist_route": "", "latency_ms": 0.0, "stage": "retrieve",
            "started_at": perf_counter(),
        }

    def supervisor(state: WorkflowState) -> dict[str, Any]:
        stage = state["stage"]
        route = {"retrieve": "retrieval", "analyze": "incident_analysis", "validate": "citation_validation"}.get(stage)
        if route is None:
            raise ValueError(f"Unknown workflow stage: {stage}")
        return {"specialist_route": route}

    def route(state: WorkflowState) -> str:
        return state["specialist_route"]

    def retrieval_node(state: WorkflowState) -> dict[str, Any]:
        return {"evidence": retrieve_evidence(state["question"], active_retriever), "stage": "analyze"}

    def analysis_node(state: WorkflowState) -> dict[str, Any]:
        evidence = [RetrievedEvidence.model_validate(item) for item in state.get("evidence", [])]
        answer, citations, abstained = analyze_incident(
            state["question"], evidence, list(state.get("messages", []))[:-1], active_provider
        )
        return {"answer": answer, "citations": citations, "abstained": abstained, "stage": "validate"}

    def citation_node(state: WorkflowState) -> dict[str, Any]:
        evidence = [RetrievedEvidence.model_validate(item) for item in state.get("evidence", [])]
        answer, citations, abstained = validate_citations(
            state.get("answer", ""), state.get("citations", []), evidence, state.get("abstained", False)
        )
        messages = list(state.get("messages", []))
        messages.append({"role": "assistant", "content": answer})
        return {
            "answer": answer, "citations": citations, "abstained": abstained,
            "messages": messages, "specialist_route": "incident_analysis" if not abstained else "citation_validation",
            "latency_ms": max(0.0, (perf_counter() - state["started_at"]) * 1000),
            "stage": "done",
        }

    workflow = StateGraph(WorkflowState)
    workflow.add_node("prepare", prepare)
    workflow.add_node("supervisor", supervisor)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("incident_analysis", analysis_node)
    workflow.add_node("citation_validation", citation_node)
    workflow.add_edge(START, "prepare")
    workflow.add_edge("prepare", "supervisor")
    workflow.add_conditional_edges("supervisor", route, {
        "retrieval": "retrieval", "incident_analysis": "incident_analysis",
        "citation_validation": "citation_validation",
    })
    workflow.add_edge("retrieval", "supervisor")
    workflow.add_edge("incident_analysis", "supervisor")
    workflow.add_edge("citation_validation", END)
    default_checkpointer = MemorySaver(
        serde=JsonPlusSerializer(allowed_msgpack_modules=[("incidentiq.schemas", "RetrievedEvidence")])
    )
    return workflow.compile(checkpointer=checkpointer if checkpointer is not None else default_checkpointer)
