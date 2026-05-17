import asyncio
import json
import logging
from pathlib import Path
from urllib.parse import quote

import aiohttp
from tqdm import tqdm

from .models import Config, RorFailureRecord, RorMatchRecord, hash_affiliation

logger = logging.getLogger(__name__)


class _BaseClient:
    def __init__(
        self,
        base_url: str,
        timeout: int = 30,
        retries: int = 3,
        retry_backoff: int = 2,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.retries = retries
        self.retry_backoff = retry_backoff
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get_json(self, url: str) -> dict:
        session = await self._get_session()
        for attempt in range(self.retries):
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:
                        retry_after = response.headers.get("Retry-After")
                        wait = (
                            int(retry_after)
                            if retry_after and retry_after.isdigit()
                            else self.retry_backoff ** attempt
                        )
                        logger.warning("Rate limited, waiting %ds", wait)
                        await asyncio.sleep(wait)
                        continue
                    elif response.status >= 500:
                        if attempt < self.retries - 1:
                            wait = self.retry_backoff ** attempt
                            logger.warning(
                                "HTTP %d, retrying in %ds",
                                response.status,
                                wait,
                            )
                            await asyncio.sleep(wait)
                            continue
                        raise Exception(
                            f"HTTP {response.status} after {self.retries} retries"
                        )
                    else:
                        raise Exception(f"HTTP {response.status}")
            except aiohttp.ClientError as e:
                if attempt < self.retries - 1:
                    wait = self.retry_backoff ** attempt
                    logger.warning(
                        "Connection error, retrying in %ds: %s", wait, e
                    )
                    await asyncio.sleep(wait)
                    continue
                raise

        raise Exception(f"Max retries ({self.retries}) exceeded")


class RorClient(_BaseClient):
    def __init__(
        self,
        base_url: str,
        endpoint: str,
        timeout: int = 30,
        retries: int = 3,
        retry_backoff: int = 2,
    ):
        super().__init__(base_url, timeout, retries, retry_backoff)
        self.endpoint = endpoint

    def _build_url(self, affiliation: str) -> str:
        encoded = quote(affiliation, safe="")
        return (
            f"{self.base_url}/v2/organizations"
            f"?affiliation={encoded}&{self.endpoint}"
        )

    async def query_affiliation(self, affiliation: str) -> str | None:
        data = await self._get_json(self._build_url(affiliation))
        return self._extract_chosen_ror_id(data)

    @staticmethod
    def _extract_chosen_ror_id(data: dict) -> str | None:
        for item in data.get("items", []):
            if item.get("chosen") is True:
                org = item.get("organization", {})
                return org.get("id")
        return None


class MarpleClient(_BaseClient):
    def __init__(
        self,
        base_url: str,
        task: str = "affiliation",
        strategy: str = "affiliation-single-search",
        timeout: int = 30,
        retries: int = 3,
        retry_backoff: int = 2,
    ):
        super().__init__(base_url, timeout, retries, retry_backoff)
        self.task = task
        self.strategy = strategy

    def _build_url(self, affiliation: str) -> str:
        encoded = quote(affiliation, safe="")
        return (
            f"{self.base_url}/match"
            f"?task={self.task}"
            f"&strategy={self.strategy}"
            f"&input={encoded}"
        )

    async def query_affiliation(self, affiliation: str) -> str | None:
        data = await self._get_json(self._build_url(affiliation))
        return self._extract_match_id(data)

    @staticmethod
    def _extract_match_id(data: dict) -> str | None:
        items = data.get("message", {}).get("items", [])
        if not items:
            return None
        return items[0].get("id")


class Checkpoint:
    def __init__(self, path: Path):
        self.path = path
        self._processed: set[str] = set()

    @classmethod
    def load(cls, path: Path) -> "Checkpoint":
        cp = cls(path)
        if path.exists():
            for line in path.read_text().strip().split("\n"):
                line = line.strip()
                if line:
                    cp._processed.add(line)
        return cp

    def mark_processed(self, h: str):
        self._processed.add(h)

    def is_processed(self, h: str) -> bool:
        return h in self._processed

    def save(self):
        self.path.write_text(("\n".join(self._processed) + "\n") if self._processed else "")

    def __len__(self) -> int:
        return len(self._processed)


async def run(config: Config, resume: bool = False):
    working_dir = Path(config.working_dir)
    affiliations_path = working_dir / "unique_affiliations.json"
    affiliations: list[str] = json.loads(affiliations_path.read_text())

    checkpoint_path = working_dir / "query.checkpoint"
    checkpoint = Checkpoint.load(checkpoint_path) if resume else Checkpoint(checkpoint_path)

    to_process = [
        (aff, h)
        for aff in affiliations
        if not checkpoint.is_processed(h := hash_affiliation(aff))
    ]

    if not to_process:
        logger.info("No affiliations to process")
        return

    matches_path = working_dir / "ror_matches.jsonl"
    failures_path = working_dir / "ror_failures.jsonl"

    matches_mode = "a" if resume and matches_path.exists() else "w"
    failures_mode = "a" if resume and failures_path.exists() else "w"

    if config.query.source == "marple":
        client = MarpleClient(
            config.query.base_url,
            task=config.query.task,
            strategy=config.query.strategy,
            timeout=config.query.timeout,
            retries=config.query.retries,
            retry_backoff=config.query.retry_backoff,
        )
    else:
        client = RorClient(
            config.query.base_url,
            config.query.endpoint,
            timeout=config.query.timeout,
            retries=config.query.retries,
            retry_backoff=config.query.retry_backoff,
        )

    semaphore = asyncio.Semaphore(config.query.concurrency)
    matches_file = open(matches_path, matches_mode)
    failures_file = open(failures_path, failures_mode)
    progress = tqdm(total=len(to_process), desc="Querying ROR")

    async def process_one(affiliation: str, aff_hash: str):
        async with semaphore:
            try:
                ror_id = await client.query_affiliation(affiliation)
                if ror_id:
                    record = RorMatchRecord(affiliation, aff_hash, ror_id)
                    matches_file.write(json.dumps(record.__dict__) + "\n")
                else:
                    record = RorFailureRecord(affiliation, aff_hash, "No match found")
                    failures_file.write(json.dumps(record.__dict__) + "\n")
            except Exception as e:
                record = RorFailureRecord(affiliation, aff_hash, str(e))
                failures_file.write(json.dumps(record.__dict__) + "\n")
            checkpoint.mark_processed(aff_hash)
            progress.update(1)

    try:
        tasks = [process_one(aff, h) for aff, h in to_process]
        await asyncio.gather(*tasks)
    finally:
        progress.close()
        matches_file.close()
        failures_file.close()
        checkpoint.save()
        await client.close()
