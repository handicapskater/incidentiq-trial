"""Low-latency intent routing for the three incident specialists.

This bounded classifier handles common paraphrases and negation without
adding a model call to every question.
"""

import re
from typing import Literal

Specialist = Literal["investigator", "planner", "communicator"]

_PLAN = re.compile(
    r"\b(?:plan|prevention|prevent|recommend|recommendation|remediat\w*|"
    r"avoid recurrence|avoid.{0,40}happening again|keep.{0,40}from happening again|"
    r"stop.{0,40}from happening again|reduce future|action items?|next steps?|"
    r"how (?:can|should|do) we (?:avoid|stop|keep|prevent|improve))\b",
    re.IGNORECASE,
)
_COMMUNICATE = re.compile(
    r"\b(?:customer impact|customers? affected|stakeholder\w*|status update|public update|"
    r"communicat\w*|explain to customers?|tell customers?|tell (?:the )?(?:users?|leadership)|"
    r"summari[sz]e for (?:customers?|stakeholders?|leadership)|user-facing|customer-facing)\b",
    re.IGNORECASE,
)
_NEGATED = re.compile(
    r"\b(?:do not|don't|not|no|without|rather than|instead of)\s+"
    r"(?:(?:a|an|the)\s+)?(?:prevention\s+plan|customer\s+update|status\s+update|"
    r"plan|prevention|prevent|recommendation|communicat\w*|customer\s+impact)\b",
    re.IGNORECASE,
)
_QUOTED = re.compile(r'"[^"\n]*"|“[^”\n]*”|\'[^\'\n]*\'')


def select_specialist(question: str) -> Specialist:
    """Select the first positive requested intent, independent of incident IDs."""
    intent = _NEGATED.sub(" ", _QUOTED.sub(" ", question))
    plan = _PLAN.search(intent)
    communication = _COMMUNICATE.search(intent)
    if plan and communication:
        return "planner" if plan.start() < communication.start() else "communicator"
    if plan:
        return "planner"
    if communication:
        return "communicator"
    return "investigator"
