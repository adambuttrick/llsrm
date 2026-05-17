import csv
import json
from pathlib import Path

import pytest

from ror_matcher.config import load_config
from ror_matcher.extract import run as run_extract
from ror_matcher.models import hash_affiliation


@pytest.fixture
def csv_input(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_file = data_dir / "records.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["doi", "institution", "department"])
        writer.writerow(["10.1234/abc", "University of Oxford", "Dept of Physics"])
        writer.writerow(["10.5678/def", "MIT", "Dept of Chemistry"])
        writer.writerow(["10.9999/ghi", "University of Oxford", "Dept of Math"])
    return csv_file


@pytest.fixture
def csv_config(tmp_path, csv_input):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"""
input:
  file: "{csv_input}"
  format: csv
  id_field: doi
  affiliation_fields:
    - institution
    - department
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
output:
  file: "{tmp_path}/out.csv"
  format: csv
working_dir: "{tmp_path / '.ror_matcher'}"
""")
    return load_config(config_file)


def test_extract_csv_creates_unique_affiliations(csv_config, tmp_path):
    run_extract(csv_config)
    working = Path(csv_config.working_dir)
    unique_path = working / "unique_affiliations.json"
    assert unique_path.exists()
    affiliations = json.loads(unique_path.read_text())
    assert isinstance(affiliations, list)
    assert set(affiliations) == {
        "University of Oxford", "MIT",
        "Dept of Physics", "Dept of Chemistry", "Dept of Math",
    }


def test_extract_csv_creates_provenance(csv_config, tmp_path):
    run_extract(csv_config)
    working = Path(csv_config.working_dir)
    prov_path = working / "provenance.jsonl"
    assert prov_path.exists()
    records = [json.loads(line) for line in prov_path.read_text().strip().split("\n")]
    # 3 rows x 2 fields = 6 provenance records
    assert len(records) == 6
    first = records[0]
    assert first["record_id"] == "10.1234/abc"
    assert first["field"] == "institution"
    assert first["affiliation"] == "University of Oxford"
    assert first["affiliation_hash"] == hash_affiliation("University of Oxford")
    assert first["row_index"] == 0


def test_extract_csv_skips_empty_affiliations(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_file = data_dir / "records.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["doi", "institution"])
        writer.writerow(["10.1234/abc", "MIT"])
        writer.writerow(["10.5678/def", ""])
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"""
input:
  file: "{csv_file}"
  format: csv
  id_field: doi
  affiliation_fields:
    - institution
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
output:
  file: "{tmp_path}/out.csv"
  format: csv
working_dir: "{tmp_path / '.ror_matcher'}"
""")
    config = load_config(config_file)
    run_extract(config)
    working = Path(config.working_dir)
    records = [json.loads(l) for l in (working / "provenance.jsonl").read_text().strip().split("\n")]
    assert len(records) == 1
    assert records[0]["affiliation"] == "MIT"


