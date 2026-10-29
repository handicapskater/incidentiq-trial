# Cloud Run deployment

IncidentIQ deploys two public Cloud Run services in project `handicapskater-gcp`, region `us-central1`: `incidentiq-trial-api` and `incidentiq-trial-ui`. The API calls `gemini-3.5-flash-lite` through Vertex AI at the `global` location using its service account. The local GGUF and llama.cpp container are not deployed.

## Prerequisites

Billing must be enabled. Enable `run.googleapis.com`, `cloudbuild.googleapis.com`, `artifactregistry.googleapis.com`, `aiplatform.googleapis.com`, and `iam.googleapis.com`. Authenticate with `gcloud`, select the project, and create a dedicated API identity:

```sh
gcloud config set project handicapskater-gcp
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com iam.googleapis.com --project handicapskater-gcp
gcloud iam service-accounts create incidentiq-trial-api --project handicapskater-gcp --display-name 'IncidentIQ trial API'
gcloud projects add-iam-policy-binding handicapskater-gcp --member 'serviceAccount:incidentiq-trial-api@handicapskater-gcp.iam.gserviceaccount.com' --role roles/aiplatform.user --condition=None
```

The service account was created and granted `roles/aiplatform.user` on 2026-10-29. Existing resources need not be recreated. The deployer must be permitted to deploy Cloud Run services and attach this identity.

## Build and deploy

From a clean `main` branch, run:

```sh
./scripts/deploy_cloud_run.sh --deploy-integrated-main
```

The script creates the `incidentiq` Artifact Registry repository if needed, builds `linux/amd64` API and UI images with Cloud Build, deploys the API with its service account, then deploys the UI with `API_URL` set to the API service URL. It prints both URLs. `Dockerfile.cloud` installs CPU-only PyTorch and bakes the retrieval assets; the local Compose API keeps its own Dockerfile. The UI has a separate small image. Cloud Build excludes `.env`, local model files, credentials, and local databases via `.gcloudignore`.

The API image downloads and caches all-MiniLM-L6-v2 and ingests the 20 bundled synthetic documents into 31 Chroma chunks at build time. New Cloud Run instances start with this immutable baseline index. The image sets Hugging Face offline mode at runtime so requests do not depend on a model download. API capacity is 2 CPU, 4 GiB memory, concurrency 1, maximum one instance, and a 300-second request timeout. The UI uses 1 CPU and 1 GiB memory.

## HTTP verification

Retrieve the URLs and test them after deploy:

```sh
API_URL=$(gcloud run services describe incidentiq-trial-api --region us-central1 --project handicapskater-gcp --format='value(status.url)')
UI_URL=$(gcloud run services describe incidentiq-trial-ui --region us-central1 --project handicapskater-gcp --format='value(status.url)')
curl -f "$API_URL/health"
curl -f "$API_URL/ready"
curl -f -H 'Content-Type: application/json' -d '{"question":"What was the final root cause of INC-1042?","thread_id":"cloud-smoke-1042"}' "$API_URL/ask"
curl -f "$UI_URL/_stcore/health"
```

Also open `UI_URL` in a browser and submit a question through its public form. Check the answer, specialist route, provider `gemini`, and a citation containing `INC-1042-POSTMORTEM`.

For a repeatable 19-case Vertex evaluation with the unchanged reference chunks and local Chroma index, run from an authenticated workstation:

```sh
MODEL_PROVIDER=gemini GEMINI_MODEL=gemini-3.5-flash-lite VERTEX_LOCATION=global .venv/bin/python -m verification.run_vertex_evaluation
```

This measures the Vertex model and graph, not the Cloud Run HTTP path. The cloud service should also be tested over HTTP with the production corpus.

## Persistence limits

Cloud Run container storage is ephemeral. The baked Chroma index is restored from the image at each cold start; updates to it during a running instance are lost when that instance stops. The LangGraph `MemorySaver` checkpointer holds threads only in one process. Thread memory disappears on restart, scale-down, or replacement and is not shared across instances. The one-instance setting reduces cross-instance inconsistency but does **not** make memory durable. Production persistence requires an external vector store and external checkpointer before accepting durable data.
