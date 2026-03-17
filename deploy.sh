#!/bin/bash
set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────
PROJECT_ID="snappy-cistern-490013-i4"
REGION="us-central1"
BACKEND_SERVICE="rag-backend"
FRONTEND_SERVICE="rag-frontend"

echo "=== Step 1: Set GCP project ==="
gcloud config set project "$PROJECT_ID"

echo ""
echo "=== Step 2: Enable required APIs ==="
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com

echo ""
echo "=== Step 3: Store secrets in Secret Manager ==="

# Read the Anthropic key from backend/.env
ANTHROPIC_KEY=$(grep '^ANTHROPIC_API_KEY=' backend/.env | cut -d'=' -f2)
if [ -z "$ANTHROPIC_KEY" ]; then
  echo "ERROR: ANTHROPIC_API_KEY not found in backend/.env"
  exit 1
fi

# Create or update the secret
if gcloud secrets describe anthropic-api-key --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "$ANTHROPIC_KEY" | gcloud secrets versions add anthropic-api-key --data-file=-
  echo "  Updated existing secret: anthropic-api-key"
else
  echo "$ANTHROPIC_KEY" | gcloud secrets create anthropic-api-key --data-file=- --replication-policy=automatic
  echo "  Created secret: anthropic-api-key"
fi

echo ""
echo "=== Step 4: Deploy backend to Cloud Run ==="
# Build from project root (Dockerfile references backend/ and data/)
gcloud run deploy "$BACKEND_SERVICE" \
  --source . \
  --dockerfile backend/Dockerfile \
  --region "$REGION" \
  --memory 2Gi \
  --cpu 1 \
  --timeout 300 \
  --set-env-vars "ANTHROPIC_MODEL=claude-sonnet-4-6,CHROMA_PERSIST_DIR=./db/chroma,PAPER_DATA_DIR=../data,GOLDEN_DATASET_PATH=../Golden Dataset _interview sample (1).xlsx,MAX_CONTEXT_CHUNKS=8,CHUNK_SIZE=800,CHUNK_OVERLAP=150,MAX_TOKENS=500" \
  --set-secrets "ANTHROPIC_API_KEY=anthropic-api-key:latest" \
  --allow-unauthenticated

BACKEND_URL=$(gcloud run services describe "$BACKEND_SERVICE" --region "$REGION" --format='value(status.url)')
echo ""
echo "  Backend deployed at: $BACKEND_URL"

echo ""
echo "=== Step 5: Update backend CORS with frontend origin ==="
# We'll set ALLOWED_ORIGINS after we know the frontend URL — update after frontend deploy

echo ""
echo "=== Step 6: Deploy frontend to Cloud Run ==="
cd frontend
gcloud run deploy "$FRONTEND_SERVICE" \
  --source . \
  --region "$REGION" \
  --memory 256Mi \
  --cpu 1 \
  --set-env-vars "BACKEND_URL=$BACKEND_URL" \
  --allow-unauthenticated
cd ..

FRONTEND_URL=$(gcloud run services describe "$FRONTEND_SERVICE" --region "$REGION" --format='value(status.url)')
echo ""
echo "  Frontend deployed at: $FRONTEND_URL"

echo ""
echo "=== Step 7: Update backend CORS to allow frontend origin ==="
gcloud run services update "$BACKEND_SERVICE" \
  --region "$REGION" \
  --update-env-vars "ALLOWED_ORIGINS=$FRONTEND_URL"

echo ""
echo "============================================="
echo "  Deployment complete!"
echo "  Frontend: $FRONTEND_URL"
echo "  Backend:  $BACKEND_URL"
echo "  Health:   $BACKEND_URL/api/health"
echo "============================================="
