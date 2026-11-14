import json
import time
from unittest.mock import Mock

import httpx
import pytest

from agent.orchestrator import Agent
from agent.schemas import Dag, DagRun, Dataset, Empty, Namespace, Runs, TaskLog, ToolCall, Trigger


def candidate():
    return {
        "run_id": "a" * 32,
        "status": "FINISHED",
        "start_time": time.time() * 1000,
        "metrics": {"f1": 0.94},
        "provenance": {
            "dataset.git_commit": "b" * 40,
            "dataset.path": "data/iris.csv",
            "dataset.dvc_digest": "c" * 32,
            "quality.passed": "true",
        },
    }


def test_multi_tool_uses_recorded_provenance_and_never_triggers(registry, settings):
    version = Mock(return_value={"dataset": "data/iris.csv", "git_commit": "b" * 40, "dvc_digest": "c" * 32})
    registry.add("mlflow_best", "best", Runs, lambda **kw: {"best": candidate(), "metric": "f1"})
    registry.add("dvc_version", "version", Dataset, version)
    registry.add("dvc_status", "status", Empty, lambda: {"changes": {}})
    registry.add("kubernetes_deployments", "deploy", Namespace, lambda **kw: {"deployments": []})
    registry.add("kubernetes_pods", "pods", Namespace, lambda **kw: {"pods": []})
    registry.add("kubernetes_services", "services", Namespace, lambda **kw: {"services": []})
    registry.add("airflow_runs", "runs", Dag, lambda **kw: {"dag_runs": []})
    trigger = Mock()
    registry.add("airflow_trigger", "trigger", Trigger, trigger, True)
    result = Agent(settings, registry).ask(
        "Find the best recent model, identify dataset version, check deployment and explain whether retraining is necessary"
    )
    version.assert_called_once_with(dataset="data/iris.csv", revision="b" * 40, expected_digest="c" * 32)
    trigger.assert_not_called()
    assert {e["tool"].split("_")[0] for e in result["evidence"]} == {"mlflow", "dvc", "kubernetes", "airflow"}
    assert "No retraining was initiated" in result["answer"]
    assert "0.94" in result["answer"]


def test_unavailable_service_does_not_invent_operational_results(registry, settings):
    registry.add("mlflow_best", "best", Runs, Mock(side_effect=RuntimeError("password=SUPERSECRET")))
    result = Agent(settings, registry).ask("Find the best model by F1")
    assert "state is unknown" in result["answer"]
    assert "Candidate" not in result["answer"]
    assert "SUPERSECRET" not in json.dumps(result)
    assert result["evidence"][0]["status"] == "error"


def test_timeout_is_reported(registry):
    registry.add("slow", "slow", Empty, Mock(side_effect=httpx.ReadTimeout("token=secret")))
    result = registry.execute(ToolCall(name="slow"), "request-123")
    assert result.status == "error"
    assert "timed out" in result.error
    assert result.request_id == "request-123"


def test_invalid_tool_arguments_never_execute(registry):
    fn = Mock()
    registry.add("mlflow_best", "best", Runs, fn)
    result = registry.execute(ToolCall(name="mlflow_best", arguments={"limit": -10, "confirmed": True}), "r")
    assert result.status == "error"
    fn.assert_not_called()


def test_unknown_tool_rejected(registry):
    assert registry.execute(ToolCall(name="shell_exec", arguments={"cmd": "whoami"}), "r").status == "error"


def test_freshness_policy_supports_retraining_review(registry, settings):
    old = candidate()
    old["start_time"] -= 45 * 86400000
    registry.add("mlflow_best", "best", Runs, lambda **kw: {"best": old})
    result = Agent(settings, registry).ask("Best model by F1")
    assert "exceeds configured 30-day freshness policy" in result["answer"]


def test_missing_provenance_is_explicit(registry, settings):
    run = candidate()
    run["provenance"] = {}
    registry.add("mlflow_best", "best", Runs, lambda **kw: {"best": run})
    result = Agent(settings, registry).ask("Find best model and dataset and deployment")
    assert "incomplete DVC provenance" in result["answer"]
    assert "dvc_version" not in [r["tool"] for r in result["evidence"]]


def test_structured_logs_do_not_contain_tool_arguments_or_secrets(registry, caplog):
    registry.add("oops", "failure", Empty, Mock(side_effect=RuntimeError("Bearer VERYSECRET")))
    with caplog.at_level("INFO", logger="mlops.tools"):
        registry.execute(ToolCall(name="oops"), "request-log")
    row = json.loads(caplog.records[-1].message)
    assert set(row) == {"tool", "status", "duration_ms", "request_id"}
    assert row["status"] == "error"
    assert "VERYSECRET" not in caplog.text


@pytest.mark.parametrize("failed_task", ["validation", "quality_gate"])
def test_pipeline_diagnostics_find_failed_task_after_upstream_failures(registry, settings, failed_task):
    registry.add(
        "airflow_runs",
        "runs",
        Dag,
        lambda **kw: {
            "dag_runs": [
                {
                    "dag_run_id": "run-1",
                    "state": "failed",
                    "conf": {"failure": "quality" if failed_task == "quality_gate" else "validation"},
                }
            ]
        },
    )
    tasks = [
        {"task_id": "evaluation_mlflow", "state": "upstream_failed"},
        {"task_id": "preprocessing", "state": "upstream_failed"},
        {"task_id": failed_task, "state": "failed", "try_number": 3},
    ]
    registry.add(
        "airflow_tasks", "tasks", DagRun, lambda **kw: {"task_instances": tasks, "failed_tasks": tasks}
    )
    logs = Mock(return_value={"logs": f"Injected failure in {failed_task}"})
    registry.add("airflow_logs", "logs", TaskLog, logs)
    result = Agent(settings, registry).ask("Report training pipeline status")
    logs.assert_called_once_with(dag_id="ml_training", run_id="run-1", task_id=failed_task, try_number=3)
    assert f"Injected failure in {failed_task}" in result["answer"]
    assert "does not establish production model degradation" in result["answer"]
    assert "No retraining was initiated" in result["answer"]
