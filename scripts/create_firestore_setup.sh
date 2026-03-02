#!/usr/bin/env bash
#
# Create Firestore database in Native mode for pipeline tracking.
# Run after gcp-service-accounts (pipeline-sa needs roles/datastore.user).
#
# Creates:
#   - Firestore database in Native mode, location us-central1, name (default)
#
# Planned pipeline tracking collection structure (created implicitly when first doc is written):
#   Collection: pipeline_runs
#     Document ID: {individual_id}_{run_id}
#     Fields: individual_id, run_id, stage, status, started_at, completed_at,
#             input_path, output_path, record_count, error_message
#
set -euo pipefail

PROJECT_ID="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
LOCATION="us-central1"
DATABASE="(default)"
DRY_RUN=false

usage() {
  cat <<EOF
Usage: $0 [OPTIONS]

Create Firestore database in Native mode for pipeline tracking.
Run after gcp-service-accounts (pipeline-sa needs datastore.user).

Options:
  -p, --project ID     GCP project ID (default: from gcloud config)
  -l, --location LOC   Database location (default: us-central1)
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

echo "Project:   $PROJECT_ID"
echo "Location:  $LOCATION"
echo "Database:  $DATABASE (Native mode)"
[[ "$DRY_RUN" == "true" ]] && echo "(dry-run mode)"
echo ""

# 1. Enable Firestore API (idempotent)
echo "Enabling Firestore API..."
run gcloud services enable firestore.googleapis.com --project="$PROJECT_ID"

# 2. Create Firestore database in Native mode
echo ""
echo "Creating Firestore database (Native mode)..."
run gcloud firestore databases create \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --database="$DATABASE" \
  --type=firestore-native \
  || true  # idempotent: ignore if already exists

echo ""
echo "Done. Firestore database ready."
echo ""
echo "Planned pipeline_runs collection structure (created when first document is written):"
echo "  Collection: pipeline_runs"
echo "    Document ID: {individual_id}_{run_id}"
echo "    Fields:"
echo "      individual_id, run_id, stage, status, started_at, completed_at,"
echo "      input_path, output_path, record_count, error_message"
