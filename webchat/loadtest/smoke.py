#!/usr/bin/env python3
"""Short reachability load for CI: fixed request count, fixed concurrency, p95 and failures.

It is not the realtime/history/search profile. It proves the stack answers under concurrent load and
gives the harness a place to grow. Usage:

    python3 loadtest/smoke.py --url http://localhost:8080/healthz --requests 200 --workers 20
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def one(url: str, timeout: float) -> tuple[float, str | None]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            response.read()
            if response.status != 200:
                return (time.perf_counter() - started) * 1000, f"status {response.status}"
    except Exception as error:  # noqa: BLE001 - the report needs the reason, not a traceback
        return (time.perf_counter() - started) * 1000, f"{type(error).__name__}: {error}"
    return (time.perf_counter() - started) * 1000, None


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--max-p95-ms", type=float, default=1000.0)
    args = parser.parse_args()

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda _: one(args.url, args.timeout), range(args.requests)))
    elapsed = time.perf_counter() - started

    latencies = [latency for latency, error in results if error is None]
    failures = [error for _, error in results if error is not None]
    report = {
        "url": args.url,
        "requests": args.requests,
        "workers": args.workers,
        "duration_s": round(elapsed, 3),
        "throughput_per_s": round(args.requests / elapsed, 1),
        "failures": len(failures),
        "p50_ms": round(percentile(latencies, 0.50), 1) if latencies else None,
        "p95_ms": round(percentile(latencies, 0.95), 1) if latencies else None,
        "p99_ms": round(percentile(latencies, 0.99), 1) if latencies else None,
        "median_ms": round(statistics.median(latencies), 1) if latencies else None,
        "first_failure": failures[0] if failures else None,
    }
    print(json.dumps(report, indent=2))

    if failures:
        print(f"{len(failures)} request(s) failed", file=sys.stderr)
        return 1
    if report["p95_ms"] is None or report["p95_ms"] > args.max_p95_ms:
        print(f"p95 {report['p95_ms']} ms exceeds {args.max_p95_ms} ms", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
