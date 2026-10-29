FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY incidentiq ./incidentiq
COPY evaluation ./evaluation
COPY corpus ./corpus
COPY scripts ./scripts
COPY tests/ ./tests/

FROM base AS api
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn incidentiq.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
