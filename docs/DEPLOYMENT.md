# Cloud Run deployment

IncidentIQ deploys two public Cloud Run services in project `handicapskater-gcp`, region `us-central1`: `incidentiq-trial-api` and `incidentiq-trial-ui`. The API calls `gemini-3.5-flash-lite` through Vertex AI at the `global` location using its service account. The local GGUF and llama.cpp container are not deployed.

## Verified deployment (2026-10-29)

| Service | Public URL | Ready revision |
| --- | --- | --- |
| FastAPI | https://incidentiq-trial-api-dpnhm5kswq-uc.a.run.app | `incidentiq-trial-api-00001-jzf` |
| Streamlit | https://incidentiq-trial-ui-dpnhm5kswq-uc.a.run.app | `incidentiq-trial-ui-00002-4fj` |

Both services reported Ready and 100% traffic on these revisions. Cloud Build `e0ab25ed-d6ad-41b6-92f0-c66845d03dbd` built the images from Git commit `6546d1d28b380b757c432c07f6bb5c044d850fcd`; the build log confirmed 20 documents and 31 Chroma chunks. The API service identity is `incidentiq-trial-api@handicapskater-gcp.iam.gserviceaccount.com` with `roles/aiplatform.user`.

The UI revision was updated on 2026-10-29 to set `PYTHONPATH=/app` because the prior image's Streamlit script could not import `incidentiq` from its script directory. The new UI revision retains its `API_URL` pointing to the Cloud Run API. The repository's `Dockerfile.ui` now embeds the package path and checks import during build. The UI revision still uses the original image digest; the environment update fixes the running configuration.

Actual public HTTP checks returned 200 for API `/health`, `/ready`, and `/ask`, plus UI `/` and `/_stcore/health`. The UI revision's `API_URL` points to the public API URL, which also returned 200 for `/ready`. The first live `/ask` call answered the final cause of INC-1042 using Vertex Gemini and cited `INC-1042-POSTMORTEM:chunk-000`; its reported latency was 39,020 ms during cold startup. A separate six-request Cloud Run HTTP smoke evaluation returned 6/6 HTTP 200, 5/5 expected specialist routes for supported questions, 5/5 expected postmortem citations, and correct abstention for an unsupported incident. The same-thread follow-up answered the INC-1042 recovery question. Five supported request wall times averaged 1,106 ms after warm-up; the first cold request is excluded from that warm figure. See `verification/cloud_http_report.json` for full responses and per-request timings. One exact keyword check in that smoke report flags the follow-up because it expects “rollback” while the correct answer says “rolled back”; this is a wording mismatch in the smoke check, not a changed evaluation case.

The unchanged 19-case reference evaluation was also run against Vertex Gemini with the local reference Chroma index: answer accuracy 19/19, retrieval accuracy 17/19, citation validity 19/19, semantic routing 19/19, abstention 19/19, memory 1/1, mean 946 ms, p95 1,588 ms, zero errors. See `verification/vertex_evaluation_report.json`. This 19-case run did **not** traverse Cloud Run. A graphical browser interaction with Streamlit could not be completed in this environment because the browser connection was unavailable; HTTP page and health checks and the configured API connection were verified.

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
