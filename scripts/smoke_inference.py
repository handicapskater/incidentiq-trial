"""Optional live inference check, separate from cheap /health and /ready probes."""

import argparse
import os
from uuid import uuid4

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.getenv("API_URL", "http://localhost:8000"))
    parser.add_argument("--question", required=True)
    args = parser.parse_args()
    key = os.getenv("INCIDENTIQ_API_KEY", "")
    headers = {"X-IncidentIQ-Key": key} if key else {}
    with httpx.Client(timeout=120) as client:
        response = client.post(
            f"{args.api_url.rstrip('/')}/ask", headers=headers,
            json={"question": args.question, "thread_id": f"smoke-{uuid4()}"},
        )
        response.raise_for_status()
    result = response.json()
    print(f"HTTP {response.status_code}; provider={result['provider']}; route={result['specialist_route']}")
    print(f"Citations: {', '.join(result['citations']) or 'none'}")
    print(result["answer"])


if __name__ == "__main__":
    main()
