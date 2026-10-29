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

for command in gcloud docker git; do
  command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; exit 2; }
done

project="${GCP_PROJECT:-handicapskater-gcp}"
region="${GCP_LOCATION:-us-central1}"
repository="${ARTIFACT_REPOSITORY:-incidentiq}"
image_base="${region}-docker.pkg.dev/${project}/${repository}"
revision="$(git rev-parse --short=12 HEAD)"
api_image="${image_base}/api:${revision}"
ui_image="${image_base}/ui:${revision}"

gcloud config set project "$project"
gcloud auth configure-docker "${region}-docker.pkg.dev" --quiet
docker build --target api -t "$api_image" .
docker build --target ui -t "$ui_image" .
docker push "$api_image"
docker push "$ui_image"

gcloud run deploy incidentiq-trial-api \
  --project "$project" --region "$region" --platform managed \
  --image "$api_image" --port 8000 \
  --set-env-vars "MODEL_PROVIDER=gemini,GCP_PROJECT=${project},GCP_LOCATION=${region},GEMINI_MODEL=${GEMINI_MODEL:-gemini-2.5-flash},CHROMA_PATH=/app/data/chroma,DATA_DIR=/app/data" \
  --allow-unauthenticated

api_url="$(gcloud run services describe incidentiq-trial-api --project "$project" --region "$region" --format 'value(status.url)')"
gcloud run deploy incidentiq-trial-ui \
  --project "$project" --region "$region" --platform managed \
  --image "$ui_image" --port 8501 \
  --set-env-vars "API_URL=${api_url}" \
  --allow-unauthenticated

echo "Deployed API and UI at revision ${revision}."
