import asyncio
import time
from dataclasses import dataclass
from urllib.parse import quote

import aiohttp

SYNTHETIC_AFFILIATIONS = [
    "University of Oxford",
    "Massachusetts Institute of Technology",
    "Stanford University",
    "ETH Zurich",
    "University of Tokyo",
]


@dataclass
class ConcurrencyResult:
    level: int
    passed: bool
    avg_latency_ms: float
    error_count: int
    total_requests: int


async def test_concurrency_level(
    base_url: str,
    level: int,
    timeout: int = 10,
) -> ConcurrencyResult:
    base_url = base_url.rstrip("/")
    timeout_config = aiohttp.ClientTimeout(total=timeout)
    errors = 0
    latencies: list[float] = []

    async def single_request(session: aiohttp.ClientSession, affiliation: str):
        nonlocal errors
        url = (
            f"{base_url}/v2/organizations"
            f"?affiliation={quote(affiliation, safe='')}&single_search"
        )
        start = time.monotonic()
        try:
            async with session.get(url) as resp:
                await resp.read()
                latency = (time.monotonic() - start) * 1000
                latencies.append(latency)
                if resp.status >= 400:
                    errors += 1
        except Exception:
            errors += 1
            latencies.append((time.monotonic() - start) * 1000)

    async with aiohttp.ClientSession(timeout=timeout_config) as session:
        tasks = []
        for i in range(level):
            aff = SYNTHETIC_AFFILIATIONS[i % len(SYNTHETIC_AFFILIATIONS)]
            tasks.append(single_request(session, aff))
        await asyncio.gather(*tasks)

    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    passed = errors == 0

    return ConcurrencyResult(
        level=level,
        passed=passed,
        avg_latency_ms=round(avg_latency, 1),
        error_count=errors,
        total_requests=level,
    )


async def find_optimal_concurrency(
    base_url: str,
    timeout: int = 10,
    floor: int = 5,
    ceiling: int = 200,
    safety_margin: float = 0.8,
) -> int:
    best_passing = floor
    low = floor
    high = ceiling

    result = await test_concurrency_level(base_url, floor, timeout)
    if not result.passed:
        return 1

    while low <= high:
        mid = (low + high) // 2
        result = await test_concurrency_level(base_url, mid, timeout)

        if result.passed:
            best_passing = mid
            low = mid + 1
        else:
            high = mid - 1

    return max(1, int(best_passing * safety_margin))
