#!/usr/bin/env python3
"""
Transfer 1000 Genomes DRAGEN hard-filtered VCFs from S3 to GCS.

Uses 25 individuals spanning all 5 superpopulations (EUR, AMR, AFR, SAS, EAS),
including GIAB HG002 for Phase 8 validation. Parallel downloads for efficiency.

Best run on a GCE VM for fastest S3↔GCS throughput (avoids routing through local).
Otherwise runs locally with parallel downloads.

Optional: bcftools stats verification, with output uploaded next to each VCF in raw/vcf/{sample_id}/
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config

# S3 path: s3://1000genomes-dragen/data/dragen-3.7.6/hg38-graph-based/
BUCKET = "1000genomes-dragen"
PREFIX = "data/dragen-3.7.6/hg38-graph-based/"
SUFFIX = ".hard-filtered.vcf.gz"

# 25 individuals spanning 5 superpopulations + GIAB HG002 (mandatory for Phase 8 validation)
# Format: (sample_id, superpopulation)
TARGET_INDIVIDUALS: list[tuple[str, str]] = [
    # EUR (5) — HG002 is GIAB Ashkenazi son, mandatory for validation
    ("HG00096", "EUR"),
    ("HG00097", "EUR"),
    ("HG00099", "EUR"),
    ("HG00101", "EUR"),
    ("HG002", "EUR"),  # GIAB — mandatory
    # AMR (5)
    ("HG01565", "AMR"),
    ("HG01566", "AMR"),
    ("HG01567", "AMR"),
    ("HG01572", "AMR"),
    ("HG01573", "AMR"),
    # AFR (5)
    ("HG01879", "AFR"),
    ("HG01880", "AFR"),
    ("HG01881", "AFR"),
    ("HG01882", "AFR"),
    ("HG01883", "AFR"),
    # SAS (5)
    ("HG00673", "SAS"),
    ("HG00674", "SAS"),
    ("HG00675", "SAS"),
    ("HG00731", "SAS"),
    ("HG00732", "SAS"),
    # EAS (5)
    ("HG00419", "EAS"),
    ("HG00420", "EAS"),
    ("HG00421", "EAS"),
    ("HG00422", "EAS"),
    ("HG00423", "EAS"),
]


def get_s3_client():
    """S3 client with anonymous access for public bucket."""
    return boto3.client(
        "s3",
        config=Config(signature_version=UNSIGNED),
        region_name="us-east-1",
    )


def find_vcf_key(client, sample_id: str) -> str | None:
    """Find S3 key for sample's hard-filtered VCF. Tries common patterns, then lists."""
    # Common pattern: PREFIX/sample_id/sample_id.hard-filtered.vcf.gz
    candidates = [
        f"{PREFIX}{sample_id}/{sample_id}{SUFFIX}",
        f"{PREFIX}{sample_id}/",
    ]
    for key in candidates:
        if key.endswith("/"):
            # List objects under prefix
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=BUCKET, Prefix=key, MaxKeys=10):
                for obj in page.get("Contents", []):
                    k = obj["Key"]
                    if k.endswith(SUFFIX):
                        return k
            continue
        try:
            client.head_object(Bucket=BUCKET, Key=key)
            return key
        except Exception:
            pass
    return None


def download_one(
    client,
    sample_id: str,
    local_dir: Path,
    include_tbi: bool = True,
) -> tuple[str, Path | None, Path | None, bool]:
    """Download VCF (and .tbi) for one sample. Skips download if VCF already exists locally.
    Returns (sample_id, vcf_path, tbi_path, skipped).
    """
    # Expected local path (we don't know key name until we look, but pattern is sample_id.hard-filtered.vcf.gz)
    vcf_path = local_dir / sample_id / f"{sample_id}{SUFFIX}"
    vcf_path.parent.mkdir(parents=True, exist_ok=True)

    # Skip download if VCF already exists (re-runs only upload, no S3 calls)
    if vcf_path.exists():
        tbi_path = vcf_path.with_suffix(vcf_path.suffix + ".tbi")
        return (sample_id, vcf_path, tbi_path if tbi_path.exists() else None, True)

    vcf_key = find_vcf_key(client, sample_id)
    if not vcf_key:
        return (sample_id, None, None, False)

    vcf_path = local_dir / sample_id / Path(vcf_key).name

    try:
        client.download_file(BUCKET, vcf_key, str(vcf_path))
    except Exception:
        return (sample_id, None, None, False)

    tbi_path = None
    if include_tbi:
        tbi_key = vcf_key + ".tbi"
        tbi_path = vcf_path.with_suffix(vcf_path.suffix + ".tbi")
        try:
            client.head_object(Bucket=BUCKET, Key=tbi_key)
            client.download_file(BUCKET, tbi_key, str(tbi_path))
        except Exception:
            tbi_path = None

    return (sample_id, vcf_path, tbi_path, False)


