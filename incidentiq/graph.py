"""LangGraph supervisor with retrieval, analysis, and citation specialists."""

import re
import logging
from time import perf_counter
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph

from incidentiq.agents.analysis import analyze_incident
from incidentiq.agents.citation import validate_citations
from incidentiq.agents.retrieval import Retriever, default_retriever
from incidentiq.agents.routing import select_specialist
from incidentiq.agents.tools import invoke_tool
from incidentiq.config import Settings
from incidentiq.inference import InferenceProvider, get_provider
from incidentiq.retrieval import evidence_is_sufficient
from incidentiq.schemas import AgentState, RetrievedEvidence


INCIDENT_ID = re.compile(r"\bINC-\d{4,}\b", re.IGNORECASE)
logger = logging.getLogger("uvicorn.error")


class WorkflowState(AgentState, total=False):
    stage: str
    started_at: float
    next_node: str
    specialist_trace: list[str]


def build_graph(
    retriever: Retriever | None = None,
    provider: InferenceProvider | None = None,
    checkpointer: Any | None = None,
    settings: Settings | None = None,
):
    """Compile the workflow; retain the returned graph for thread memory."""
    active_retriever = retriever or default_retriever
    active_settings = settings or Settings()
    active_provider = provider or get_provider(active_settings)

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
            "specialist_trace": [],
            "started_at": perf_counter(),
        }

    def supervisor(state: WorkflowState) -> dict[str, Any]:
        stage = state["stage"]
        route = {"retrieve": "retrieval", "analyze": select_specialist(state["question"]),
                 "validate": "citation_validation"}.get(stage)
        if route is None:
            raise ValueError(f"Unknown workflow stage: {stage}")
        result = {"next_node": route}
        if stage == "analyze":
            result["specialist_route"] = route
        return result

    def route(state: WorkflowState) -> str:
        return state["next_node"]

    def retrieval_node(state: WorkflowState) -> dict[str, Any]:
        query = state["question"]
        if not INCIDENT_ID.search(query):
            for message in reversed(state.get("messages", [])[:-1]):
                if message.get("role") == "user":
                    previous_id = INCIDENT_ID.search(message.get("content", ""))
                    if previous_id:
                        query = f"{query} {previous_id.group().upper()}"
                        break
        evidence = invoke_tool("incident_retrieval", query, active_retriever)
        logger.info("retrieval query=%r evidence=%s", query,
                    [(item.document_id, item.chunk_id) for item in evidence])
        if not evidence_is_sufficient(query, evidence):
            logger.info("retrieval evidence insufficient for query=%r", query)
            evidence = []
        return {"evidence": evidence,
                "stage": "analyze", "specialist_trace": [*state.get("specialist_trace", []), "retrieval"]}

    def specialist_node(name: str):
        def execute(state: WorkflowState) -> dict[str, Any]:
            evidence = [RetrievedEvidence.model_validate(item) for item in state.get("evidence", [])]
            logger.info("specialist=%s evidence_chunks=%s", name, [item.chunk_id for item in evidence])
            answer, citations, abstained = analyze_incident(
                state["question"], evidence, list(state.get("messages", []))[:-1], active_provider,
                specialist=name, deadline_at=state["started_at"] + active_settings.REQUEST_DEADLINE_SECONDS,
            )
            return {"answer": answer, "citations": citations, "abstained": abstained,
                    "stage": "validate", "specialist_trace": [*state.get("specialist_trace", []), name]}
        return execute

    def citation_node(state: WorkflowState) -> dict[str, Any]:
        evidence = [RetrievedEvidence.model_validate(item) for item in state.get("evidence", [])]
        answer, citations, abstained = validate_citations(
            state.get("answer", ""), state.get("citations", []), evidence, state.get("abstained", False)
        )
        logger.info("citation_validation citations=%s abstained=%s", citations, abstained)
        messages = list(state.get("messages", []))
        messages.append({"role": "assistant", "content": answer})
        return {
            "answer": answer, "citations": citations, "abstained": abstained,
            "messages": messages,
            "specialist_trace": [*state.get("specialist_trace", []), "citation_validation"],
            "latency_ms": max(0.0, (perf_counter() - state["started_at"]) * 1000),
            "stage": "done",
        }

    workflow = StateGraph(WorkflowState)
    workflow.add_node("prepare", prepare)
    workflow.add_node("supervisor", supervisor)
    workflow.add_node("retrieval", retrieval_node)
    for specialist in ("investigator", "planner", "communicator"):
        workflow.add_node(specialist, specialist_node(specialist))
    workflow.add_node("citation_validation", citation_node)
    workflow.add_edge(START, "prepare")
    workflow.add_edge("prepare", "supervisor")
    workflow.add_conditional_edges("supervisor", route, {
        "retrieval": "retrieval", "investigator": "investigator",
        "planner": "planner", "communicator": "communicator",
        "citation_validation": "citation_validation",
    })
    workflow.add_edge("retrieval", "supervisor")
    for specialist in ("investigator", "planner", "communicator"):
        workflow.add_edge(specialist, "supervisor")
    workflow.add_edge("citation_validation", END)
    default_checkpointer = MemorySaver(
        serde=JsonPlusSerializer(allowed_msgpack_modules=[("incidentiq.schemas", "RetrievedEvidence")])
    )
    return workflow.compile(checkpointer=checkpointer if checkpointer is not None else default_checkpointer)
