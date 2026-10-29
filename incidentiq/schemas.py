"""Shared request, response, evidence, and graph state contracts."""

from typing import Any, TypedDict

from pydantic import BaseModel, Field


class IncidentRequest(BaseModel):
    question: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)


class RetrievedEvidence(BaseModel):
    document_id: str
    chunk_id: str
    text: str
    similarity_score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class IncidentResponse(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)
    specialist_route: str
    provider: str
    latency_ms: float = Field(ge=0)
    abstained: bool


class AgentState(TypedDict, total=False):
    """Shared LangGraph state keys."""

    question: str
    thread_id: str
    specialist_route: str
    evidence: list[RetrievedEvidence]
    answer: str
    citations: list[str]
    provider: str
    abstained: bool
    latency_ms: float
    messages: list[Any]
