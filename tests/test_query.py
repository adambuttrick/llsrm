import asyncio
import json
import re
from pathlib import Path

import pytest
from aioresponses import aioresponses

from ror_matcher.query import RorClient, MarpleClient, Checkpoint, run as run_query
from ror_matcher.config import load_config

ROR_API_PATTERN = re.compile(r"^https://api\.ror\.org/v2/organizations\?")
MARPLE_API_PATTERN = re.compile(r"^http://localhost:8000/match\?")


@pytest.fixture
def ror_response_chosen():
    return {
        "items": [
            {
                "chosen": True,
                "organization": {"id": "https://ror.org/052gg0110"},
            }
        ]
    }


@pytest.fixture
def ror_response_empty():
    return {"items": []}


@pytest.mark.asyncio
async def test_query_single_search_match(ror_response_chosen):
    with aioresponses() as m:
        m.get(
            ROR_API_PATTERN,
            payload=ror_response_chosen,
        )
        client = RorClient("https://api.ror.org", "single_search", timeout=5, retries=1)
        result = await client.query_affiliation("University of Oxford")
        assert result == "https://ror.org/052gg0110"


@pytest.mark.asyncio
async def test_query_multisearch_match(ror_response_chosen):
    with aioresponses() as m:
        m.get(
            ROR_API_PATTERN,
            payload=ror_response_chosen,
        )
        client = RorClient("https://api.ror.org", "multisearch", timeout=5, retries=1)
        result = await client.query_affiliation("University of Oxford")
        assert result == "https://ror.org/052gg0110"


@pytest.mark.asyncio
async def test_query_no_match_returns_none(ror_response_empty):
    with aioresponses() as m:
        m.get(
            ROR_API_PATTERN,
            payload=ror_response_empty,
        )
        client = RorClient("https://api.ror.org", "single_search", timeout=5, retries=1)
        result = await client.query_affiliation("Unknown Institution")
        assert result is None


@pytest.mark.asyncio
async def test_query_retries_on_500():
    with aioresponses() as m:
        m.get(ROR_API_PATTERN, status=500)
        m.get(
            ROR_API_PATTERN,
            payload={"items": [{"chosen": True, "organization": {"id": "https://ror.org/abc123"}}]},
        )
        client = RorClient("https://api.ror.org", "single_search", timeout=5, retries=3, retry_backoff=0)
        result = await client.query_affiliation("Test University")
        assert result == "https://ror.org/abc123"


@pytest.mark.asyncio
async def test_query_raises_on_4xx():
    with aioresponses() as m:
        m.get(ROR_API_PATTERN, status=400)
        client = RorClient("https://api.ror.org", "single_search", timeout=5, retries=1)
        with pytest.raises(Exception, match="400"):
            await client.query_affiliation("Bad Request")


@pytest.fixture
def marple_response_match():
    return {
        "status": "ok",
        "message_type": "matched-item-list",
        "message": {
            "items": [
                {
                    "id": "https://ror.org/00f54p054",
                    "confidence": 0.95,
                    "strategies": ["affiliation-single-search"],
                }
            ],
            "strategy": "affiliation-single-search",
        },
    }


@pytest.mark.asyncio
async def test_marple_query_match(marple_response_match):
    with aioresponses() as m:
        m.get(MARPLE_API_PATTERN, payload=marple_response_match)
        client = MarpleClient("http://localhost:8000", timeout=5, retries=1)
        result = await client.query_affiliation("Stanford University")
        assert result == "https://ror.org/00f54p054"


@pytest.mark.asyncio
async def test_marple_query_no_match():
    with aioresponses() as m:
        m.get(
            MARPLE_API_PATTERN,
            payload={"status": "ok", "message": {"items": []}},
        )
        client = MarpleClient("http://localhost:8000", timeout=5, retries=1)
        result = await client.query_affiliation("Unknown Place")
        assert result is None


@pytest.mark.asyncio
async def test_marple_retries_on_500(marple_response_match):
    with aioresponses() as m:
        m.get(MARPLE_API_PATTERN, status=500)
        m.get(MARPLE_API_PATTERN, payload=marple_response_match)
        client = MarpleClient(
            "http://localhost:8000", timeout=5, retries=3, retry_backoff=0
        )
        result = await client.query_affiliation("Stanford University")
        assert result == "https://ror.org/00f54p054"


