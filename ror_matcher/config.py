from pathlib import Path

import yaml

from .models import (
    AffiliationFieldConfig,
    Config,
    InputConfig,
    OutputConfig,
    QueryConfig,
)

VALID_FORMATS = {"csv", "json", "jsonl"}
VALID_ENDPOINTS = {"single_search", "multisearch"}
VALID_SOURCES = {"ror", "marple"}
MARPLE_DEFAULT_BASE_URL = "http://localhost:8000"


def _parse_affiliation_field(raw) -> AffiliationFieldConfig:
    if isinstance(raw, str):
        return AffiliationFieldConfig(field_name=raw)
    if isinstance(raw, dict):
        if "path" in raw:
            return AffiliationFieldConfig(
                field_name=raw["path"],
                path=raw["path"],
                output_name=raw.get("output_name"),
                delimiter=raw.get("delimiter"),
            )
        if "field" in raw:
            return AffiliationFieldConfig(
                field_name=raw["field"],
                output_name=raw.get("output_name"),
                delimiter=raw.get("delimiter"),
            )
    raise ValueError(f"Invalid affiliation field config: {raw}")


def load_config(path: str | Path) -> Config:
    with open(path) as f:
        raw = yaml.safe_load(f)

    inp = raw["input"]
    q = raw["query"]
    out = raw["output"]

    input_format = inp["format"]
    if input_format not in VALID_FORMATS:
        raise ValueError(f"Invalid input format: {input_format!r}. Must be one of {VALID_FORMATS}")

    output_format = out["format"]
    if output_format not in VALID_FORMATS:
        raise ValueError(f"Invalid output format: {output_format!r}. Must be one of {VALID_FORMATS}")

    source = q.get("source", "ror")
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid source: {source!r}. Must be one of {VALID_SOURCES}")

    if source == "ror":
        endpoint = q["endpoint"]
        if endpoint not in VALID_ENDPOINTS:
            raise ValueError(f"Invalid endpoint: {endpoint!r}. Must be one of {VALID_ENDPOINTS}")
        base_url = q["base_url"]
    else:
        endpoint = q.get("endpoint")
        base_url = q.get("base_url", MARPLE_DEFAULT_BASE_URL)

    affiliation_fields = [
        _parse_affiliation_field(af) for af in inp["affiliation_fields"]
    ]

    return Config(
        input=InputConfig(
            file=inp["file"],
            format=input_format,
            id_field=inp["id_field"],
            affiliation_fields=affiliation_fields,
        ),
        query=QueryConfig(
            base_url=base_url,
            endpoint=endpoint,
            source=source,
            task=q.get("task", "affiliation"),
            strategy=q.get("strategy", "affiliation-single-search"),
            timeout=q.get("timeout", 30),
            concurrency=q.get("concurrency", 50),
            retries=q.get("retries", 3),
            retry_backoff=q.get("retry_backoff", 2),
        ),
        output=OutputConfig(
            file=out["file"],
            format=output_format,
            ror_id_field=out.get("ror_id_field", "ror_id"),
        ),
        working_dir=raw.get("working_dir", ".ror_matcher"),
    )