@pytest.fixture
def jsonl_input(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    jsonl_file = data_dir / "records.jsonl"
    records = [
        {"id": "10.1234/abc", "attributes": {"creators": [
            {"name": "Smith", "affiliation": [{"name": "University of Oxford"}, {"name": "Dept of Physics"}]},
        ]}},
        {"id": "10.5678/def", "attributes": {"creators": [
            {"name": "Jones", "affiliation": [{"name": "MIT"}]},
        ]}},
    ]
    with open(jsonl_file, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return jsonl_file


@pytest.fixture
def jsonl_config(tmp_path, jsonl_input):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"""
input:
  file: "{jsonl_input}"
  format: jsonl
  id_field: id
  affiliation_fields:
    - path: attributes.creators[].affiliation[].name
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
output:
  file: "{tmp_path}/out.jsonl"
  format: jsonl
working_dir: "{tmp_path / '.ror_matcher'}"
""")
    return load_config(config_file)


def test_extract_jsonl_creates_unique_affiliations(jsonl_config):
    run_extract(jsonl_config)
    working = Path(jsonl_config.working_dir)
    affiliations = json.loads((working / "unique_affiliations.json").read_text())
    assert set(affiliations) == {"University of Oxford", "Dept of Physics", "MIT"}


def test_extract_jsonl_creates_provenance_with_path_indices(jsonl_config):
    run_extract(jsonl_config)
    working = Path(jsonl_config.working_dir)
    records = [json.loads(l) for l in (working / "provenance.jsonl").read_text().strip().split("\n")]
    assert len(records) == 3
    assert records[0]["record_id"] == "10.1234/abc"
    assert records[0]["affiliation"] == "University of Oxford"
    assert records[0]["path_indices"] == [0, 0]
    assert records[0]["row_index"] == 0
    assert records[1]["path_indices"] == [0, 1]
    assert records[1]["affiliation"] == "Dept of Physics"


@pytest.fixture
def json_input(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    json_file = data_dir / "records.json"
    records = [
        {"id": "10.1234/abc", "institution": "MIT"},
        {"id": "10.5678/def", "institution": "Stanford University"},
    ]
    with open(json_file, "w") as f:
        json.dump(records, f)
    return json_file


@pytest.fixture
def json_config(tmp_path, json_input):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"""
input:
  file: "{json_input}"
  format: json
  id_field: id
  affiliation_fields:
    - institution
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
output:
  file: "{tmp_path}/out.json"
  format: json
working_dir: "{tmp_path / '.ror_matcher'}"
""")
    return load_config(config_file)


def test_extract_json_creates_unique_affiliations(json_config):
    run_extract(json_config)
    working = Path(json_config.working_dir)
    affiliations = json.loads((working / "unique_affiliations.json").read_text())
    assert set(affiliations) == {"MIT", "Stanford University"}


def test_extract_json_creates_provenance(json_config):
    run_extract(json_config)
    working = Path(json_config.working_dir)
    records = [json.loads(l) for l in (working / "provenance.jsonl").read_text().strip().split("\n")]
    assert len(records) == 2
    assert records[0]["record_id"] == "10.1234/abc"
    assert records[0]["affiliation"] == "MIT"
    assert records[0]["row_index"] == 0


def test_extract_csv_delimiter_splits_values(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_file = data_dir / "records.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "alt_names"])
        writer.writerow(["1", "MIT", "Massachusetts Institute of Technology | MIT"])
        writer.writerow(["2", "Oxford", "University of Oxford | Oxford Uni"])
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"""
input:
  file: "{csv_file}"
  format: csv
  id_field: id
  affiliation_fields:
    - name
    - field: alt_names
      delimiter: " | "
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
output:
  file: "{tmp_path}/out.csv"
  format: csv
working_dir: "{tmp_path / '.ror_matcher'}"
""")
    config = load_config(config_file)
    run_extract(config)
    working = Path(config.working_dir)
    affiliations = json.loads((working / "unique_affiliations.json").read_text())
    assert set(affiliations) == {
        "MIT", "Oxford",
        "Massachusetts Institute of Technology",
        "University of Oxford", "Oxford Uni",
    }
    records = [json.loads(l) for l in (working / "provenance.jsonl").read_text().strip().split("\n")]
    # 2 rows x (1 name + 2 alt_names each) = 6 provenance records
    assert len(records) == 6
    alt_records = [r for r in records if r["field"] == "alt_names"]
    assert len(alt_records) == 4
    assert alt_records[0]["affiliation"] == "Massachusetts Institute of Technology"
    assert alt_records[1]["affiliation"] == "MIT"


def test_extract_csv_delimiter_filters_empty_parts(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    csv_file = data_dir / "records.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "names"])
        writer.writerow(["1", "MIT |  | Stanford"])
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"""
input:
  file: "{csv_file}"
  format: csv
  id_field: id
  affiliation_fields:
    - field: names
      delimiter: " | "
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
output:
  file: "{tmp_path}/out.csv"
  format: csv
working_dir: "{tmp_path / '.ror_matcher'}"
""")
    config = load_config(config_file)
    run_extract(config)
    working = Path(config.working_dir)
    affiliations = json.loads((working / "unique_affiliations.json").read_text())
    assert set(affiliations) == {"MIT", "Stanford"}


def test_extract_json_flat_field_delimiter(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    json_file = data_dir / "records.json"
    records = [
        {"id": "1", "names": "MIT | Stanford"},
    ]
    with open(json_file, "w") as f:
        json.dump(records, f)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"""
input:
  file: "{json_file}"
  format: json
  id_field: id
  affiliation_fields:
    - field: names
      delimiter: " | "
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
output:
  file: "{tmp_path}/out.json"
  format: json
working_dir: "{tmp_path / '.ror_matcher'}"
""")
    config = load_config(config_file)
    run_extract(config)
    working = Path(config.working_dir)
    affiliations = json.loads((working / "unique_affiliations.json").read_text())
    assert set(affiliations) == {"MIT", "Stanford"}
