#!/usr/bin/env bash
#
# Create firewall rules for ClickHouse VM access.
# Uses the default VPC (no custom VPC for prototype).
#
# Creates:
#   - allow-clickhouse: tcp 8123, 9000 (ClickHouse HTTP, native) from your workstation
#   - allow-ssh-prototype: tcp 22 (SSH) from your workstation
#
# Both rules target VMs with tag: clickhouse-server
#
set -euo pipefail

PROJECT_ID="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
SOURCE_IP="${SOURCE_IP:-}"  # From env, or set via -i
DRY_RUN=false

usage() {
  cat <<EOF
Usage: $0 -i IP [OPTIONS]

Create firewall rules for ClickHouse VM (SSH + ClickHouse ports).
Uses the default VPC. Rules restrict access to your workstation IP only.

Options:
  -i, --source-ip IP   Your workstation's public IP (required, or set SOURCE_IP env var)
  -p, --project ID     GCP project ID (default: from gcloud config)
  -n, --dry-run        Print commands without executing
  -h, --help           Show this help

To auto-detect your IP, run: curl -s ifconfig.me
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
    -i|--source-ip)
      SOURCE_IP="$2"
      shift 2
      ;;
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

if [[ -z "${SOURCE_IP:-}" ]]; then
  echo "Error: -i/--source-ip is required. Use your workstation's public IP (e.g. curl -s ifconfig.me)" >&2
  usage >&2
  exit 1
fi

# Ensure /32 CIDR
if [[ "$SOURCE_IP" != *"/"* ]]; then
  SOURCE_CIDR="${SOURCE_IP}/32"
else
  SOURCE_CIDR="$SOURCE_IP"
fi

if [[ -z "${PROJECT_ID:-}" ]]; then
  echo "Error: No project ID. Set GCP_PROJECT, use -p/--project, or run 'gcloud config set project PROJECT_ID'" >&2
  exit 1
fi

echo "Project:   $PROJECT_ID"
echo "Source IP: $SOURCE_CIDR (your workstation)"
echo "Target:    VMs with tag clickhouse-server"
[[ "$DRY_RUN" == "true" ]] && echo "(dry-run mode)"
echo ""

# 1. ClickHouse ports (8123 HTTP, 9000 native)
echo "Creating firewall rule allow-clickhouse (tcp:8123, tcp:9000)..."
run gcloud compute firewall-rules create allow-clickhouse \
  --project="$PROJECT_ID" \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:8123,tcp:9000 \
  --source-ranges="$SOURCE_CIDR" \
  --target-tags=clickhouse-server \
  --description="ClickHouse HTTP and native protocol from workstation" \
  || true  # idempotent: ignore if exists

# 2. SSH
echo ""
echo "Creating firewall rule allow-ssh-prototype (tcp:22)..."
run gcloud compute firewall-rules create allow-ssh-prototype \
  --project="$PROJECT_ID" \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:22 \
  --source-ranges="$SOURCE_CIDR" \
  --target-tags=clickhouse-server \
  --description="SSH from workstation for prototype" \
  || true  # idempotent: ignore if exists

echo ""
echo "Done. Ensure your ClickHouse VM has network tag: clickhouse-server"
