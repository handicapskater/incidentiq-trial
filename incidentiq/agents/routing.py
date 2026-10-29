"""Deterministic intent routing for the three incident specialists."""

import re
from typing import Literal

Specialist = Literal["investigator", "planner", "communicator"]

_PLAN = re.compile(
    r"\b(?:plan|prevention|prevent|recommend|recommendation|reduce future|avoid recurrence|action items?)\b",
    re.IGNORECASE,
)
_COMMUNICATE = re.compile(
    r"\b(?:customer impact|customers? affected|stakeholder|status update|public update|"
    r"communicat(?:e|ion)|explain to customers?|user-facing)\b",
    re.IGNORECASE,
)


def select_specialist(question: str) -> Specialist:
    """Select by requested task, independent of incident or evaluation IDs."""
    if _PLAN.search(question):
        return "planner"
    if _COMMUNICATE.search(question):
        return "communicator"
    return "investigator"
