"""
Quick script to hammer the login endpoint with invalid credentials and observe rate limiting.

Usage:
    uv run python test/bruteforce_simulation.py --username demo --attempts 20
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import string
import sys
import time
from collections import Counter

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate brute-force login attempts.")
    parser.add_argument("--base-url", default=os.getenv("TEST_BASE_URL", "http://localhost:5050"), help="API base URL")
    parser.add_argument("--username", default=os.getenv("TEST_USERNAME", "admin"), help="Login identifier to attack")
    parser.add_argument("--attempts", type=int, default=20, help="Total number of attempts to issue (default: 20)")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Concurrent request limit (default: 4)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="Delay in seconds between scheduling attempts (default: 0.05)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Explicit password to reuse for each request; random values are used when omitted",
    )
    return parser.parse_args()


def build_payload(username: str, password: str) -> dict[str, str]:
    return {"username": username, "password": password}


def random_password() -> str:
    base = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(random.choices(base, k=12))


async def attempt_login(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    attempt_no: int,
    username: str,
    static_password: str | None,
) -> tuple[int, float]:
    async with semaphore:
        password = static_password or random_password()
        payload = build_payload(username, password)
        started = time.perf_counter()
        response = await client.post("/api/auth/token", data=payload)
        elapsed = time.perf_counter() - started
        detail = (
            response.json().get("detail")
            if response.headers.get("content-type", "").startswith("application/json")
            else response.text
        )
        print(
            f"[{attempt_no:02d}] {response.status_code} in {elapsed * 1000:.1f} ms (pwd={password!r}) detail={detail!r}"
        )
        return response.status_code, elapsed


async def run_simulation(args: argparse.Namespace) -> int:
    timeout = httpx.Timeout(10.0, connect=3.0)
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
    semaphore = asyncio.Semaphore(args.concurrency)
    status_counts: Counter[int] = Counter()

    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=timeout, limits=limits) as client:
        tasks = []
        for attempt_no in range(1, args.attempts + 1):
            tasks.append(
                asyncio.create_task(attempt_login(client, semaphore, attempt_no, args.username, args.password))
            )
            if args.delay:
                await asyncio.sleep(args.delay)

        for task in asyncio.as_completed(tasks):
            status_code, _ = await task
            status_counts[status_code] += 1

    print("\nSummary:")
    for code, total in sorted(status_counts.items()):
        print(f"  HTTP {code}: {total} hits")

    if 429 in status_counts:
        print("Rate limiting engaged (HTTP 429 encountered).")
        return 0

    print("No rate limiting observed; consider increasing attempt count or reducing delay.")
    return 1


def main() -> None:
    args = parse_args()
    try:
        exit_code = asyncio.run(run_simulation(args))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        exit_code = 130
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
