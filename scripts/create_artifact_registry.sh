#!/usr/bin/env bash
#
# Create Artifact Registry Docker repository for genomic pipeline images.
# Run after gcp-service-accounts.
#
# Creates:
#   - Docker repository: genomic-pipeline in us-central1
#
set -euo pipefail

PROJECT_ID="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REPOSITORY="genomic-pipeline"
LOCATION="us-central1"
DRY_RUN=false

usage() {
  cat <<EOF
Usage: $0 [OPTIONS]

Create Artifact Registry Docker repository for genomic pipeline images.
Run after gcp-service-accounts.

Options:
  -p, --project ID     GCP project ID (default: from gcloud config)
  -l, --location LOC   Repository location (default: us-central1)
  -n, --dry-run        Print commands without executing
  -h, --help           Show this help
EOF
}

run() {
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--project)
      PROJECT_ID="$2"
      shift 2
      ;;
    -l|--location)
      LOCATION="$2"
      shift 2
      ;;
    -n|--dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${PROJECT_ID:-}" ]]; then
  echo "Error: No project ID. Set GCP_PROJECT, use -p/--project, or run 'gcloud config set project PROJECT_ID'" >&2
  exit 1
fi

echo "Project:    $PROJECT_ID"
echo "Repository: $REPOSITORY"
echo "Location:   $LOCATION"
[[ "$DRY_RUN" == "true" ]] && echo "(dry-run mode)"
echo ""

# Enable Artifact Registry API (idempotent)
echo "Enabling Artifact Registry API..."
run gcloud services enable artifactregistry.googleapis.com --project="$PROJECT_ID"

# Create Docker repository
echo ""
echo "Creating Docker repository..."
run gcloud artifacts repositories create "$REPOSITORY" \
  --project="$PROJECT_ID" \
  --repository-format=docker \
  --location="$LOCATION" \
  --description="Genomic pipeline Docker images" \
  || true  # idempotent: ignore if already exists

echo ""
echo "Done. Push images to: $LOCATION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/<image>"
