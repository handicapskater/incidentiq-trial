"""Citation validation specialist."""

from incidentiq.schemas import RetrievedEvidence


ABSTENTION = "I don't have enough verified evidence to answer this incident question."


def validate_citations(
    answer: str,
    citations: list[str],
    evidence: list[RetrievedEvidence],
    abstained: bool,
) -> tuple[str, list[str], bool]:
    allowed = {item.chunk_id for item in evidence if item.text.strip()}
    if abstained or not answer.strip() or not citations or any(item not in allowed for item in citations):
        return ABSTENTION, [], True
    return answer, list(dict.fromkeys(citations)), False
