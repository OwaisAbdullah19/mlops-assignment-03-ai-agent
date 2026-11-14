"""Check all prepared demo endpoints without revealing credentials."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx

ENDPOINTS = {
    "agent": "http://localhost:8001/health",
    "language_model": "http://localhost:11434/health",
    "mlflow": "http://localhost:5002/health",
    "airflow": "http://localhost:8080/api/v2/monitor/health",
    "kubernetes_inference": "http://localhost:8002/health/ready",
}


def check(item):
    name, url = item
    try:
        response = httpx.get(url, timeout=5, trust_env=False)
        try:
            body = response.json()
        except ValueError:
            body = response.text[:200]
        return name, {"url": url, "http_status": response.status_code, "response": body}
    except httpx.HTTPError as exc:
        return name, {"url": url, "error": type(exc).__name__}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=5) as pool:
        result = {
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "services": dict(pool.map(check, ENDPOINTS.items())),
        }
    encoded = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
