#!/usr/bin/env python3
"""
Download GIAB HG002 v4.2.1 benchmark VCF from NIST FTP and upload to GCS.

Source: NIST GIAB Ashkenazim Trio (HG002) NISTv4.2.1 GRCh38:
  ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/
  HG002_NA24385_son/NISTv4.2.1/GRCh38/

Files: HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz, .tbi, and
  HG002_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed

Destination: gs://genomic-variant-prototype-{suffix}/raw/vcf/giab/
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from ftplib import FTP
from pathlib import Path

FTP_HOST = "ftp-trace.ncbi.nlm.nih.gov"
FTP_PATH = (
    "ReferenceSamples/giab/release/AshkenazimTrio/"
    "HG002_NA24385_son/NISTv4.2.1/GRCh38"
)
FILES = [
    "HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz",
    "HG002_GRCh38_1_22_v4.2.1_benchmark.vcf.gz.tbi",
    "HG002_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed",
]
# Timeout for FTP operations (seconds); benchmark VCF is large
FTP_TIMEOUT = 3600


def download_file(
    ftp: FTP,
    remote_name: str,
    local_path: Path,
    dry_run: bool = False,
) -> bool:
    """Download a single file from FTP to local_path. Returns True on success."""
    if dry_run:
        print(f"[dry-run] Would download {remote_name} -> {local_path}")
        return True
    local_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {remote_name} -> {local_path}")
    try:
        with open(local_path, "wb") as f:
            ftp.retrbinary(f"RETR {remote_name}", f.write)
        return True
    except Exception as e:
        print(f"Failed to download {remote_name}: {e}", file=sys.stderr)
        return False


def upload_to_gcs(
    local_path: Path,
    gcs_uri: str,
    dry_run: bool = False,
) -> bool:
    """Upload file to GCS via gsutil."""
    if dry_run:
        print(f"[dry-run] gsutil cp {local_path} {gcs_uri}")
        return True
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download GIAB HG002 v4.2.1 benchmark VCF from NIST FTP and upload to GCS."
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
        default=Path("giab-hg002-benchmark"),
        help="Local directory for downloads (default: giab-hg002-benchmark)",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Only download locally, do not upload to GCS",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Print actions without executing",
    )
    args = parser.parse_args()

    bucket = f"genomic-variant-prototype-{args.suffix}"
    gcs_prefix = f"gs://{bucket}/raw/vcf/giab"

    print(f"Source: ftp://{FTP_HOST}/{FTP_PATH}/")
    print(f"Files:  {', '.join(FILES)}")
    print(f"Dest:   {gcs_prefix}/")
    print()

    if args.dry_run:
        print("[dry-run] Would download and upload the following:")
        for f in FILES:
            print(f"  {f}")
        return

    args.work_dir.mkdir(parents=True, exist_ok=True)

    # Download from FTP (skip if already present)
    ftp = FTP(timeout=FTP_TIMEOUT)
    try:
        ftp.connect(FTP_HOST)
        ftp.login()
        ftp.cwd(FTP_PATH)
    except Exception as e:
        print(f"FTP connection failed: {e}", file=sys.stderr)
        sys.exit(1)

    downloaded = 0
    for name in FILES:
        local_path = args.work_dir / name
        if local_path.exists():
            print(f"Skipping (already exists) {name}")
            downloaded += 1
            continue
        if download_file(ftp, name, local_path, args.dry_run):
            downloaded += 1
    try:
        ftp.quit()
    except Exception:
        pass

    print(f"\nDownloaded {downloaded}/{len(FILES)} files to {args.work_dir.absolute()}")

    if args.no_upload:
        print("Skipping GCS upload (--no-upload)")
        return

    # Verify bucket access
    check = subprocess.run(
        ["gsutil", "ls", f"gs://{bucket}/"],
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        print(f"Cannot access gs://{bucket}/. Ensure:", file=sys.stderr)
        print("  1. gcloud auth login (or gcloud auth application-default login)", file=sys.stderr)
        print("  2. Bucket exists (run gcs-bucket-layout first)", file=sys.stderr)
        if check.stderr:
            print(check.stderr, file=sys.stderr)
        sys.exit(1)

    print("\nUploading to GCS...")
    for name in FILES:
        local_path = args.work_dir / name
        if not local_path.exists():
            print(f"  {name}: skipped (not downloaded)", file=sys.stderr)
            continue
        if upload_to_gcs(local_path, f"{gcs_prefix}/{name}", args.dry_run):
            print(f"  {name}: uploaded")

    print("\nDone.")


if __name__ == "__main__":
    main()
