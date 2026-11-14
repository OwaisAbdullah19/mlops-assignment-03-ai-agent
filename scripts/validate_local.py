"""Run a temporary real MLflow server, train candidates and export actual local evidence."""

import importlib.metadata
import json
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import psutil
from fastapi.testclient import TestClient


def main():
    root = Path.cwd()
    evidence = root / "evidence"
    runtime = root / ".runtime"
    evidence.mkdir(exist_ok=True)
    runtime.mkdir(exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    uri = f"http://127.0.0.1:{port}"
    os.environ["MLFLOW_TRACKING_URI"] = uri
    os.environ["MLFLOW_EXPERIMENT_NAME"] = "iris-training"
    os.environ["AGENT_PLANNER"] = "rules"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost," + os.environ.get("NO_PROXY", "")
    os.environ["DO_NOT_TRACK"] = "1"
    os.environ["MLFLOW_ENABLE_SYSTEM_METRICS_LOGGING"] = "false"
    backend = "sqlite:///" + (runtime / "validation-mlflow.db").as_posix()
    log_path = runtime / "mlflow-server.log"
    with log_path.open("w", encoding="utf-8") as logfile:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "mlflow",
                "server",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--backend-store-uri",
                backend,
                "--serve-artifacts",
                "--artifacts-destination",
                (runtime / "mlartifacts").as_uri(),
            ],
            stdout=logfile,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            with httpx.Client(trust_env=False) as client:
                for _ in range(90):
                    if process.poll() is not None:
                        raise RuntimeError(f"MLflow server exited; inspect {log_path}")
                    try:
                        if client.get(uri + "/health", timeout=1).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(1)
                else:
                    raise RuntimeError("Local MLflow server did not become ready")
            from mlflow import MlflowClient

            tracking = MlflowClient(tracking_uri=uri)
            experiment = tracking.get_experiment_by_name("iris-training")
            if experiment:
                # This helper owns this local database; preserve interrupted attempts as failures.
                interrupted = tracking.search_runs(
                    [experiment.experiment_id], filter_string="attributes.status = 'RUNNING'"
                )
                for run in interrupted:
                    tracking.set_tag(run.info.run_id, "training.interrupted_validation", "true")
                    tracking.set_terminated(run.info.run_id, status="FAILED")
            for c in (0.1, 1.0, 10.0):
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "training.train",
                        "--c",
                        str(c),
                        "--output",
                        f".runtime/candidate-{str(c).replace('.', '-')}",
                    ],
                    check=True,
                    timeout=180,
                )
            from scripts.capture_evidence import main as capture

            capture()
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.reproduce_data",
                    "--output",
                    f".runtime/reproduced-{uuid4().hex[:8]}",
                ],
                check=True,
                timeout=180,
            )
            from agent.config import Settings
            from agent.tools.mlflow_tools import MLflowTools

            best = MLflowTools(Settings()).best()["best"]
            subprocess.run(
                [sys.executable, "-m", "scripts.export_model", best["run_id"]], check=True, timeout=120
            )
            subprocess.run([sys.executable, "-m", "scripts.prepare_release"], check=True, timeout=30)
            from api.main import app

            os.environ["MODEL_PATH"] = "artifacts/model.joblib"
            os.environ["MODEL_METADATA_PATH"] = "artifacts/metadata.json"
            with TestClient(app) as inference:
                ready = inference.get("/health/ready")
                prediction = inference.post("/predict", json={"instances": [[5.1, 3.5, 1.4, 0.2]]})
                assert ready.status_code == 200 and prediction.status_code == 200
                assert prediction.json()["predictions"] == [0]
                metadata = inference.get("/metadata").json()
            versions = {
                name: importlib.metadata.version(name)
                for name in (
                    "mlflow",
                    "dvc",
                    "fastapi",
                    "pydantic",
                    "scikit-learn",
                    "numpy",
                    "pandas",
                    "httpx",
                    "SQLAlchemy",
                    "pathspec",
                    "pytest",
                    "ruff",
                )
            }
            result = {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "versions": versions,
                "tracking_kind": "real temporary local HTTP MLflow server with SQLite backend",
                "tracking_uri": uri,
                "server_stopped_after_capture": True,
                "inference_readiness_http": ready.status_code,
                "prediction": prediction.json(),
                "loaded_model_metadata": metadata,
                "live_airflow": False,
                "live_kubernetes": False,
                "live_ollama": False,
                "scope_note": "Airflow/Kubernetes unavailable; their exported evidence remains explicit errors.",
            }
            (evidence / "local-validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print("Local DVC, MLflow, model export and inference validation complete.")
        finally:
            # MLflow can launch a child HTTP server. Stop only this helper's descendants.
            try:
                children = psutil.Process(process.pid).children(recursive=True)
            except psutil.NoSuchProcess:
                children = []
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            _, alive = psutil.wait_procs(children, timeout=5)
            for child in alive:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass


if __name__ == "__main__":
    main()
