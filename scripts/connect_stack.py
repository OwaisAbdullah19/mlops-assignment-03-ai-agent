"""Privately configure authenticated local services; never print credential values."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]


def docker(*args):
    result = subprocess.run(
        [sys.executable, "-m", "scripts.wsl", "docker", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError("Local container command failed; inspect service health")
    return result.stdout.strip()


def update_env(values):
    path = ROOT / ".env"
    lines = path.read_text(encoding="utf-8").splitlines()
    for key, value in values.items():
        lines = [line for line in lines if not line.startswith(key + "=")]
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kubernetes", action="store_true")
    parser.add_argument("--airflow", action="store_true")
    args = parser.parse_args()
    if args.kubernetes:
        cluster = yaml.safe_load((ROOT / ".runtime/kubeconfig-linux").read_text())["clusters"][0]["cluster"]
        token = docker(
            "exec",
            "mlops-a3-k3s",
            "kubectl",
            "-n",
            "mlops-agent",
            "create",
            "token",
            "mlops-agent",
            "--duration=24h",
        )
        config = {
            "apiVersion": "v1",
            "kind": "Config",
            "clusters": [{"name": "assignment", "cluster": cluster}],
            "users": [{"name": "agent", "user": {"token": token}}],
            "contexts": [
                {
                    "name": "assignment",
                    "context": {"cluster": "assignment", "user": "agent", "namespace": "mlops-agent"},
                }
            ],
            "current-context": "assignment",
        }
        path = ROOT / ".runtime/kubeconfig-agent"
        path.write_text(yaml.safe_dump(config), encoding="utf-8")
        update_env({"KUBECONFIG": str(path)})
        print("Agent configured with namespace-scoped Kubernetes credentials (24 hours)")
    if args.airflow:
        users = json.loads(
            docker(
                "exec",
                "mlops-a3-airflow-1",
                "cat",
                "/opt/airflow/simple_auth_manager_passwords.json.generated",
            )
        )
        with httpx.Client(trust_env=False, timeout=30) as client:
            response = client.post(
                "http://localhost:8080/auth/token", json={"username": "admin", "password": users["admin"]}
            )
            response.raise_for_status()
            token = response.json()["access_token"]
            response = client.patch(
                "http://localhost:8080/api/v2/dags/ml_training",
                headers={"Authorization": "Bearer " + token},
                json={"is_paused": False},
            )
            response.raise_for_status()
        update_env(
            {
                "AIRFLOW_URL": "http://localhost:8080",
                "AIRFLOW_TOKEN": token,
                "MLFLOW_TRACKING_URI": "http://localhost:5002",
            }
        )
        print("Airflow authenticated, training DAG unpaused, agent connected to container MLflow")


if __name__ == "__main__":
    main()
