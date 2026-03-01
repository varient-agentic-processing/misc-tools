#!/usr/bin/env python3
"""
Download all .hard-filtered.vcf.gz files from the 1000 Genomes DRAGEN S3 path.
Uses anonymous access (no-sign-request) for the public bucket.
"""
import os
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config

# S3 path: s3://1000genomes-dragen/data/dragen-3.7.6/hg38-graph-based/
BUCKET = "1000genomes-dragen"
PREFIX = "data/dragen-3.7.6/hg38-graph-based/"
SUFFIX = ".hard-filtered.vcf.gz"
# Number of top-level directories under the prefix to process
NUM_DIRECTORIES = 10


def get_s3_client():
    """S3 client with no signing (anonymous access for public bucket)."""
    return boto3.client(
        "s3",
        config=Config(signature_version=UNSIGNED),
        region_name="us-east-1",
    )


def list_top_level_directories(client):
    """List up to NUM_DIRECTORIES top-level 'directories' under PREFIX."""
    paginator = client.get_paginator("list_objects_v2")
    seen = set()
    dirs = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX, Delimiter="/"):
        for prefix in page.get("CommonPrefixes", []):
            d = prefix["Prefix"]
            if d not in seen:
                seen.add(d)
                dirs.append(d)
                if len(dirs) >= NUM_DIRECTORIES:
                    return dirs
    return dirs


def find_hard_filtered_vcf_keys(client, max_dirs):
    """Find all object keys ending with .hard-filtered.vcf.gz under up to max_dirs top-level directories."""
    paginator = client.get_paginator("list_objects_v2")
    # First get the top-level directories
    dirs = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX, Delimiter="/"):
        for prefix in page.get("CommonPrefixes", []):
            dirs.append(prefix["Prefix"])
            if len(dirs) >= max_dirs:
                break
        if len(dirs) >= max_dirs:
            break

    if not dirs:
        # No common prefixes; list all objects under PREFIX
        dirs = [PREFIX]

    keys = []
    for dir_prefix in dirs:
        for page in paginator.paginate(Bucket=BUCKET, Prefix=dir_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(SUFFIX):
                    keys.append(key)
    return keys


def download_file(client, key: str, local_dir: Path):
    """Download a single S3 object to local_dir, preserving path structure."""
    local_path = local_dir / key
    local_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {key} -> {local_path}")
    client.download_file(BUCKET, key, str(local_path))


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Download .hard-filtered.vcf.gz files from 1000 Genomes DRAGEN S3 (public, no-sign-request)."
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("downloads"),
        help="Local directory to save files (default: downloads)",
    )
    parser.add_argument(
        "-n",
        "--max-dirs",
        type=int,
        default=NUM_DIRECTORIES,
        help=f"Max top-level directories to scan (default: {NUM_DIRECTORIES})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list matching keys, do not download",
    )
    args = parser.parse_args()

    client = get_s3_client()
    print(f"Listing objects under s3://{BUCKET}/{PREFIX} (first {args.max_dirs} directories)...")
    keys = find_hard_filtered_vcf_keys(client, args.max_dirs)
    print(f"Found {len(keys)} files ending with {SUFFIX}")

    if not keys:
        print("No matching files found.")
        return

    if args.dry_run:
        for k in keys:
            print(k)
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    skipped = 0
    downloaded = 0
    for key in keys:
        local_path = args.output_dir / key
        if local_path.exists():
            skipped += 1
            print(f"Skipping (already exists) {key}")
        else:
            downloaded += 1
            download_file(client, key, args.output_dir)
    print(f"Done. Skipped {skipped} existing, downloaded {downloaded} new. Saved under {args.output_dir.absolute()}")


if __name__ == "__main__":
    main()
