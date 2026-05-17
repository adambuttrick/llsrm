# Local Large-Scale ROR Matching (LLSRM)

Batch reconciliation of affiliation strings against a local [ROR API](https://github.com/ror-community/ror-api) instance. Extracts affiliations from CSV/JSON/JSONL files, queries them concurrently, and writes enriched output with matched ROR IDs.

**Not intended for use with the production ROR API.** The production endpoint at `api.ror.org` is rate-limited to 2000 requests per 5 minutes, and individual users may be throttled further during periods of heavy traffic. This tool is designed for large-scale local reconciliation and will easily exceed those limits. Set up a local ROR API instance following the instructions at [ror-community/ror-api](https://github.com/ror-community/ror-api).

## Install

```bash
pip install -e .
```

## Usage

All commands take a `--config` flag pointing to a YAML config file.

```bash
# Run the full pipeline (extract -> query -> reconcile)
ror-matcher run --config config.yaml

# With automatic concurrency optimization
ror-matcher run --config config.yaml --optimize

# Resume a previously interrupted run
ror-matcher run --config config.yaml --resume

# Or run individual stages:
ror-matcher extract --config config.yaml
ror-matcher query --config config.yaml
ror-matcher query --config config.yaml --resume
ror-matcher reconcile --config config.yaml

# Find optimal concurrency for your local instance
ror-matcher optimize --config config.yaml
```

## Config

```yaml
input:
  file: data.csv
  format: csv              # csv | json | jsonl
  id_field: doi
  affiliation_fields:
    - institution           # simple field name
    - field: department     # with options
      delimiter: " | "
      output_name: dept_ror
    - path: authors[].affiliation[].name  # JSON path with array traversal

query:
  source: ror              # ror | marple (default: ror)
  base_url: http://localhost:9292
  endpoint: single_search  # ror only: single_search | multisearch
  timeout: 30
  concurrency: 50
  retries: 3
  retry_backoff: 2

output:
  file: enriched.csv
  format: csv
  ror_id_field: ror_id

working_dir: .ror_matcher
```

### Marple backend

To match against a local [Marple](https://github.com/crossref/marple) instance instead of the ROR API, set `source: marple`. Marple's affiliation task also returns ROR IDs, so output is unchanged.

```yaml
query:
  source: marple
  # base_url defaults to http://localhost:8000
  # task defaults to "affiliation"
  # strategy defaults to "affiliation-single-search"
  concurrency: 50
```

## Pipeline

```
Input file
  -> [extract]   -> unique_affiliations.json + provenance.jsonl
  -> [query]     -> ror_matches.jsonl + ror_failures.jsonl
  -> [reconcile] -> enriched output file
```

Intermediate files are stored in `working_dir` (default `.ror_matcher/`). The query stage writes a checkpoint file, so interrupted runs can be resumed with `--resume`.