def upload_to_gcs(
    local_path: Path,
    gcs_uri: str,
    dry_run: bool = False,
) -> bool:
    """Upload file to GCS via gsutil."""
    if dry_run:
        print(f"[dry-run] gsutil cp {local_path} {gcs_uri}")
        return True
    # Use absolute path so gsutil works regardless of cwd
    abs_path = str(local_path.resolve())
    if not Path(abs_path).exists():
        print(f"File not found: {abs_path}", file=sys.stderr)
        return False
    result = subprocess.run(
        ["gsutil", "cp", abs_path, gcs_uri],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"gsutil failed for {local_path.name}:", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        return False
    return True


def run_bcftools_stats(vcf_path: Path, dry_run: bool = False) -> tuple[str | None, str | None]:
    """Run bcftools stats, return (stdout, error_message). stdout is None on failure."""
    if dry_run:
        return (f"[dry-run] bcftools stats {vcf_path}", None)
    try:
        result = subprocess.run(
            ["bcftools", "stats", str(vcf_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or f"exit code {result.returncode}").strip()
            return (None, err)
        return (result.stdout, None)
    except FileNotFoundError:
        return (None, "bcftools not found. Install with: brew install bcftools")
    except subprocess.TimeoutExpired:
        return (None, "bcftools stats timed out")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transfer 25 1000 Genomes DRAGEN VCFs (S3→GCS), spanning populations. "
        "Optional bcftools stats verification."
    )
    parser.add_argument(
        "-s",
        "--suffix",
        required=True,
        help="GCS bucket suffix (gs://genomic-variant-prototype-SUFFIX)",
    )
    parser.add_argument(
        "-o",
        "--work-dir",
        type=Path,
        default=Path("vcf-transfer"),
        help="Local directory for downloads (default: vcf-transfer)",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=8,
        help="Parallel download jobs (default: 8)",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Only download locally, do not upload to GCS",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run bcftools stats on each VCF and upload .bcftools_stats.txt next to the VCF in GCS",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only run bcftools stats and upload stats to GCS (no download, no VCF upload). Use after VCFs are already in work-dir.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without executing",
    )
    args = parser.parse_args()

    bucket = f"genomic-variant-prototype-{args.suffix}"
    gcs_raw = f"gs://{bucket}/raw/vcf"

    print(f"Target: {len(TARGET_INDIVIDUALS)} individuals across 5 superpopulations")
    print(f"  EUR: 5 (incl. HG002 GIAB), AMR: 5, AFR: 5, SAS: 5, EAS: 5")
    print(f"Source: s3://{BUCKET}/{PREFIX}")
    print(f"Dest:   {gcs_raw}/ (VCF, .tbi, and .bcftools_stats.txt per sample)")
    print()

    if args.dry_run:
        print("[dry-run] Would download and upload the following samples:")
        for sid, pop in TARGET_INDIVIDUALS:
            print(f"  {sid} ({pop})")
        return

    # --verify-only: run bcftools stats on local VCFs and upload stats only (no download, no VCF upload)
    if args.verify_only:
        args.work_dir.mkdir(parents=True, exist_ok=True)
        check = subprocess.run(
            ["gsutil", "ls", f"gs://{bucket}/"],
            capture_output=True,
            text=True,
        )
        if check.returncode != 0:
            print(f"Cannot access gs://{bucket}/. Run gcloud auth application-default login?", file=sys.stderr)
            if check.stderr:
                print(check.stderr, file=sys.stderr)
            sys.exit(1)
        print("Verify only: running bcftools stats on local VCFs, uploading to GCS...")
        verify_error_shown = False
        for sample_id, _ in TARGET_INDIVIDUALS:
            vcf_path = args.work_dir / sample_id / f"{sample_id}{SUFFIX}"
            if not vcf_path.exists():
                print(f"  {sample_id}: skipped (no local VCF)", file=sys.stderr)
                continue
            stats, err = run_bcftools_stats(vcf_path, args.dry_run)
            if stats:
                stats_path = args.work_dir / f"{sample_id}.bcftools_stats.txt"
                stats_path.write_text(stats)
                if upload_to_gcs(stats_path, f"{gcs_raw}/{sample_id}/{sample_id}.bcftools_stats.txt", args.dry_run):
                    print(f"  {sample_id}: stats uploaded")
            else:
                if not verify_error_shown and err:
                    print(f"  bcftools error: {err}", file=sys.stderr)
                    verify_error_shown = True
                print(f"  {sample_id}: bcftools stats failed", file=sys.stderr)
        print("\nDone.")
        return

    args.work_dir.mkdir(parents=True, exist_ok=True)
    client = get_s3_client()

    # Parallel downloads
    downloaded: list[tuple[str, Path | None, Path | None, bool]] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futures = {
            ex.submit(
                download_one,
                client,
                sample_id,
                args.work_dir,
                include_tbi=True,
            ): sample_id
            for sample_id, _ in TARGET_INDIVIDUALS
        }
        for fut in as_completed(futures):
            sample_id = futures[fut]
            try:
                res = fut.result()
                downloaded.append(res)
                sid, vcf, tbi, skipped = res
                if vcf:
                    print(f"Skipped {sid} (already exists)" if skipped else f"Downloaded {sid}")
                else:
                    print(f"Failed {sid}", file=sys.stderr)
            except Exception as e:
                print(f"Error {sample_id}: {e}", file=sys.stderr)

    ok = sum(1 for _, v, _, _ in downloaded if v is not None)
    print(f"\nDownloaded {ok}/{len(TARGET_INDIVIDUALS)} VCFs")

    if args.dry_run:
        return

    if args.no_upload:
        print("Skipping GCS upload (--no-upload)")
        return

    # Verify bucket access before uploading
    check = subprocess.run(
        ["gsutil", "ls", f"gs://{bucket}/"],
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        print(f"Cannot access gs://{bucket}/. Ensure:", file=sys.stderr)
        print("  1. gcloud auth login (or gcloud auth application-default login)", file=sys.stderr)
        print("  2. Bucket exists (run gcs-bucket-layout first)", file=sys.stderr)
        print("  3. Correct suffix (bucket is genomic-variant-prototype-{suffix})", file=sys.stderr)
        if check.stderr:
            print(check.stderr, file=sys.stderr)
        sys.exit(1)

    # Upload to GCS
    print("\nUploading to GCS...")
    for sample_id, vcf_path, tbi_path, _ in downloaded:
        if vcf_path is None:
            continue
        sample_prefix = f"{gcs_raw}/{sample_id}/"
        upload_to_gcs(vcf_path, f"{sample_prefix}{vcf_path.name}", args.dry_run)
        if tbi_path and tbi_path.exists():
            upload_to_gcs(tbi_path, f"{sample_prefix}{tbi_path.name}", args.dry_run)

    # Optional bcftools stats
    if args.verify:
        print("\nRunning bcftools stats...")
        verify_error_shown = False
        for sample_id, vcf_path, _, _ in downloaded:
            if vcf_path is None or not vcf_path.exists():
                continue
            stats, err = run_bcftools_stats(vcf_path, args.dry_run)
            if stats:
                stats_path = args.work_dir / f"{sample_id}.bcftools_stats.txt"
                stats_path.write_text(stats)
                upload_to_gcs(
                    stats_path,
                    f"{gcs_raw}/{sample_id}/{sample_id}.bcftools_stats.txt",
                    args.dry_run,
                )
                print(f"  {sample_id}: stats uploaded")
            else:
                if not verify_error_shown and err:
                    print(f"  bcftools error: {err}", file=sys.stderr)
                    verify_error_shown = True
                print(f"  {sample_id}: bcftools stats skipped (missing or failed)", file=sys.stderr)

    print("\nDone.")


if __name__ == "__main__":
    main()
