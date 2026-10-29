"""The graph's sole tool boundary: scoped incident evidence retrieval."""

from incidentiq.agents.retrieval import Retriever, retrieve_evidence
from incidentiq.schemas import RetrievedEvidence

ALLOWED_TOOLS = frozenset({"incident_retrieval"})


class ToolNotAllowed(PermissionError):
    """A requested operation is outside the graph's tool allowlist."""


def invoke_tool(name: str, query: str, retriever: Retriever) -> list[RetrievedEvidence]:
    """Run only the configured retrieval adapter; never dispatch arbitrary code."""
    if name not in ALLOWED_TOOLS:
        raise ToolNotAllowed(f"Tool '{name}' is not allowed")
    return retrieve_evidence(query, retriever)
