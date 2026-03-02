#!/usr/bin/env bash
#
# Create the prototype GCS bucket and folder structure for the genomic variant pipeline.
# Run after create_gcp_service_accounts.sh (service accounts need to exist for IAM).
#
# Creates:
#   - Bucket gs://genomic-variant-prototype-[suffix]
#   - Folder structure (raw/vcf, raw/clinvar, staging/normalised, staging/annotated, logs, reference)
#   - Versioning enabled
#   - Lifecycle rule: delete staging/ objects after 30 days
#
set -euo pipefail

PROJECT_ID="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
BUCKET_SUFFIX=""
LOCATION="us-central1"
DRY_RUN=false

usage() {
  cat <<EOF
Usage: $0 -s SUFFIX [OPTIONS]

Create the prototype GCS bucket and folder layout for the genomic variant pipeline.
Run after gcp-service-accounts (service accounts must exist first).

Options:
  -s, --suffix SUFFIX  Required. Bucket will be gs://genomic-variant-prototype-SUFFIX
  -p, --project ID     GCP project ID (default: from gcloud config)
  -l, --location LOC   Bucket location (default: us-central1)
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
    -s|--suffix)
      BUCKET_SUFFIX="$2"
      shift 2
      ;;
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

if [[ -z "${BUCKET_SUFFIX:-}" ]]; then
  echo "Error: -s/--suffix is required (e.g. your-project or dev-2024)" >&2
  usage >&2
  exit 1
fi

if [[ -z "${PROJECT_ID:-}" ]]; then
  echo "Error: No project ID. Set GCP_PROJECT, use -p/--project, or run 'gcloud config set project PROJECT_ID'" >&2
  exit 1
fi

BUCKET="genomic-variant-prototype-${BUCKET_SUFFIX}"
BUCKET_URI="gs://${BUCKET}"

echo "Project: $PROJECT_ID"
echo "Bucket:  $BUCKET_URI"
echo "Location: $LOCATION"
[[ "$DRY_RUN" == "true" ]] && echo "(dry-run mode)"
echo ""

# 1. Create bucket
echo "Creating bucket..."
run gcloud storage buckets create "$BUCKET_URI" \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --uniform-bucket-level-access

# 2. Enable versioning
echo ""
echo "Enabling versioning..."
run gcloud storage buckets update "$BUCKET_URI" \
  --project="$PROJECT_ID" \
  --versioning

# 3. Create folder structure (placeholder objects)
echo ""
echo "Creating folder structure..."
PREFIXES=(
  "raw/vcf"           # incoming VCFs from 1000 Genomes
  "raw/clinvar"       # ClinVar VCF and TSV from NCBI
  "staging/normalised" # bcftools-normalised VCFs
  "staging/annotated"  # ClinVar-annotated VCFs
  "logs"               # pipeline run logs
  "reference"          # GRCh38 reference FASTA
)

KEEP_TEMP=$(mktemp)
LIFECYCLE_FILE=$(mktemp)
trap 'rm -f "$KEEP_TEMP" "$LIFECYCLE_FILE"' EXIT
: > "$KEEP_TEMP"

for prefix in "${PREFIXES[@]}"; do
  echo "  $prefix/"
  run gcloud storage cp "$KEEP_TEMP" "${BUCKET_URI}/${prefix}/.keep"
done

# 4. Lifecycle rule: delete staging/ after 30 days
echo ""
echo "Setting lifecycle rule (delete staging/ after 30 days)..."
cat > "$LIFECYCLE_FILE" <<'LIFECYCLE'
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {
        "age": 30,
        "matchesPrefix": ["staging/"]
      }
    }
  ]
}
LIFECYCLE

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[dry-run] gcloud storage buckets update $BUCKET_URI --lifecycle-file=..."
  cat "$LIFECYCLE_FILE"
else
  run gcloud storage buckets update "$BUCKET_URI" \
    --project="$PROJECT_ID" \
    --lifecycle-file="$LIFECYCLE_FILE"
fi

echo ""
echo "Done. Bucket layout:"
echo "  $BUCKET_URI/"
echo "    raw/vcf/         ← incoming VCFs from 1000 Genomes"
echo "    raw/clinvar/     ← ClinVar VCF and TSV from NCBI"
echo "    staging/normalised/  ← bcftools-normalised VCFs"
echo "    staging/annotated/   ← ClinVar-annotated VCFs"
echo "    logs/             ← pipeline run logs"
echo "    reference/        ← GRCh38 reference FASTA"
