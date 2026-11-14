import time
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from agent.main import create_app
from agent.schemas import Restart, ToolCall, Trigger


def test_unauthorized_kubernetes_namespace_rejected(registry):
    fn = Mock()
    registry.add("kubernetes_restart", "restart", Restart, fn, True)
    result = registry.execute(
        ToolCall(name="kubernetes_restart", arguments={"namespace": "kube-system"}), "r"
    )
    assert result.status == "denied"
    fn.assert_not_called()


def test_kubernetes_mutation_requires_exact_single_use_confirmation(registry):
    fn = Mock(return_value={"restart_requested": True})
    registry.add("kubernetes_restart", "restart", Restart, fn, True)
    proposal = registry.execute(ToolCall(name="kubernetes_restart"), "r")
    assert proposal.status == "confirmation_required"
    fn.assert_not_called()
    token = proposal.data["confirmation_token"]
    assert registry.confirm(token, "r2").status == "ok"
    fn.assert_called_once_with(namespace="mlops-agent", deployment="iris-api")
    with pytest.raises(PermissionError):
        registry.confirm(token, "r3")


def test_model_cannot_inject_confirmation_argument(registry):
    fn = Mock()
    registry.add("kubernetes_restart", "restart", Restart, fn, True)
    result = registry.execute(ToolCall(name="kubernetes_restart", arguments={"approved": True}), "r")
    assert result.status == "error"
    fn.assert_not_called()


def test_confirmation_expiration(registry):
    registry.add("kubernetes_restart", "restart", Restart, Mock(), True)
    token = registry.execute(ToolCall(name="kubernetes_restart"), "r").data["confirmation_token"]
    _, call = registry.confirmations.pending[token]
    registry.confirmations.pending[token] = (time.monotonic() - 1, call)
    with pytest.raises(PermissionError):
        registry.confirm(token, "r")


def test_unapproved_dag_rejected(registry):
    fn = Mock()
    registry.add("airflow_trigger", "trigger", Trigger, fn, True)
    result = registry.execute(
        ToolCall(name="airflow_trigger", arguments={"dag_id": "delete_everything"}), "r"
    )
    assert result.status == "denied"
    fn.assert_not_called()


def test_api_auth_and_confirmation_endpoint(registry, settings, monkeypatch):
    fn = Mock(return_value={"restart_requested": True})
    registry.add("kubernetes_restart", "restart", Restart, fn, True)
    monkeypatch.setenv("AGENT_API_TOKEN", "test-api-credential")
    client = TestClient(create_app(settings, registry))
    assert client.post("/chat", json={"message": "restart deployment"}).status_code == 401
    headers = {"Authorization": "Bearer test-api-credential"}
    result = client.post("/chat", json={"message": "restart deployment"}, headers=headers).json()
    fn.assert_not_called()
    token = result["pending_actions"][0]["confirmation_token"]
    assert client.post("/confirm", json={"token": token}, headers=headers).json()["status"] == "ok"
    assert client.post("/confirm", json={"token": token}, headers=headers).status_code == 403


def test_api_invalid_request_rejected(registry, settings, monkeypatch):
    monkeypatch.setenv("AGENT_API_TOKEN", "test-api-credential")
    client = TestClient(create_app(settings, registry))
    assert (
        client.post(
            "/chat", json={"message": ""}, headers={"Authorization": "Bearer test-api-credential"}
        ).status_code
        == 422
    )
