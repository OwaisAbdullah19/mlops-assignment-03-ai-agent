"""Read states/logs of the explicitly confirmed demo runs; never trigger a workflow."""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from scripts.local_services import environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    os.environ.update(environment())
    from agent.config import Settings
    from agent.tools.airflow_tools import AirflowTools

    tools = AirflowTools(Settings())
    path = Path("evidence/live-pipeline-executions.json")
    evidence = json.loads(path.read_text(encoding="utf-8"))
    deadline, previous = time.monotonic() + 900, None
    while True:
        runs = {r["dag_run_id"]: r for r in tools.runs(limit=20)["dag_runs"]}
        complete, summary = True, []
        for row in evidence["runs"]:
            run_id = (row["trigger_result"].get("data") or {}).get("dag_run_id")
            run = runs.get(run_id)
            if not run:
                complete = False
                summary.append((row["failure"], "unknown"))
                continue
            row["dag_run"] = run
            state = run["state"]
            summary.append((row["failure"], state))
            if state in ("success", "failed"):
                if "tasks" not in row:
                    row["tasks"] = tools.tasks("ml_training", run_id)
                    row["failure_logs"] = [
                        {
                            "task_id": t["task_id"],
                            **tools.logs("ml_training", run_id, t["task_id"], max(1, t["try_number"])),
                        }
                        for t in row["tasks"]["failed_tasks"]
                        if t["state"] == "failed"
                    ]
                row["expected_outcome_observed"] = state == (
                    "success" if row["failure"] == "none" else "failed"
                )
            else:
                complete = False
        evidence["observed_at"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        if summary != previous:
            print(json.dumps(summary), flush=True)
            previous = summary
        if complete:
            if not all(r.get("expected_outcome_observed") for r in evidence["runs"]):
                raise SystemExit("A live run did not match the expected demonstration outcome")
            print(
                "Normal workflow and both injected failures reached their expected terminal states",
                flush=True,
            )
            return
        if not args.wait or time.monotonic() > deadline:
            return
        time.sleep(5)


if __name__ == "__main__":
    main()
