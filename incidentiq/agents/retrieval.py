"""Retrieval specialist and adapter for Agent B's retrieval module."""

from collections.abc import Callable

from incidentiq.schemas import RetrievedEvidence

Retriever = Callable[[str], list[RetrievedEvidence]]


def default_retriever(question: str) -> list[RetrievedEvidence]:
    from incidentiq import retrieval

    search = getattr(retrieval, "retrieve", None) or getattr(retrieval, "search", None)
    if search is None:
        raise RuntimeError("incidentiq.retrieval must expose retrieve(question) or search(question)")
    return search(question)


def retrieve_evidence(question: str, retriever: Retriever) -> list[RetrievedEvidence]:
    return [RetrievedEvidence.model_validate(item) for item in retriever(question)]
