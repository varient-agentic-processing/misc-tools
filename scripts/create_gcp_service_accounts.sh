#!/usr/bin/env bash
#
# Create GCP service accounts for pipeline components.
# Limits blast radius if credentials are compromised; makes permissions auditable.
#
# Security: Never create or download service account JSON keys for the prototype.
# Use Workload Identity Federation or attach SAs directly to Compute Engine VMs
# and Cloud Run services. Key files are a security anti-pattern.
#
set -euo pipefail

PROJECT_ID="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
DRY_RUN=false

usage() {
  cat <<EOF
Usage: $0 [OPTIONS]

Create ClickHouse, Pipeline, and MCP Server service accounts with appropriate IAM roles.

Options:
  -p, --project ID    GCP project ID (default: from gcloud config)
  -n, --dry-run       Print commands without executing
  -h, --help          Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--project)
      PROJECT_ID="$2"
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

run() {
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

grant_role() {
  local sa=$1
  local role=$2
  run gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${sa}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="$role" \
    --quiet
}

echo "Project: $PROJECT_ID"
[[ "$DRY_RUN" == "true" ]] && echo "(dry-run mode)"

# 1. ClickHouse service account
echo ""
echo "Creating clickhouse-sa..."
run gcloud iam service-accounts create clickhouse-sa \
  --project="$PROJECT_ID" \
  --display-name="ClickHouse VM Service Account" \
  --description="Service account for ClickHouse VM" \
  || true  # idempotent: ignore if exists

for role in roles/storage.objectViewer roles/logging.logWriter roles/secretmanager.secretAccessor; do
  echo "  Granting $role"
  grant_role "clickhouse-sa" "$role"
done

# 2. Pipeline service account
echo ""
echo "Creating pipeline-sa..."
run gcloud iam service-accounts create pipeline-sa \
  --project="$PROJECT_ID" \
  --display-name="Pipeline Jobs Service Account" \
  --description="Service account for pipeline jobs" \
  || true

for role in roles/storage.objectAdmin roles/batch.jobsEditor roles/run.invoker roles/datastore.user roles/logging.logWriter roles/secretmanager.secretAccessor; do
  echo "  Granting $role"
  grant_role "pipeline-sa" "$role"
done

# 3. MCP Server service account
echo ""
echo "Creating mcp-server-sa..."
run gcloud iam service-accounts create mcp-server-sa \
  --project="$PROJECT_ID" \
  --display-name="MCP Server Service Account" \
  --description="Service account for MCP server" \
  || true

for role in roles/logging.logWriter roles/secretmanager.secretAccessor; do
  echo "  Granting $role"
  grant_role "mcp-server-sa" "$role"
done

echo ""
echo "Done. Service accounts created (or already existed)."
echo "Remember: Do NOT create or download JSON keys. Use Workload Identity or attach SAs to VMs/Cloud Run."
