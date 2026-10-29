#!/usr/bin/env bash
set -euo pipefail

# Deploy only from an integrated, clean main branch after an explicit invocation.
if [[ "${1:-}" != "--deploy-integrated-main" ]]; then
  echo "Usage: $0 --deploy-integrated-main" >&2
  exit 2
fi
if [[ "$(git branch --show-current)" != "main" ]] || [[ -n "$(git status --porcelain)" ]]; then
  echo "Deployment requires a clean integrated main branch." >&2
  exit 2
fi

for command in gcloud git; do
  command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 2; }
done

project="${GCP_PROJECT:-handicapskater-gcp}"
region="${GCP_LOCATION:-us-central1}"
vertex_location="${VERTEX_LOCATION:-global}"
gemini_model="${GEMINI_MODEL:-gemini-3.5-flash-lite}"
repository="${ARTIFACT_REPOSITORY:-incidentiq}"
service_account="${API_SERVICE_ACCOUNT:-incidentiq-trial-api@${project}.iam.gserviceaccount.com}"
image_base="${region}-docker.pkg.dev/${project}/${repository}"
revision="$(git rev-parse --short=12 HEAD)"
api_image="${image_base}/api:${revision}"
ui_image="${image_base}/ui:${revision}"

gcloud config set project "$project"
gcloud iam service-accounts describe "$service_account" --project "$project" >/dev/null
if ! gcloud artifacts repositories describe "$repository" --project "$project" --location "$region" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$repository" --project "$project" --location "$region" \
    --repository-format docker --description "IncidentIQ trial images"
fi
gcloud builds submit . --project "$project" --config cloudbuild.yaml \
  --substitutions "_REGION=${region},_REPOSITORY=${repository},_TAG=${revision}"

gcloud run deploy incidentiq-trial-api \
  --project "$project" --region "$region" --platform managed \
  --image "$api_image" --port 8000 --service-account "$service_account" \
  --memory 4Gi --cpu 2 --concurrency 1 --max-instances 1 --timeout 300 \
  --set-env-vars "MODEL_PROVIDER=gemini,GCP_PROJECT=${project},GCP_LOCATION=${region},VERTEX_LOCATION=${vertex_location},GEMINI_MODEL=${gemini_model},CHROMA_PATH=/app/data/chroma,DATA_DIR=/app/data,GIT_COMMIT_SHA=${revision}" \
  --allow-unauthenticated

api_url="$(gcloud run services describe incidentiq-trial-api --project "$project" --region "$region" --format 'value(status.url)')"
gcloud run deploy incidentiq-trial-ui \
  --project "$project" --region "$region" --platform managed \
  --image "$ui_image" --port 8501 --memory 1Gi --cpu 1 \
  --set-env-vars "API_URL=${api_url}" \
  --allow-unauthenticated

ui_url="$(gcloud run services describe incidentiq-trial-ui --project "$project" --region "$region" --format 'value(status.url)')"
echo "API: ${api_url}"
echo "UI: ${ui_url}"
echo "Images tagged from commit ${revision}. Verify /health, /ready, /ask, and the public UI over HTTP."
