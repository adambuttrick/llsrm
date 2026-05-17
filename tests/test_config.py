import pytest
import yaml
from pathlib import Path
from ror_matcher.config import load_config


@pytest.fixture
def tmp_config(tmp_path):
    def _write(yaml_str):
        p = tmp_path / "config.yaml"
        p.write_text(yaml_str)
        return p
    return _write


def test_load_minimal_csv_config(tmp_config):
    path = tmp_config("""
input:
  file: "data/records.csv"
  format: csv
  id_field: doi
  affiliation_fields:
    - institution
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
output:
  file: "results/enriched.csv"
  format: csv
""")
    config = load_config(path)
    assert config.input.format == "csv"
    assert config.input.id_field == "doi"
    assert len(config.input.affiliation_fields) == 1
    assert config.input.affiliation_fields[0].field_name == "institution"
    assert config.query.endpoint == "single_search"
    assert config.query.concurrency == 50
    assert config.output.ror_id_field == "ror_id"
    assert config.working_dir == ".ror_matcher"


def test_load_config_with_path_syntax(tmp_config):
    path = tmp_config("""
input:
  file: "data/records.jsonl"
  format: jsonl
  id_field: id
  affiliation_fields:
    - path: attributes.creators[].affiliation[].name
query:
  base_url: "https://api.ror.org"
  endpoint: multisearch
output:
  file: "results/enriched.jsonl"
  format: jsonl
""")
    config = load_config(path)
    af = config.input.affiliation_fields[0]
    assert af.path == "attributes.creators[].affiliation[].name"
    assert af.field_name == "attributes.creators[].affiliation[].name"


def test_load_config_with_output_name_override(tmp_config):
    path = tmp_config("""
input:
  file: "data/records.csv"
  format: csv
  id_field: doi
  affiliation_fields:
    - field: institution
      output_name: inst_ror
    - field: department
      output_name: dept_ror
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
output:
  file: "out.csv"
  format: csv
""")
    config = load_config(path)
    assert config.input.affiliation_fields[0].output_name == "inst_ror"
    assert config.input.affiliation_fields[1].output_name == "dept_ror"


def test_load_config_multiple_simple_fields(tmp_config):
    path = tmp_config("""
input:
  file: "data/records.csv"
  format: csv
  id_field: doi
  affiliation_fields:
    - institution
    - department
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
output:
  file: "out.csv"
  format: csv
""")
    config = load_config(path)
    assert len(config.input.affiliation_fields) == 2
    assert config.input.affiliation_fields[0].field_name == "institution"
    assert config.input.affiliation_fields[1].field_name == "department"


def test_load_config_invalid_format(tmp_config):
    path = tmp_config("""
input:
  file: "data/records.xml"
  format: xml
  id_field: doi
  affiliation_fields:
    - institution
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
output:
  file: "out.csv"
  format: csv
""")
    with pytest.raises(ValueError, match="format"):
        load_config(path)


def test_load_config_invalid_endpoint(tmp_config):
    path = tmp_config("""
input:
  file: "data/records.csv"
  format: csv
  id_field: doi
  affiliation_fields:
    - institution
query:
  base_url: "https://api.ror.org"
  endpoint: fuzzy_search
output:
  file: "out.csv"
  format: csv
""")
    with pytest.raises(ValueError, match="endpoint"):
        load_config(path)


def test_load_config_missing_required_field(tmp_config):
    path = tmp_config("""
input:
  file: "data/records.csv"
  format: csv
  affiliation_fields:
    - institution
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
output:
  file: "out.csv"
  format: csv
""")
    with pytest.raises((ValueError, KeyError)):
        load_config(path)


def test_load_config_with_delimiter(tmp_config):
    path = tmp_config("""
input:
  file: "data/records.csv"
  format: csv
  id_field: doi
  affiliation_fields:
    - Name
    - field: "alt_name"
      delimiter: " | "
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
output:
  file: "out.csv"
  format: csv
""")
    config = load_config(path)
    assert config.input.affiliation_fields[0].delimiter is None
    assert config.input.affiliation_fields[1].delimiter == " | "
    assert config.input.affiliation_fields[1].field_name == "alt_name"


def test_load_config_delimiter_on_path_field(tmp_config):
    path = tmp_config("""
input:
  file: "data/records.jsonl"
  format: jsonl
  id_field: id
  affiliation_fields:
    - path: attributes.names[].value
      delimiter: " | "
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
output:
  file: "out.jsonl"
  format: jsonl
""")
    config = load_config(path)
    af = config.input.affiliation_fields[0]
    assert af.path == "attributes.names[].value"
    assert af.delimiter == " | "


def test_load_config_marple_source_defaults(tmp_config):
    path = tmp_config("""
input:
  file: "data/records.csv"
  format: csv
  id_field: doi
  affiliation_fields:
    - institution
query:
  source: marple
output:
  file: "out.csv"
  format: csv
""")
    config = load_config(path)
    assert config.query.source == "marple"
    assert config.query.base_url == "http://localhost:8000"
    assert config.query.task == "affiliation"
    assert config.query.strategy == "affiliation-single-search"
    assert config.query.endpoint is None


def test_load_config_marple_source_overrides(tmp_config):
    path = tmp_config("""
input:
  file: "data/records.csv"
  format: csv
  id_field: doi
  affiliation_fields:
    - institution
query:
  source: marple
  base_url: "http://marple.example:9000"
  task: affiliation
  strategy: affiliation-multi-search
output:
  file: "out.csv"
  format: csv
""")
    config = load_config(path)
    assert config.query.base_url == "http://marple.example:9000"
    assert config.query.strategy == "affiliation-multi-search"


def test_load_config_invalid_source(tmp_config):
    path = tmp_config("""
input:
  file: "data/records.csv"
  format: csv
  id_field: doi
  affiliation_fields:
    - institution
query:
  source: openalex
  base_url: "http://localhost:8000"
output:
  file: "out.csv"
  format: csv
""")
    with pytest.raises(ValueError, match="source"):
        load_config(path)


def test_load_config_plain_string_has_no_delimiter(tmp_config):
    path = tmp_config("""
input:
  file: "data/records.csv"
  format: csv
  id_field: doi
  affiliation_fields:
    - institution
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
output:
  file: "out.csv"
  format: csv
""")
    config = load_config(path)
    assert config.input.affiliation_fields[0].delimiter is None
