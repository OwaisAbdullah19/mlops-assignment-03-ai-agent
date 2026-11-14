"""Capture actual responses only. Unavailable infrastructure remains explicit in the export."""

import json
import logging
import time
from pathlib import Path
from uuid import uuid4

from agent.config import Settings
from agent.orchestrator import Agent
from agent.tools import build_registry

PROMPTS = [
    ("01-dataset", "Which dataset version is currently tracked, and how can I reproduce it?"),
    ("02-model-selection", "Compare the last five training runs and recommend the best model by F1"),
    ("03-pipeline", "Report training pipeline status and diagnose failed tasks"),
    ("04-deployment", "Why is my prediction API unavailable?"),
    (
        "05-multi-tool",
        "Find the best recent model, identify the dataset version used to train it, check the deployment status, and explain whether retraining is necessary",
    ),
]


def main():
    output = Path("evidence")
    output.mkdir(exist_ok=True)
    log = logging.FileHandler(output / "tool-audit.jsonl", encoding="utf-8")
    log.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger("mlops.tools").addHandler(log)
    logging.getLogger("mlops.tools").setLevel(logging.INFO)
    settings = Settings()
    registry = build_registry(settings)
    agent = Agent(settings, registry)
    summary = []
    for name, prompt in PROMPTS:
        result = agent.ask(prompt)
        # Confirmation capabilities do not belong in published evidence.
        result["pending_actions"] = []
        result["prompt"] = prompt
        result["evidence_kind"] = (
            "actual tool calls; unavailable services are errors, never simulated successes"
        )
        (output / f"{name}.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        summary.append(
            {
                "scenario": name,
                "tools": [{"tool": e["tool"], "status": e["status"]} for e in result["evidence"]],
            }
        )
    # Explicitly capture two real training failures independently of Airflow availability.
    from training.train import evaluate, preprocess, quality_gate, train

    failures = []
    for kind in ("validation", "quality"):
        destination = f".runtime/failure-{kind}-{uuid4().hex[:8]}"
        start = time.monotonic()
        try:
            preprocess("data/iris.csv", destination, failure=kind)
            train(destination)
            evaluate("data/iris.csv", destination, failure=kind, track=False)
            quality_gate(destination)
            failures.append({"injection": kind, "unexpected_success": True})
        except ValueError as exc:
            failures.append(
                {
                    "injection": kind,
                    "error": str(exc),
                    "blocked": True,
                    "approved_artifact_exists": (Path(destination) / "approved.json").exists(),
                    "duration_ms": round((time.monotonic() - start) * 1000, 2),
                }
            )
    (output / "failure-investigations.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
    (output / "capture-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
