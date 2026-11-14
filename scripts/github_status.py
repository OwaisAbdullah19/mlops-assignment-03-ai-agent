"""Read hosted CI status using an existing noninteractive Git credential helper."""

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-write", action="store_true", help="Inspect CI without modifying evidence")
    args = parser.parse_args()
    remote = subprocess.check_output(["git", "remote", "get-url", "origin"], text=True).strip()
    match = re.fullmatch(r"https://github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?", remote)
    if not match:
        raise SystemExit("Expected an HTTPS github.com origin")
    repo = match[1]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    credential = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True,
        capture_output=True,
        env=env,
        timeout=20,
    )
    fields = dict(line.split("=", 1) for line in credential.stdout.splitlines() if "=" in line)
    if not fields.get("password"):
        raise SystemExit("No existing GitHub credential; no interactive login was opened")
    with httpx.Client(
        headers={"Authorization": "Bearer " + fields["password"], "Accept": "application/vnd.github+json"},
        timeout=30,
    ) as client:
        response = client.get(f"https://api.github.com/repos/{repo}/actions/runs", params={"per_page": 5})
        response.raise_for_status()
        rows = []
        for run in response.json()["workflow_runs"]:
            row = {
                key: run.get(key) for key in ("id", "name", "html_url", "head_sha", "status", "conclusion")
            }
            jobs = client.get(f"https://api.github.com/repos/{repo}/actions/runs/{run['id']}/jobs")
            jobs.raise_for_status()
            row["jobs"] = [
                {
                    "name": j["name"],
                    "status": j["status"],
                    "conclusion": j["conclusion"],
                    "steps": [{k: s.get(k) for k in ("name", "status", "conclusion")} for s in j["steps"]],
                }
                for j in jobs.json()["jobs"]
            ]
            rows.append(row)
    result = {
        "repository": "https://github.com/" + repo,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "runs": rows,
    }
    if not args.no_write:
        Path("evidence/github-ci.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
