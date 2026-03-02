# misc-tools

Miscellaneous tools for the project that don’t need their own repo. Managed with [Poetry](https://python-poetry.org/) for dependencies and [Poe the Poet](https://poethepoet.readthedocs.io/) for running tasks.

## Setup

- **Install Poetry** (if needed): <https://python-poetry.org/docs/#installation>
- **Install dependencies and create the env:**

  ```bash
  poetry install
  ```

  This installs the project dependencies and the dev dependency `poe`.

- **Other requirements** (macOS with Homebrew):
  - **gcloud** — for GCP scripts: [Install the Google Cloud CLI](https://cloud.google.com/sdk/docs/install)
  - **samtools** — for `reference-fasta` (script can run `brew install samtools` if missing)
  - **bcftools** — for `transfer-1000g-vcf --verify` and `--verify-only`: `brew install bcftools`
  - **gsutil** — included with the Google Cloud CLI; used for GCS uploads

## Running tools

Use **Poe** so commands run inside the Poetry env. Either run `poe` via Poetry or activate the shell first:

```bash
# List tasks
poetry run poe
# or: poetry shell, then poe

# Run a task by name (examples)
poetry run poe download-vcf
poetry run poe download-vcf -- -o ./my-downloads -n 5 --dry-run
```

Anything after `--` is passed through to the underlying script (e.g. `-o`, `-n`, `--dry-run` for the VCF downloader).

You can also run a script directly with Poetry:

```bash
poetry run python src/import/download_hard_filtered_vcf.py --help
```

### GCP setup order

**Preferred order** for running the setup scripts (each step may depend on the previous):

| Step | Task | Command |
|------|------|---------|
| 1 | Service accounts | `poe gcp-service-accounts` (use `-- -p PROJECT -n` for dry-run) |
| 2 | GCS bucket layout | `poe gcs-bucket-layout -- -s SUFFIX` |
| 3 | Reference FASTA | `poe reference-fasta -- -s SUFFIX` |
| 4 | Firestore | `poe firestore-setup` |
| 5 | 1000G VCF transfer | `poe transfer-1000g-vcf -- -s SUFFIX --verify` |
| 6 | Artifact Registry | `poe artifact-registry` |
| 7 | Networking (firewall) | `poe networking -- -i WORKSTATION_IP` |

Replace `SUFFIX` with your bucket suffix (e.g. `my-project`), `PROJECT` with your GCP project ID, and `WORKSTATION_IP` with your public IP (`curl -s ifconfig.me`).

### Script arguments reference

| Task | Arguments |
|------|------------|
| **gcp-service-accounts** | `-p PROJECT` — GCP project (default: gcloud config). `-n` — dry-run. |
| **gcs-bucket-layout** | `-s SUFFIX` *(required)*. `-p PROJECT`, `-l LOCATION` (default: us-central1), `-n` (dry-run). |
| **reference-fasta** | `-s SUFFIX` *(required)*. `-p PROJECT`, `-w WORK_DIR` (default: ./reference-download), `-n` (dry-run). |
| **firestore-setup** | `-p PROJECT`, `-l LOCATION` (default: us-central1), `-n` (dry-run). |
| **transfer-1000g-vcf** | `-s SUFFIX` *(required)*. `-o WORK_DIR` (default: vcf-transfer), `-j JOBS` (default: 8), `--no-upload`, `--verify`, `--verify-only`, `-n` (dry-run). |
| **artifact-registry** | `-p PROJECT`, `-l LOCATION` (default: us-central1), `-n` (dry-run). |
| **networking** | `-i WORKSTATION_IP` *(required)* or `SOURCE_IP` env. `-p PROJECT`, `-n` (dry-run). |
| **clickhouse-status / start / stop** | `-i INSTANCE`, `-z ZONE`, `-p PROJECT` (optional; default: discover by tag clickhouse-server). |
| **vm-list** | `-p PROJECT` (optional). |
| **download-vcf** | `-o OUTPUT_DIR` (default: downloads), `-n MAX_DIRS` (max dirs to scan, default: 10), `--dry-run`. |

### ClickHouse VM management

After the ClickHouse VM is created (with tag `clickhouse-server`), use these to manage it:

| Task | Description |
|------|-------------|
| `clickhouse-status` | Show if the VM is running, its zone, and external IP (exit 1 if stopped) |
| `clickhouse-start` | Start the ClickHouse VM |
| `clickhouse-stop` | Stop the ClickHouse VM |
| `vm-list` | List all VMs in the project (name, zone, status, external IP) |

The script finds the VM by tag `clickhouse-server`. To specify explicitly: `poe clickhouse-status -- -i INSTANCE -z ZONE -p PROJECT`. Use `vm-list` to see all VMs (not ClickHouse-specific).

## Adding new tools

1. Add the script under `src/` (e.g. `src/import/` or another subdir).
2. Add any new library dependencies:

   ```bash
   poetry add <package>
   ```

3. Optionally add a Poe task in `pyproject.toml` under `[tool.poe.tasks]`:

   ```toml
   my-task = "python src/path/to/script.py"
   my-task.help = "Short description for poe"
   ```

   Then run it with `poe my-task` or `poe my-task -- --script-args`.

## Current tools

### GCP setup (run in order above)

| Task / script | Description |
|---------------|-------------|
| `gcp-service-accounts` | Create service accounts (ClickHouse, Pipeline, MCP Server) with IAM roles. Requires `gcloud`. Never creates JSON keys. |
| `gcs-bucket-layout` | Create GCS bucket and folder structure. **After gcp-service-accounts.** Requires `-s SUFFIX`. Optional: `-p`, `-l`, `-n`. |
| `reference-fasta` | Download GRCh38 reference (GIAB), generate .fai, upload to GCS. **After gcs-bucket-layout.** Requires `-s SUFFIX`. Optional: `-p`, `-w`, `-n`. Auto-installs samtools via brew if missing (macOS). |
| `firestore-setup` | Create Firestore database in Native mode. **After gcp-service-accounts.** Optional: `-p`, `-l`, `-n`. |
| `transfer-1000g-vcf` | Transfer 25 1000 Genomes VCFs (S3→GCS). **After gcs-bucket-layout.** Requires `-s SUFFIX`. Optional: `-o`, `-j`, `--no-upload`, `--verify` (bcftools stats next to each VCF), `--verify-only` (stats only, no download/upload). Skips re-download if local VCF exists. Best run on GCE VM. Requires `gsutil`, `bcftools` for verify. |
| `artifact-registry` | Create Artifact Registry Docker repository. **After gcp-service-accounts.** Optional: `-p`, `-l`, `-n`. |
| `networking` | Create firewall rules for ClickHouse VM. **After gcp-service-accounts.** Requires `-i WORKSTATION_IP`. Optional: `-p`, `-n`. |

### Other tools

| Task / script | Description |
|---------------|-------------|
| `download-vcf` | Download `.hard-filtered.vcf.gz` from 1000 Genomes DRAGEN S3 (public). Optional: `-o OUTPUT_DIR`, `-n MAX_DIRS`, `--dry-run`. |
| `clickhouse-status` | Show if ClickHouse VM is up (status, zone, external IP). Optional: `-i INSTANCE -z ZONE -p PROJECT` if not using tag. |
| `clickhouse-start` | Start the ClickHouse VM. Optional: `-i`, `-z`, `-p`. |
| `clickhouse-stop` | Stop the ClickHouse VM. Optional: `-i`, `-z`, `-p`. |
| `vm-list` | List all VMs in the project. Optional: `-p PROJECT`. |
