# Assignment 03 — Evidence-based MLOps AI Agent

A Python agent that inspects DVC dataset provenance, ranks MLflow experiments, operates an
approved Airflow 3 training DAG, and diagnoses a Kubernetes inference application. Tool
results drive every operational claim. State changes require separate explicit confirmation.

Start with [the technical report](report.md), [architecture and tool permissions](architecture.md),
and [the evidence index](evidence/README.md) for implementation and validation status.

## Install

Use Python **3.11** for the reference environment. Airflow runs in Linux containers, including
on Windows via Docker Desktop/WSL2. Docker, Git, kubectl and a local Kubernetes cluster
(kind or minikube) are prerequisites for the full demonstration. A GPU is unnecessary for
training the Iris classifier. Ollama needs a downloaded tool-capable model for LLM planning.

Run from the repository root in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m scripts.configure_demo
. .\scripts\env.ps1
```

On Linux/macOS, use `python3.11`, `source .venv/bin/activate`, and load the generated dotenv
file using `set -a; source .env; set +a`. All commands below run from the repository root.
The project pins direct Python dependencies in `pyproject.toml`; Airflow is pinned separately
in `Dockerfile.airflow`. The checked-in validation evidence records the environment actually
used for local checks. Do not copy this workspace's virtualenv to another machine.
`pathspec` is pinned to 0.12.1 because DVC 3.63.0 uses an internal symbol removed in newer releases.

## Version and reproduce the dataset

`training.data` exports sklearn's built-in 150-row Iris dataset; it does not download data.
The bootstrap configures a private workspace-local DVC remote for a self-contained demo.

```powershell
python -m scripts.init_data
git add .
git commit -m "Implement MLOps agent and version Iris dataset"
python -m scripts.reproduce_data
```

If a commit already exists in this delivered workspace, use it; only commit new changes.
Set your own Git identity if Git requests it. The reproduction script requires a new output
directory and exports the actual commit, data digest and verification result. For another
revision, use `python -m scripts.reproduce_data --revision COMMIT --output .runtime/reproduced-v2`.
`dvc diff --json OLD_COMMIT NEW_COMMIT` compares data versions. To create a second data version,
edit the CSV, run `dvc add data/iris.csv`, `dvc push`, and commit its updated pointer. Historical
cache objects remain in the remote. Configure a shared DVC object-storage remote for collaboration;
the local remote and data cache are intentionally excluded from Git.

## Launch MLflow and Airflow 3

The generated `.env` supplies random PostgreSQL, Fernet and JWT values. Never commit it.

```powershell
docker compose up -d --build
docker compose logs airflow
docker compose exec airflow cat /opt/airflow/simple_auth_manager_passwords.json.generated
```

Open MLflow at `http://localhost:5000` and Airflow at `http://localhost:8080`. Use the generated
Airflow password locally. Do not export that password in screenshots or evidence. The local
Airflow SimpleAuthManager uses `admin` with the `admin` role. The standalone process starts the
API server, scheduler, DAG processor and triggerer against PostgreSQL. Wait for the DAG
`ml_training` to appear; unpause it in the UI. Compose's endpoints bind only to loopback.

Retrieve an authenticated Airflow 3 JWT:

```powershell
python -m scripts.airflow_token
# Set AIRFLOW_TOKEN to the printed JWT in this shell; never commit or screenshot it.
$env:AIRFLOW_TOKEN = 'YOUR_LOCAL_JWT'
```

The helper calls `/auth/token`; the integration uses bearer-authenticated `/api/v2` endpoints.
Refresh the token after expiry. Airflow training accesses MLflow at `http://mlflow:5000`, while
host processes use `http://localhost:5000`. Do not replace one with the other.

For a local MLflow-only run without Docker:

```powershell
mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///.runtime/mlflow.db --serve-artifacts --artifacts-destination .runtime/mlartifacts
```

In another activated shell, create several actual experiment candidates:

```powershell
python -m training.train --c 0.1 --output .runtime/candidate-01
python -m training.train --c 1.0 --output .runtime/candidate-10
python -m training.train --c 10.0 --output .runtime/candidate-100
```

Training verifies the committed DVC pointer. Each run logs F1, accuracy, parameters, data
provenance and artifacts; only quality-approved models enter the registry. `python -m
training.train --no-track` verifies local training without claiming an MLflow run. `dvc repro`
runs the tracked training stage with MLflow enabled and records a DVC pipeline lock.

## Start and use the agent

The deterministic scenario router works without an LLM and is identified as `rules` in every
response. To enable **actual LLM tool calling**, install and start Ollama, pull a tool-capable
model (for example `ollama pull qwen3:8b`), and set:

```powershell
$env:AGENT_PLANNER = 'ollama'
$env:OLLAMA_MODEL = 'qwen3:8b'
```

The agent calls Ollama's `/api/chat` with generated JSON tool schemas. Configure `OLLAMA_URL`
if it is not local. The mandatory cross-service scenario uses an explicit collection workflow
in either mode. LLM downtime is reported as uncertainty, without an invented answer.

Interactive CLI retains pending confirmation capabilities in the same process:

```powershell
python -m agent.main
```

Ask these five demonstration questions:

1. `Which dataset version is currently tracked, and how can I reproduce it?`
2. `Compare the last five training runs and recommend the best model by F1`
3. `Trigger the model training pipeline`
4. `Why is my prediction API unavailable?`
5. `Find the best recent model, identify the dataset version used to train it, check the deployment status, and explain whether retraining is necessary`

For scenario 3, review the proposed DAG and arguments, then type `confirm TOKEN` using the
returned capability. Ask `Report training pipeline status and diagnose failed tasks` until
the run is terminal. Trigger acknowledgement is never reported as successful completion.
One-shot read/proposal example: `python -m agent.main --message "Find the best model by F1"`.
One-shot proposals cannot be confirmed in another process; use the interactive CLI or HTTP.

