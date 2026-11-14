"""Start, inspect, or stop workspace-owned hidden local demo processes."""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".runtime/local-services.json"
SERVICES = {
    "mlflow": {"port": 5000, "health": "/health", "module": "mlflow"},
    "inference": {"port": 8000, "health": "/health/ready", "module": "uvicorn"},
    "agent": {"port": 8001, "health": "/health", "module": "uvicorn"},
}
LLAMA = ROOT / ".runtime/llama/llama-server.exe"
MODEL = ROOT / ".runtime/models/qwen2.5-0.5b-instruct-q4_k_m.gguf"
if LLAMA.exists() and MODEL.exists():
    SERVICES["llm"] = {"port": 11434, "health": "/health", "module": "llama-server"}


def environment():
    env = os.environ.copy()
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", key.strip()):
                env[key.strip()] = value.strip()
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    env["NO_PROXY"] = "127.0.0.1,localhost," + env.get("NO_PROXY", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["DO_NOT_TRACK"] = "1"
    env["REPO_ROOT"] = str(ROOT)
    return env


def owned_process(record):
    try:
        process = psutil.Process(record["pid"])
        if abs(process.create_time() - record["created_at"]) > 0.1:
            return None
        if Path(process.cwd()).resolve() != ROOT:
            return None
        if process.cmdline() != record["command"]:
            return None
        return process
    except (psutil.Error, OSError):
        return None


def healthy(name):
    service = SERVICES[name]
    try:
        response = httpx.get(
            f"http://127.0.0.1:{service['port']}{service['health']}", timeout=2, trust_env=False
        )
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start", "status", "stop"), nargs="?", default="start")
    parser.add_argument("--service", choices=tuple(SERVICES), help="Operate on only this owned service")
    args = parser.parse_args()
    env = environment()
    selected = set(env.get("LOCAL_SERVICES", ",".join(SERVICES)).split(","))
    os.chdir(ROOT)
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if args.action == "stop":
        for name, record in list(state.items()):
            if args.service and name != args.service:
                continue
            process = owned_process(record)
            if process:
                children = process.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                process.terminate()
                _, alive = psutil.wait_procs([process, *children], timeout=5)
                for child in alive:
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                print(f"Stopped {name}")
            state.pop(name)
        STATE.write_text(json.dumps(state, indent=2))
        return
    if args.action == "start":
        logs = ROOT / ".runtime/services"
        logs.mkdir(parents=True, exist_ok=True)
        commands = {
            "mlflow": [
                "-m",
                "mlflow",
                "server",
                "--host",
                "127.0.0.1",
                "--port",
                "5000",
                "--backend-store-uri",
                "sqlite:///" + (ROOT / ".runtime/validation-mlflow.db").as_posix(),
                "--serve-artifacts",
                "--artifacts-destination",
                (ROOT / ".runtime/mlartifacts").as_uri(),
            ],
            "inference": ["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8000"],
            "agent": ["-m", "uvicorn", "agent.main:app", "--host", "127.0.0.1", "--port", "8001"],
        }
        if os.name != "nt":
            commands["mlflow"] += ["--workers", "1"]
        if "llm" in SERVICES:
            commands["llm"] = [
                str(LLAMA),
                "--model",
                str(MODEL),
                "--alias",
                "qwen2.5:0.5b",
                "--host",
                "127.0.0.1",
                "--port",
                "11434",
                "--ctx-size",
                "8192",
                "--parallel",
                "1",
                "--threads",
                "2",
                "--jinja",
                "--no-webui",
            ]
        for name, service in SERVICES.items():
            if args.service and name != args.service:
                continue
            if not args.service and name not in selected:
                continue
            if name in state and owned_process(state[name]) and healthy(name):
                continue
            with socket.socket() as sock:
                if sock.connect_ex(("127.0.0.1", service["port"])) == 0:
                    raise SystemExit(f"Port {service['port']} is already occupied; no process was stopped.")
            command = commands[name] if name == "llm" else [sys.executable, *commands[name]]
            with (logs / f"{name}.log").open("a", encoding="utf-8") as log:
                process = subprocess.Popen(
                    command,
                    cwd=ROOT,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            state[name] = {
                "pid": process.pid,
                "created_at": psutil.Process(process.pid).create_time(),
                "command": command,
            }
            STATE.write_text(json.dumps(state, indent=2))
            for _ in range(90):
                if process.poll() is not None:
                    raise SystemExit(f"{name} exited; inspect .runtime/services/{name}.log")
                if healthy(name):
                    break
                time.sleep(1)
            else:
                raise SystemExit(f"{name} is not ready; inspect .runtime/services/{name}.log")
    for name, service in SERVICES.items():
        if args.service and name != args.service:
            continue
        if not args.service and name not in selected:
            continue
        print(f"{name}: {'ready' if healthy(name) else 'unavailable'} http://localhost:{service['port']}")


if __name__ == "__main__":
    main()
