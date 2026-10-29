# IncidentIQ trial

IncidentIQ answers questions about a synthetic incident corpus with FastAPI, a LangGraph supervisor that selects Investigator, Planner, or Communicator, Chroma retrieval, all-MiniLM-L6-v2 embeddings, and llama.cpp. Streamlit provides the UI. GCP deployment has not been performed.

## Local setup

Requires Python 3.11 and Docker. Set `GGUF_MODEL_PATH` to an existing nonempty host GGUF file; the path in `.env.example` was verified on the original host.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
docker compose up -d --build
docker compose exec -T api python scripts/ingest.py
curl http://localhost:8000/ready
```

`/health` checks the API process. `/ready` checks the compiled graph, nonempty Chroma collection, and configured model service. The UI is at `http://localhost:8501`. The Docker llama.cpp service uses a 4096-token context and one slot to fit local memory. Its image reports no accelerator device on this Mac; a full incident request exceeded the API's 120-second timeout. A tiny Docker prompt measured 7.38 prompt tokens/s and 3.27 generated tokens/s, so a roughly 1700-token evidence prompt exceeds that timeout during prompt processing alone. Health does not imply acceptable CPU inference latency.

For faster local inference on Apple Silicon with Metal-enabled llama.cpp, use two terminals:

```sh
GGUF_MODEL_PATH=/path/to/model.gguf
llama-server -m "$GGUF_MODEL_PATH" --host 127.0.0.1 --port 8082 --ctx-size 4096 --parallel 1 --gpu-layers 99
```

```sh
LLAMA_URL=http://127.0.0.1:8082 .venv/bin/uvicorn incidentiq.api:app --host 127.0.0.1 --port 8001
```

The measured evaluation used port 8082 and the same GGUF file as Docker. Host llama.cpp reported Apple M1 Max Metal and averaged 1.22 seconds per evaluation case; that result does not represent Docker CPU performance.

The graph exposes only `incident_retrieval` as a tool. Shell, arbitrary file, and network tools are not registered; model output requesting a tool is rejected. Citation validation checks returned chunk IDs against retrieved evidence.

## Verification

```sh
.venv/bin/python -m pytest -q
LLAMA_URL=http://127.0.0.1:8082 .venv/bin/python -m verification.run_live_evaluation
```

The evaluator writes responses to `verification/live_evaluation_predictions.jsonl` and metrics to `verification/live_evaluation_report.json`. It indexes the unchanged `evaluation/reference_chunks.json` into a separate local Chroma index. See `RUBRIC.md` for results and remaining gaps.
