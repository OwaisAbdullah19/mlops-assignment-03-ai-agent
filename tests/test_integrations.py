from types import SimpleNamespace as NS
from unittest.mock import Mock

import httpx
import pytest

from agent.tools.airflow_tools import AirflowTools
from agent.tools.dvc_tools import DVCTools
from agent.tools.kubernetes_tools import KubernetesTools
from agent.tools.mlflow_tools import MLflowTools


def run(run_id, score, status="FINISHED"):
    return NS(
        info=NS(run_id=run_id, experiment_id="1", status=status, start_time=100),
        data=NS(metrics={"f1": score}, params={"C": "1"}, tags={"dataset.git_commit": "abc"}),
    )


def test_mlflow_ranking_excludes_failed_and_nan_runs(settings):
    client = Mock()
    client.get_experiment_by_name.return_value = NS(experiment_id="1")
    client.search_runs.return_value = [
        run("new", 0.8),
        run("failed", 1.0, "FAILED"),
        run("nan", float("nan")),
        run("best", 0.95),
    ]
    result = MLflowTools(settings, client).best()
    assert result["best"]["run_id"] == "best"
    assert "production readiness" in result["caution"]
    assert client.search_runs.call_args.kwargs["order_by"] == ["attributes.start_time DESC"]


def test_mlflow_minimization_supported(settings):
    client = Mock()
    client.get_experiment_by_name.return_value = NS(experiment_id="1")
    client.search_runs.return_value = [run("low", 0.2), run("high", 0.9)]
    assert MLflowTools(settings, client).best(direction="min")["best"]["run_id"] == "low"


def test_airflow_uses_authenticated_v2_and_failed_task_diagnostics(settings):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"task_instances": [{"task_id": "validation", "state": "failed"}]})

    tools = AirflowTools(settings, httpx.Client(transport=httpx.MockTransport(handler)))
    result = tools.tasks("ml_training", "manual__123")
    assert result["failed_tasks"][0]["task_id"] == "validation"
    assert seen[0].url.path == "/api/v2/dags/ml_training/dagRuns/manual__123/taskInstances"
    assert seen[0].headers["Authorization"] == "Bearer test-only-token"


def test_airflow_http_failure_raises(settings):
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(503)))
    with pytest.raises(httpx.HTTPStatusError):
        AirflowTools(settings, client).dags()


def test_dvc_rejects_path_traversal_before_subprocess(settings):
    tools = DVCTools(settings)
    tools._run = Mock()
    with pytest.raises(ValueError):
        tools.version("../../secret.csv")
    tools._run.assert_not_called()


def test_dvc_version_detects_provenance_mismatch(settings):
    tools = DVCTools(settings)
    tools._run = Mock(side_effect=["abcdef", "outs:\n- md5: actual\n  path: iris.csv\n"])
    result = tools.version(expected_digest="different")
    assert result["matches_recorded_digest"] is False
    assert tools._run.call_args_list[1].args[0] == ["git", "show", "abcdef:data/iris.csv.dvc"]


def test_unhealthy_pod_and_restarts_are_reported(settings):
    core = Mock()
    status = NS(
        name="inference",
        ready=False,
        restart_count=3,
        image="bad:v1",
        state=NS(waiting=NS(reason="CrashLoopBackOff")),
    )
    pod = NS(
        metadata=NS(name="iris-api-test"),
        status=NS(
            phase="Running",
            container_statuses=[status],
            conditions=[NS(type="Ready", status="False", reason="ContainersNotReady")],
        ),
    )
    core.list_namespaced_pod.return_value = NS(items=[pod])
    result = KubernetesTools(settings, core, Mock()).pods()
    assert result["pods"][0]["unhealthy"] is True
    assert result["pods"][0]["containers"][0]["restarts"] == 3


def test_kubernetes_logs_reject_unrelated_pod(settings):
    core = Mock()
    core.list_namespaced_pod.return_value = NS(items=[])
    with pytest.raises(PermissionError):
        KubernetesTools(settings, core, Mock()).logs("some-secret-pod")
    core.read_namespaced_pod_log.assert_not_called()
