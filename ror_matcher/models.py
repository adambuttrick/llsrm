from dataclasses import dataclass

import xxhash


def hash_affiliation(affiliation: str) -> str:
    return xxhash.xxh3_64(affiliation.encode()).hexdigest()


@dataclass
class AffiliationFieldConfig:
    field_name: str
    path: str | None = None
    output_name: str | None = None
    delimiter: str | None = None


@dataclass
class InputConfig:
    file: str
    format: str
    id_field: str
    affiliation_fields: list[AffiliationFieldConfig]


@dataclass
class QueryConfig:
    base_url: str
    endpoint: str | None = None
    source: str = "ror"
    task: str = "affiliation"
    strategy: str = "affiliation-single-search"
    timeout: int = 30
    concurrency: int = 50
    retries: int = 3
    retry_backoff: int = 2


@dataclass
class OutputConfig:
    file: str
    format: str
    ror_id_field: str = "ror_id"


@dataclass
class Config:
    input: InputConfig
    query: QueryConfig
    output: OutputConfig
    working_dir: str = ".ror_matcher"


@dataclass
class ProvenanceRecord:
    record_id: str
    field: str
    affiliation: str
    affiliation_hash: str
    row_index: int
    path_indices: list[int] | None = None


@dataclass
class RorMatchRecord:
    affiliation: str
    affiliation_hash: str
    ror_id: str


@dataclass
class RorFailureRecord:
    affiliation: str
    affiliation_hash: str
    error: str
