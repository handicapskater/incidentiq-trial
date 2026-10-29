"""Calibrated relevance checks using the unchanged synthetic corpus."""

from pathlib import Path

from incidentiq.retrieval import IncidentRetriever, evidence_is_sufficient


def test_relevance_gate_keeps_incidents_and_rejects_unrelated_queries(tmp_path):
    retriever = IncidentRetriever(tmp_path / "chroma")
    retriever.ingest(Path(__file__).resolve().parents[1] / "corpus")
    for question in (
        "What was the root cause of INC-1042?",
        "How should we prevent a repeat of INC-1044?",
        "Payment API connection pool root cause",
        "Which incident involved an expired certificate?",
    ):
        assert evidence_is_sufficient(question, retriever.retrieve(question)), question
    for question in (
        "What is the payroll account password?",
        "What is the payroll account password for INC-1042?",
        "What is the weather in Tokyo?",
        "Which incident will happen next month?",
        "What was the root cause of INC-9999?",
    ):
        assert not evidence_is_sufficient(question, retriever.retrieve(question)), question
