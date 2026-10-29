"""Evaluate Gemini on Vertex AI using the local CLI identity and reference index."""

import subprocess
from functools import lru_cache

from incidentiq import inference
from verification.run_live_evaluation import main


@lru_cache(maxsize=1)
def _cli_token() -> str:
    return subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()


if __name__ == "__main__":
    inference.vertex_access_token = _cli_token
    main(prefix="vertex_evaluation")
