FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY incidentiq ./incidentiq
COPY evaluation ./evaluation
COPY corpus ./corpus
COPY scripts ./scripts
COPY tests/ ./tests/

FROM base AS api
ENV HF_HOME=/app/model-cache \
    CHROMA_PATH=/app/data/chroma \
    DATA_DIR=/app/data \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=2
RUN python scripts/ingest.py --corpus /app/corpus --chroma-path /app/data/chroma
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn incidentiq.api:app --host 0.0.0.0 --port ${PORT:-8000}"]

FROM base AS ui
ENV PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true
EXPOSE 8501
CMD ["sh", "-c", "exec streamlit run incidentiq/ui.py --server.address 0.0.0.0 --server.port ${PORT:-8501}"]
