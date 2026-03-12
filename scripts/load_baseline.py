from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import TypedDict, cast

import httpx


class LatencyReport(TypedDict):
    p50: float
    p95: float
    max: float


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
    return ordered[index]


def timed_request(
    client: httpx.Client,
    method: str,
    url: str,
    json_body: object | None = None,
) -> tuple[float, httpx.Response]:
    start = time.perf_counter()
    response = client.request(method, url, json=json_body)
    elapsed_ms = (time.perf_counter() - start) * 1000
    _ = response.raise_for_status()
    return elapsed_ms, response


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a lightweight ingest/ask latency baseline.")
    _ = parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    _ = parser.add_argument("--iterations", type=int, default=5)
    _ = parser.add_argument("--report", default="")
    args = parser.parse_args()

    ingest_latencies: list[float] = []
    ask_latencies: list[float] = []
    base_url = cast(str, args.base_url).rstrip("/")
    iterations = cast(int, args.iterations)
    report_path = cast(str, args.report)

    with httpx.Client(timeout=30.0) as client:
        _ = timed_request(client, "GET", f"{base_url}/healthz")

        for index in range(iterations):
            ingest_ms, _ = timed_request(
                client,
                "POST",
                f"{base_url}/api/text/add-to-vectordb",
                json_body={
                    "text": f"Higher policy rates pressure growth stocks. run={index}",
                    "metadata": {"doc_id": f"load_{index}", "source_type": "load_baseline"},
                },
            )
            ask_ms, _ = timed_request(
                client,
                "POST",
                f"{base_url}/api/ask",
                json_body={"question": "How do higher policy rates affect growth stocks?"},
            )
            ingest_latencies.append(ingest_ms)
            ask_latencies.append(ask_ms)

    ingest_report: LatencyReport = {
        "p50": round(percentile(ingest_latencies, 0.5), 2),
        "p95": round(percentile(ingest_latencies, 0.95), 2),
        "max": round(max(ingest_latencies, default=0.0), 2),
    }
    ask_report: LatencyReport = {
        "p50": round(percentile(ask_latencies, 0.5), 2),
        "p95": round(percentile(ask_latencies, 0.95), 2),
        "max": round(max(ask_latencies, default=0.0), 2),
    }

    report = {
        "base_url": base_url,
        "iterations": iterations,
        "ingest_ms": ingest_report,
        "ask_ms": ask_report,
        "ingest_mean_ms": round(statistics.fmean(ingest_latencies), 2) if ingest_latencies else 0.0,
        "ask_mean_ms": round(statistics.fmean(ask_latencies), 2) if ask_latencies else 0.0,
    }

    print(json.dumps(report, indent=2))
    if report_path:
        _ = Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