def test_marple_url_includes_task_and_strategy():
    client = MarpleClient(
        "http://localhost:8000",
        task="affiliation",
        strategy="affiliation-single-search",
    )
    url = client._build_url("MIT")
    assert "task=affiliation" in url
    assert "strategy=affiliation-single-search" in url
    assert "input=MIT" in url
    assert url.startswith("http://localhost:8000/match?")


@pytest.mark.asyncio
async def test_marple_full_pipeline(tmp_path, marple_response_match):
    working = tmp_path / ".ror_matcher"
    working.mkdir()
    (working / "unique_affiliations.json").write_text(
        json.dumps(["Stanford University", "MIT"])
    )

    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"""
input:
  file: "unused.csv"
  format: csv
  id_field: doi
  affiliation_fields:
    - institution
query:
  source: marple
  concurrency: 2
  timeout: 5
output:
  file: "{tmp_path}/out.csv"
  format: csv
working_dir: "{working}"
""")
    config = load_config(config_file)

    with aioresponses() as m:
        m.get(MARPLE_API_PATTERN, payload=marple_response_match, repeat=True)
        await run_query(config)

    matches_path = working / "ror_matches.jsonl"
    matches = [json.loads(l) for l in matches_path.read_text().strip().split("\n")]
    assert len(matches) == 2
    assert all(m["ror_id"] == "https://ror.org/00f54p054" for m in matches)


def test_checkpoint_save_and_load(tmp_path):
    cp_path = tmp_path / "test.checkpoint"
    cp = Checkpoint(cp_path)
    cp.mark_processed("abc123")
    cp.mark_processed("def456")
    cp.save()

    loaded = Checkpoint.load(cp_path)
    assert loaded.is_processed("abc123")
    assert loaded.is_processed("def456")
    assert not loaded.is_processed("unknown")


def test_checkpoint_load_nonexistent(tmp_path):
    cp = Checkpoint.load(tmp_path / "nonexistent.checkpoint")
    assert not cp.is_processed("anything")
    assert len(cp) == 0


@pytest.mark.asyncio
async def test_query_full_pipeline(tmp_path):
    working = tmp_path / ".ror_matcher"
    working.mkdir()
    affiliations = ["University of Oxford", "MIT"]
    (working / "unique_affiliations.json").write_text(json.dumps(affiliations))

    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"""
input:
  file: "unused.csv"
  format: csv
  id_field: doi
  affiliation_fields:
    - institution
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
  concurrency: 2
  timeout: 5
output:
  file: "{tmp_path}/out.csv"
  format: csv
working_dir: "{working}"
""")
    config = load_config(config_file)

    with aioresponses() as m:
        m.get(
            ROR_API_PATTERN,
            payload={"items": [{"chosen": True, "organization": {"id": "https://ror.org/052gg0110"}}]},
            repeat=True,
        )
        await run_query(config)

    matches_path = working / "ror_matches.jsonl"
    assert matches_path.exists()
    matches = [json.loads(l) for l in matches_path.read_text().strip().split("\n")]
    assert len(matches) == 2

    checkpoint_path = working / "query.checkpoint"
    assert checkpoint_path.exists()


@pytest.mark.asyncio
async def test_query_resume_skips_processed(tmp_path):
    working = tmp_path / ".ror_matcher"
    working.mkdir()
    affiliations = ["University of Oxford", "MIT"]
    (working / "unique_affiliations.json").write_text(json.dumps(affiliations))

    from ror_matcher.models import hash_affiliation
    cp = Checkpoint(working / "query.checkpoint")
    cp.mark_processed(hash_affiliation("University of Oxford"))
    cp.save()

    (working / "ror_matches.jsonl").write_text("")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"""
input:
  file: "unused.csv"
  format: csv
  id_field: doi
  affiliation_fields:
    - institution
query:
  base_url: "https://api.ror.org"
  endpoint: single_search
  concurrency: 2
  timeout: 5
output:
  file: "{tmp_path}/out.csv"
  format: csv
working_dir: "{working}"
""")
    config = load_config(config_file)

    with aioresponses() as m:
        m.get(
            ROR_API_PATTERN,
            payload={"items": [{"chosen": True, "organization": {"id": "https://ror.org/abc"}}]},
            repeat=True,
        )
        await run_query(config, resume=True)

    matches = [json.loads(l) for l in (working / "ror_matches.jsonl").read_text().strip().split("\n") if l.strip()]
    assert len(matches) == 1
    assert matches[0]["affiliation"] == "MIT"
