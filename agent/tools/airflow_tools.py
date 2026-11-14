from datetime import datetime, timezone
from urllib.parse import quote
from uuid import uuid4

import httpx

from agent.schemas import Dag, DagRun, Empty, TaskLog, Trigger
from agent.security import redact


class AirflowTools:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client

    def request(self, method, path, **kwargs):
        if not self.settings.airflow_token:
            raise RuntimeError("AIRFLOW_TOKEN is required")
        headers = {"Authorization": f"Bearer {self.settings.airflow_token}"}
        url = self.settings.airflow_url.rstrip("/") + "/api/v2/" + path
        if self.client is not None:
            response = self.client.request(
                method, url, headers=headers, timeout=self.settings.timeout, **kwargs
            )
        else:
            with httpx.Client() as client:
                response = client.request(
                    method, url, headers=headers, timeout=self.settings.timeout, **kwargs
                )
        response.raise_for_status()
        return response.json()

    def dags(self):
        return self.request("GET", "dags", params={"limit": 100})

    def runs(self, dag_id="ml_training", limit=5):
        return self.request(
            "GET",
            f"dags/{quote(dag_id, safe='')}/dagRuns",
            params={"limit": limit, "order_by": "-logical_date"},
        )

    def tasks(self, dag_id, run_id):
        data = self.request(
            "GET",
            f"dags/{quote(dag_id, safe='')}/dagRuns/{quote(run_id, safe='')}/taskInstances",
            params={"limit": 100},
        )
        return {
            **data,
            "failed_tasks": [
                t for t in data.get("task_instances", []) if t.get("state") in ("failed", "upstream_failed")
            ],
        }

    def logs(self, dag_id, run_id, task_id, try_number=1):
        path = (
            f"dags/{quote(dag_id, safe='')}/dagRuns/{quote(run_id, safe='')}/taskInstances/"
            f"{quote(task_id, safe='')}/logs/{try_number}"
        )
        return {"logs": redact(str(self.request("GET", path, params={"full_content": "true"})))[:16000]}

    def trigger(self, dag_id="ml_training", failure="none"):
        # No HTTP retry: a timed-out POST may already have started a run.
        return self.request(
            "POST",
            f"dags/{quote(dag_id, safe='')}/dagRuns",
            json={
                "dag_run_id": f"agent__{uuid4().hex}",
                "logical_date": datetime.now(timezone.utc).isoformat(),
                "conf": {"failure": failure},
            },
        )

    def register(self, r):
        r.add("airflow_dags", "List Airflow 3 DAGs", Empty, self.dags)
        r.add("airflow_runs", "Read recent training DAG run states", Dag, self.runs)
        r.add("airflow_tasks", "Read task states and identify failed tasks", DagRun, self.tasks)
        r.add("airflow_logs", "Retrieve failure diagnostics from task logs", TaskLog, self.logs)
        r.add(
            "airflow_trigger",
            "Request an approved DAG run; explicit confirmation required",
            Trigger,
            self.trigger,
            True,
        )
