"""Streamlit chat interface for IncidentIQ."""

from uuid import uuid4

import httpx
import streamlit as st

from incidentiq.config import Settings
from incidentiq.schemas import IncidentRequest, IncidentResponse


def _ask(api_url: str, request: IncidentRequest) -> IncidentResponse:
    with httpx.Client(timeout=120.0) as client:
        key = Settings().INCIDENTIQ_API_KEY
        headers = {"X-IncidentIQ-Key": key} if key else {}
        response = client.post(f"{api_url.rstrip('/')}/ask", json=request.model_dump(), headers=headers)
        response.raise_for_status()
        return IncidentResponse.model_validate(response.json())


def main() -> None:
    st.set_page_config(page_title="IncidentIQ", page_icon="🔎")
    st.title("IncidentIQ")
    st.caption("Ask about an incident and review the supporting evidence.")
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid4())
    if "history" not in st.session_state:
        st.session_state.history = []

    with st.sidebar:
        st.subheader("Conversation")
        st.code(st.session_state.thread_id, language=None)
        if st.button("New conversation"):
            st.session_state.thread_id = str(uuid4())
            st.session_state.history = []
            st.rerun()

    for entry in st.session_state.history:
        with st.chat_message("user"):
            st.write(entry["question"])
        with st.chat_message("assistant"):
            st.write(entry["response"]["answer"])
            _details(entry["response"])

    question = st.chat_input("Ask an incident question")
    if not question:
        return
    try:
        request = IncidentRequest(question=question, thread_id=st.session_state.thread_id)
        with st.spinner("Analyzing incident…"):
            response = _ask(Settings().API_URL, request)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 503:
            st.error("Incident analysis is currently unavailable. Please try again later.")
        elif exc.response.status_code == 422:
            st.error("The question or conversation ID is invalid. Please revise the question or start a new conversation.")
        else:
            st.error(f"The API returned an error ({exc.response.status_code}). Please try again.")
        return
    except (httpx.RequestError, ValueError):
        st.error("Could not reach IncidentIQ or read its response. Please check the API connection.")
        return

    st.session_state.history.append({"question": question, "response": response.model_dump()})
    st.rerun()


def _details(response: dict) -> None:
    citations = response["citations"]
    st.caption("Sources: " + (", ".join(citations) if citations else "None"))
    with st.expander("Analysis details"):
        st.write(f"Specialist route: {response['specialist_route']}")
        st.write(f"Model provider: {response['provider']}")
        st.write(f"Response latency: {response['latency_ms']:.0f} ms")
        if response["abstained"]:
            st.info("The assistant could not provide a supported answer.")


if __name__ == "__main__":
    main()
