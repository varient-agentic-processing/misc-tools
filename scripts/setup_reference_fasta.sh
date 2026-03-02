#!/usr/bin/env bash
#
# Download GRCh38 reference FASTA (GIAB-curated, with decoy sequences), generate
# .fai index for bcftools, and upload both to GCS reference/ prefix.
#
# Requires: curl, samtools (samtools faidx), gcloud (gsutil). Auto-installs samtools via brew if missing (macOS).
# Run after gcs-bucket-layout (bucket and reference/ prefix must exist).
#
set -euo pipefail

PROJECT_ID="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
BUCKET_SUFFIX=""
WORK_DIR="${WORK_DIR:-./reference-download}"
DRY_RUN=false

# GIAB-curated GRCh38 with decoy sequences (reduces mapping artefacts)
FASTA_URL="https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/references/GRCh38/GCA_000001405.15_GRCh38_no_alt_analysis_set.fasta.gz"
FASTA_NAME="GCA_000001405.15_GRCh38_no_alt_analysis_set.fasta.gz"

usage() {
  cat <<EOF
Usage: $0 -s SUFFIX [OPTIONS]

Download GRCh38 reference FASTA from GIAB, generate .fai index (samtools faidx),
and upload to GCS. Required for bcftools indel left-alignment in Phase 3.

Run after gcs-bucket-layout. Requires: curl, samtools, gcloud/gsutil.

Options:
  -s, --suffix SUFFIX  Required. Bucket is gs://genomic-variant-prototype-SUFFIX
  -p, --project ID     GCP project ID (default: from gcloud config)
  -w, --work-dir DIR   Local directory for download (default: ./reference-download)
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
    -w|--work-dir)
      WORK_DIR="$2"
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
  echo "Error: -s/--suffix is required (same suffix used for gcs-bucket-layout)" >&2
  usage >&2
  exit 1
fi

if [[ -z "${PROJECT_ID:-}" ]]; then
  echo "Error: No project ID. Set GCP_PROJECT, use -p/--project, or run 'gcloud config set project PROJECT_ID'" >&2
  exit 1
fi

BUCKET="genomic-variant-prototype-${BUCKET_SUFFIX}"
GCS_REF="gs://${BUCKET}/reference"

echo "Project:   $PROJECT_ID"
echo "Bucket:    gs://$BUCKET"
echo "Work dir:  $WORK_DIR"
[[ "$DRY_RUN" == "true" ]] && echo "(dry-run mode)"
echo ""

# 1. Download FASTA
mkdir -p "$WORK_DIR"
FASTA_PATH="$WORK_DIR/$FASTA_NAME"

if [[ -f "$FASTA_PATH" ]]; then
  echo "FASTA already exists: $FASTA_PATH (skipping download)"
else
  echo "Downloading GRCh38 reference from GIAB..."
  run curl -L -o "$FASTA_PATH" "$FASTA_URL"
fi

# 2. Generate .fai index (samtools faidx)
FAI_PATH="${FASTA_PATH}.fai"
if [[ -f "$FAI_PATH" ]]; then
  echo ""
  echo "Index already exists: $FAI_PATH (skipping samtools faidx)"
else
  echo ""
  echo "Generating FASTA index (samtools faidx)..."
  if ! command -v samtools &>/dev/null; then
    if command -v brew &>/dev/null; then
      echo "samtools not found. Installing via brew..."
      run brew install samtools
    else
      echo "Error: samtools required. Install via: brew install samtools (macOS) or conda install -c bioconda samtools" >&2
      exit 1
    fi
  fi
  run samtools faidx "$FASTA_PATH"
fi

# 3. Upload to GCS
echo ""
echo "Uploading to $GCS_REF/..."
run gsutil cp "$FASTA_PATH" "$GCS_REF/"
run gsutil cp "$FAI_PATH" "$GCS_REF/"

# samtools faidx on .gz also creates .gzi if needed
GZI_PATH="${FASTA_PATH}.gzi"
if [[ -f "$GZI_PATH" ]]; then
  echo "Uploading .gzi index..."
  run gsutil cp "$GZI_PATH" "$GCS_REF/"
fi

echo ""
echo "Done. Reference available at:"
echo "  $GCS_REF/$FASTA_NAME"
echo "  $GCS_REF/$FASTA_NAME.fai"
