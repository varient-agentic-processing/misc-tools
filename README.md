# misc-tools

Miscellaneous tools for the project that don’t need their own repo. Managed with [Poetry](https://python-poetry.org/) for dependencies and [Poe the Poet](https://poethepoet.readthedocs.io/) for running tasks.

## Setup

- **Install Poetry** (if needed): <https://python-poetry.org/docs/#installation>
- **Install dependencies and create the env:**

  ```bash
  poetry install
  ```

  This installs the project dependencies and the dev dependency `poe`.

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

| Task / script | Description |
|---------------|-------------|
| `download-vcf` | Download `.hard-filtered.vcf.gz` files from 1000 Genomes DRAGEN S3 (public bucket). |
