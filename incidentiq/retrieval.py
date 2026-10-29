"""Persistent Chroma ingestion and cited incident retrieval.

The collection uses cosine distance over normalized MiniLM vectors. Returned
similarity_score is 1 - cosine_distance, so a higher value is a better match.
No similarity cutoff is applied unless a caller explicitly sets one.
"""

import json
import re
from pathlib import Path

import chromadb

from incidentiq.config import Settings
from incidentiq.embeddings import EMBEDDING_DIMENSION, embed_query, embed_texts
from incidentiq.schemas import RetrievedEvidence

COLLECTION_NAME = "incidentiq_evidence"
INCIDENT_ID_PATTERN = re.compile(r"\bINC-\d{4,}\b", re.IGNORECASE)
DOCUMENT_TYPES = {"report", "logs", "runbook", "postmortem"}


def chunk_text(text: str, max_words: int = 120, overlap_words: int = 20) -> list[str]:
    """Split on words deterministically, retaining nearby context at boundaries."""
    if max_words < 1 or not 0 <= overlap_words < max_words:
        raise ValueError("Require max_words > overlap_words >= 0")
    words = text.split()
    step = max_words - overlap_words
    return [" ".join(words[start:start + max_words]) for start in range(0, len(words), step)
            if start == 0 or start + overlap_words < len(words)]


class IncidentRetriever:
    def __init__(self, chroma_path: str | Path | None = None, collection_name: str = COLLECTION_NAME):
        path = Path(chroma_path or Settings().CHROMA_PATH)
        path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(path))
        self.collection = self.client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine", "embedding_model": "all-MiniLM-L6-v2", "embedding_dimension": EMBEDDING_DIMENSION}
        )
        if self.collection.metadata.get("hnsw:space") != "cosine":
            raise ValueError("Existing collection must use cosine distance")

    def ingest(self, corpus_path: str | Path = "corpus") -> tuple[int, int]:
        """Upsert all JSON documents and remove stale chunks from changed documents.

        Returns (document_count, chunk_count) for this ingestion pass.
        """
        files = sorted(Path(corpus_path).glob("*.json"))
        if not files:
            raise ValueError(f"No JSON documents found in {corpus_path}")
        documents = []
        seen_sources: set[str] = set()
        for file in files:
            document = json.loads(file.read_text(encoding="utf-8"))
            required = {"source_id", "incident_id", "document_type", "timestamp", "title", "content"}
            if not required.issubset(document) or not all(isinstance(document[key], str) and document[key].strip() for key in required):
                raise ValueError(f"Invalid or missing document fields in {file}")
            source_id = document["source_id"]
            incident_id = document["incident_id"].upper()
            if source_id in seen_sources or not INCIDENT_ID_PATTERN.fullmatch(incident_id):
                raise ValueError(f"Duplicate source ID or invalid incident ID in {file}")
            if document["document_type"] not in DOCUMENT_TYPES:
                raise ValueError(f"Invalid document type in {file}")
            seen_sources.add(source_id)
            documents.append(document)
        chunk_count = 0
        for document in documents:
            source_id = document["source_id"]
            chunks = chunk_text(document["content"])
            ids = [f"{source_id}:chunk-{i:03d}" for i in range(len(chunks))]
            metadata = {
                "source_id": source_id,
                "document_id": source_id,
                "incident_id": document["incident_id"].upper(),
                "document_type": document["document_type"],
                "timestamp": document["timestamp"],
                "title": document["title"],
            }
            existing = self.collection.get(where={"source_id": source_id}, include=[])["ids"]
            stale = set(existing) - set(ids)
            if stale:
                self.collection.delete(ids=sorted(stale))
            self.collection.upsert(ids=ids, documents=chunks,
                                   embeddings=embed_texts(chunks),
                                   metadatas=[metadata.copy() for _ in ids])
            chunk_count += len(ids)
        return len(documents), chunk_count

    def retrieve(self, query: str, top_k: int = 5, min_similarity: float | None = None) -> list[RetrievedEvidence]:
        """Return cited evidence, optionally filtered by incident and similarity.

        Explicit incident IDs constrain the search so neighboring incidents do not
        masquerade as evidence for a named incident. A missing ID returns no hits.
        """
        if top_k < 1:
            raise ValueError("top_k must be positive")
        if min_similarity is not None and not -1 <= min_similarity <= 1:
            raise ValueError("min_similarity must be in [-1, 1]")
        incident_ids = {match.upper() for match in INCIDENT_ID_PATTERN.findall(query)}
        if len(incident_ids) > 1:
            raise ValueError("Search one incident ID at a time")
        where = {"incident_id": next(iter(incident_ids))} if incident_ids else None
        count = self.collection.count()
        if count == 0:
            return []
        if where and not self.collection.get(where=where, limit=1, include=[])["ids"]:
            return []
        result = self.collection.query(
            query_embeddings=[embed_query(query)], n_results=min(top_k, count),
            where=where, include=["documents", "metadatas", "distances"],
        )
        evidence = []
        for chunk_id, text, metadata, distance in zip(
            result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
        ):
            score = 1.0 - float(distance)
            if min_similarity is None or score >= min_similarity:
                evidence.append(RetrievedEvidence(
                    document_id=metadata["document_id"], chunk_id=chunk_id,
                    text=text, similarity_score=score, metadata=metadata,
                ))
        return evidence


def ingest_corpus(corpus_path: str | Path = "corpus", chroma_path: str | Path | None = None) -> tuple[int, int]:
    return IncidentRetriever(chroma_path).ingest(corpus_path)


def retrieve(query: str, top_k: int = 5, min_similarity: float | None = None,
             chroma_path: str | Path | None = None) -> list[RetrievedEvidence]:
    return IncidentRetriever(chroma_path).retrieve(query, top_k, min_similarity)
