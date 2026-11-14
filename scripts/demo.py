"""Run an authenticated read-only live demo without displaying credentials."""

import argparse
import json
from pathlib import Path

import httpx

from scripts.local_services import environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--message",
        default="Find the best recent model, identify its dataset version, check deployment status, and explain whether retraining is necessary",
    )
    args = parser.parse_args()
    env = environment()
    with httpx.Client(trust_env=False, timeout=600) as client:
        result = client.post(
            "http://localhost:8001/chat",
            json={"message": args.message},
            headers={"Authorization": "Bearer " + env["AGENT_API_TOKEN"]},
        )
        result.raise_for_status()
        data = result.json()
    print(data["answer"])
    # Confirmation capabilities are private and excluded from shared demo exports.
    data["pending_actions"] = []
    for row in data.get("evidence", []):
        if row.get("status") == "confirmation_required" and isinstance(row.get("data"), dict):
            row["data"].pop("confirmation_token", None)
    Path("evidence/latest-demo.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
