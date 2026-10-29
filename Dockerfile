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

FROM base AS api
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn incidentiq.api:app --host 0.0.0.0 --port ${PORT:-8000}"]

FROM base AS ui
ENV PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true
EXPOSE 8501
CMD ["sh", "-c", "exec streamlit run incidentiq/ui.py --server.address 0.0.0.0 --server.port ${PORT:-8501}"]
