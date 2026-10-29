# IncidentIQ trial

Bootstrap for a four-agent incident response engineering exercise. Application code is pending.

## Local setup

Requires Python 3.11, Docker, and a local GGUF for llama.cpp. Create a virtual environment only if absent:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Set `GGUF_MODEL_PATH` to an existing nonempty host file before starting a model container. On this host, `/Users/troywilkes/rag/models/model.gguf` was verified during bootstrap. `/models/model.gguf` is valid inside a container only after Agent D defines and verifies a bind mount.

No application run command exists yet. See `docs/INTERFACES.md`, `ARCHITECTURE.md`, `RUBRIC.md`, and `AGENTS.md`.