Authenticated HTTP service (one worker preserves confirmation state):

```powershell
uvicorn agent.main:app --host 127.0.0.1 --port 8001
```

From another shell with the same environment:

```powershell
$headers = @{ Authorization = "Bearer $env:AGENT_API_TOKEN" }
$body = @{ message = 'Trigger the model training pipeline' } | ConvertTo-Json
$proposal = Invoke-RestMethod http://localhost:8001/chat -Method Post -Headers $headers -ContentType application/json -Body $body
$proposal.pending_actions
# After reviewing and explicitly approving the displayed action:
$confirmation = @{ token = $proposal.pending_actions[0].confirmation_token } | ConvertTo-Json
Invoke-RestMethod http://localhost:8001/confirm -Method Post -Headers $headers -ContentType application/json -Body $confirmation
```

`GET /tools` exposes typed contracts; `GET /health` is a public process health check.
Invalid credentials return 401, invalid requests 422, expired/reused confirmations 403.
Ordinary integration errors are returned inside evidence envelopes so partial results survive.

## Build and deploy inference

Choose a finished, quality-approved MLflow run from the agent's recorded results. Replace
`YOUR_RUN_ID` with that actual ID. Export creates an approved model bundle and a release file
declaring its identity; these commands do not modify the cluster:

```powershell
python -m scripts.export_model YOUR_RUN_ID
python -m scripts.prepare_release
$metadata = Get-Content artifacts/metadata.json | ConvertFrom-Json
$modelTag = $metadata.run_id.Substring(0, 12)
docker build -t "mlops-inference:$modelTag" .
kind create cluster --name mlops-a3
kind load docker-image "mlops-inference:$modelTag" --name mlops-a3
```

Review the manifests, select the intended local cluster, and explicitly apply the deployment:

```powershell
kubectl config current-context
kubectl apply -f kubernetes/namespace.yaml
kubectl apply -f .runtime/release.yaml
kubectl apply -f kubernetes/service.yaml
kubectl apply -f kubernetes/rbac.yaml
kubectl -n mlops-agent rollout status deployment/iris-api --timeout=120s
kubectl -n mlops-agent get pods,deployments,services
kubectl -n mlops-agent port-forward service/iris-api 8000:80
```

Use a restricted kubeconfig or the supplied namespaced ServiceAccount for the agent; do not
use cluster-admin credentials in a shared deployment. The agent loads in-cluster configuration
first, then kubeconfig. The manifests specify two replicas, ClusterIP, ConfigMap, resource
requests/limits, readiness/liveness probes, and a non-root container. The image contains the
verified model bundle. It does not train a model on startup.

```powershell
Invoke-RestMethod http://localhost:8000/health/ready
Invoke-RestMethod http://localhost:8000/metadata
Invoke-RestMethod http://localhost:8000/predict -Method Post -ContentType application/json -Body '{"instances":[[5.1,3.5,1.4,0.2]]}'
```

To run inference without Kubernetes: export/train a quality-approved bundle into `artifacts/`,
then `uvicorn api.main:app --host 127.0.0.1 --port 8000`. Missing, corrupt, or rejected models
leave readiness at 503. `/metadata` reports the loaded model identity separately from declared
Deployment annotations.

## Verify, inject failures, and capture evidence

```powershell
ruff check .
ruff format --check .
pytest -q --junitxml=evidence/pytest.xml
python -m scripts.capture_evidence
```

Ordinary tests mock external services. They also train and exercise a real classifier locally.
On a restricted Windows runner, pytest may need a writable `--basetemp` directory. The evidence
capture makes actual tool calls and records explicit service errors when infrastructure is
unavailable. It does not replace live Airflow/Kubernetes evidence with mocks.

Two deliberately injected training failures can be exercised through the confirmed DAG:

- Ask `Trigger training with validation failure`; confirm the proposal. `validation` fails,
  later stages remain unexecuted/upstream_failed. Inspect task states and logs.
- Ask `Trigger training with quality failure`; confirm it. Evaluation records real metrics,
  while the deliberately impossible F1 threshold 1.01 fails `quality_gate`; no approval exists.

The capture script also executes both failures locally and exports their real exceptions.
Repair by triggering the normal DAG configuration, then confirm its final task states.
For deployment diagnosis, a missing model reports readiness 503; inspect probes, Pod conditions,
events and logs. Do not infer that retraining fixes infrastructure failures.

`python -m scripts.validate_local` performs the complete local verification: it starts a
temporary real MLflow HTTP server, trains three candidates, captures the five conversations,
retrieves a DVC dataset in a new clone, exports a verified model, and tests inference. It stops
its temporary server afterward. The persisted runs are in `.runtime/validation-mlflow.db`,
and model artifacts remain available in `artifacts/`. This helper does not start Airflow,
create a cluster, or modify Kubernetes.

## Repository and submission

Source lives in `agent/`, `api/`, `training/`, and `dags/`; infrastructure is in `kubernetes/`,
Dockerfiles, and `compose.yaml`. GitHub Actions runs lint, formatting and pytest on pull
requests. [report.md](report.md) maps implementation to the assessment requirements and
lists remaining live demonstration steps. Evidence exports are in `evidence/`; optional
screenshots belong in `screenshots/` after removing credentials.

Push this reviewed repository to your own GitHub remote. No remote account or repository
name is assumed. Before submission, launch Airflow and Kubernetes, execute and confirm a real
DAG run, re-run evidence capture, and include live task and deployment status. Existing error
exports honestly show the limits of the local validation session.
