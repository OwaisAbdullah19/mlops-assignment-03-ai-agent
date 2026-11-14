from dataclasses import replace
from unittest.mock import Mock

from agent.orchestrator import Agent
from agent.schemas import Runs


def test_ollama_structured_tool_selection_executes_evidence_only(registry, settings, monkeypatch):
    fn = Mock(return_value={"best": None, "runs": []})
    registry.add("mlflow_best", "best", Runs, fn)
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    first = Mock()
    first.json.return_value = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "mlflow_best", "arguments": {"metric": "accuracy", "limit": 3}}}
            ],
        }
    }
    final = Mock()
    final.json.return_value = {"message": {"role": "assistant", "content": "Invented: all Pods are healthy"}}
    client.post.side_effect = [first, final]
    monkeypatch.setattr("agent.orchestrator.httpx.Client", Mock(return_value=client))
    result = Agent(replace(settings, planner="ollama"), registry).ask("Inspect recent accuracy results")
    fn.assert_called_once_with(metric="accuracy", limit=3, direction="max")
    assert "Invented" not in result["answer"]
    assert result["evidence"][0]["tool"] == "mlflow_best"


def test_llm_outage_does_not_make_up_results(registry, settings, monkeypatch):
    monkeypatch.setattr("agent.orchestrator.httpx.Client", Mock(side_effect=ConnectionError()))
    result = Agent(replace(settings, planner="ollama"), registry).ask("Investigate model performance")
    assert result["evidence"] == []
    assert "LLM planner unavailable" in result["answer"]
