#!/usr/bin/env python3
"""
Download ClinVar VCF, index, and variant_summary from NCBI FTP; upload to GCS.

Source: ftp.ncbi.nlm.nih.gov
  - pub/clinvar/vcf_GRCh38/clinvar.vcf.gz, clinvar.vcf.gz.tbi
  - pub/clinvar/tab_delimited/variant_summary.txt.gz

Destination: gs://genomic-variant-prototype-{suffix}/raw/clinvar/

Logs the ClinVar release date from the VCF header to logs/clinvar_version.txt
(local) and uploads it as raw/clinvar/clinvar_version.txt in the bucket
(annotation version pin).
"""
from __future__ import annotations

import argparse
import gzip
import re
import subprocess
import sys
from ftplib import FTP
from pathlib import Path

FTP_HOST = "ftp.ncbi.nlm.nih.gov"
# (directory, filename) for each file
FTP_FILES = [
    ("pub/clinvar/vcf_GRCh38", "clinvar.vcf.gz"),
    ("pub/clinvar/vcf_GRCh38", "clinvar.vcf.gz.tbi"),
    ("pub/clinvar/tab_delimited", "variant_summary.txt.gz"),
]
FTP_TIMEOUT = 3600

# VCF header line that carries release date (VCF 4.x ##fileDate=YYYYMMDD)
FILEDATE_RE = re.compile(r"^##fileDate=(\S+)", re.IGNORECASE)


def get_clinvar_release_date(vcf_gz_path: Path) -> str | None:
    """Read gzipped VCF header and return release date (##fileDate=) if present."""
    try:
        with gzip.open(vcf_gz_path, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.startswith("##"):
                    break
                m = FILEDATE_RE.match(line.strip())
                if m:
                    return m.group(1).strip()
    except Exception:
        pass
    return None


def download_file(
    ftp: FTP,
    remote_dir: str,
    remote_name: str,
    local_path: Path,
    dry_run: bool = False,
) -> bool:
    """Download a single file from FTP (after cwd to remote_dir) to local_path."""
    if dry_run:
        print(f"[dry-run] Would download {remote_dir}/{remote_name} -> {local_path}")
        return True
    local_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {remote_dir}/{remote_name} -> {local_path}")
    try:
        # Ensure we're at root then cwd to target (works whether server uses / or not)
        try:
            ftp.cwd("/")
        except Exception:
            pass
        ftp.cwd(remote_dir)
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
        description="Download ClinVar VCF and variant_summary from NCBI FTP, log release date, upload to GCS."
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
        default=Path("clinvar-download"),
        help="Local directory for downloads (default: clinvar-download)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("logs/clinvar_version.txt"),
        help="Path to write ClinVar release date (default: logs/clinvar_version.txt)",
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
    gcs_prefix = f"gs://{bucket}/raw/clinvar"

    print(f"Source: ftp://{FTP_HOST}/ (vcf_GRCh38/ + tab_delimited/)")
    print(f"Files:  clinvar.vcf.gz, clinvar.vcf.gz.tbi, variant_summary.txt.gz")
    print(f"Dest:   {gcs_prefix}/")
    print(f"Log:    {args.log_file} (release date from VCF header)")
    print()

    if args.dry_run:
        print("[dry-run] Would download, log release date, and upload.")
        return

    args.work_dir.mkdir(parents=True, exist_ok=True)

    ftp = FTP(timeout=FTP_TIMEOUT)
    try:
        ftp.connect(FTP_HOST)
        ftp.login()
    except Exception as e:
        print(f"FTP connection failed: {e}", file=sys.stderr)
        sys.exit(1)

    downloaded = 0
    for remote_dir, name in FTP_FILES:
        local_path = args.work_dir / name
        if local_path.exists():
            print(f"Skipping (already exists) {name}")
            downloaded += 1
            continue
        if download_file(ftp, remote_dir, name, local_path, args.dry_run):
            downloaded += 1
    try:
        ftp.quit()
    except Exception:
        pass

    print(f"\nDownloaded {downloaded}/{len(FTP_FILES)} files to {args.work_dir.absolute()}")

    # Log ClinVar release date from VCF header
    vcf_path = args.work_dir / "clinvar.vcf.gz"
    if vcf_path.exists():
        release_date = get_clinvar_release_date(vcf_path)
        if release_date:
            args.log_file.parent.mkdir(parents=True, exist_ok=True)
            args.log_file.write_text(f"ClinVar release date (##fileDate): {release_date}\n")
            print(f"Logged release date to {args.log_file}: {release_date}")
        else:
            print("Could not find ##fileDate in VCF header; not writing log.", file=sys.stderr)
    else:
        print("VCF not present; skipping release date log.", file=sys.stderr)

    if args.no_upload:
        print("Skipping GCS upload (--no-upload)")
        return

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
    for _remote_dir, name in FTP_FILES:
        local_path = args.work_dir / name
        if not local_path.exists():
            print(f"  {name}: skipped (not downloaded)", file=sys.stderr)
            continue
        if upload_to_gcs(local_path, f"{gcs_prefix}/{name}", args.dry_run):
            print(f"  {name}: uploaded")

    # Upload version pin to bucket so pipelines can reference it
    if args.log_file.exists():
        if upload_to_gcs(
            args.log_file,
            f"{gcs_prefix}/clinvar_version.txt",
            args.dry_run,
        ):
            print(f"  clinvar_version.txt: uploaded")

    print("\nDone.")


if __name__ == "__main__":
    main()
