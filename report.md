# Technical report — Assignment 03

**Project:** Evidence-based MLOps AI Agent  
**Dataset/task:** Iris multiclass classification with a reproducible sklearn pipeline  
**Validation date:** 14 November 2026, Asia/Karachi

## System architecture

[architecture.md](architecture.md) documents the complete control flow, training lifecycle,
typed tool contracts and permissions. A conversational CLI and authenticated FastAPI control
API feed an evidence-collecting orchestrator. The tool registry dispatches to DVC/Git,
MLflow's Python client, authenticated Airflow 3 APIs, and Kubernetes's Python client.

There are two explicitly identified planning modes. The rule router supports the five
demonstration scenarios without an LLM. The Ollama mode performs real structured model tool
calling; unsupported or unavailable LLM responses cannot become operational facts. A fixed
cross-service workflow handles the mandatory integration request in both modes. Final
responses separate known facts, uncertainty, and recommended actions and attach evidence IDs.

## Implementation against the assessment

| Component | Delivered implementation | Validation |
|---|---|---|
| DVC (15) | Five read tools, historical Git pointer resolution, DVC hash comparison, status, diff, isolated reproduction script | Real local DVC evidence plus path/provenance tests |
| MLflow (15) | Six client tools, bounded recent-run ranking, metric direction, parameters/artifacts, registry versions, recorded data provenance | Real tracked training/ranking where configured; mocked failure/ranking tests |
| Airflow (15) | Airflow 3 JWT `/api/v2` client, five tools, five-stage TaskFlow DAG, retries and task diagnostics | Auth/path/failure tests; live DAG run remains environment-dependent |
| Kubernetes (15) | Six tools, namespace/app checks, confirmed restart, two-replica Deployment, ClusterIP, ConfigMap, resources and health probes | Health/restart/authorization tests; live rollout remains environment-dependent |
| Integration (15) | Mandatory four-service scenario, timestamped evidence, run-to-dataset/deployment correlation, policy-based retraining review | Cross-service and no-automatic-trigger tests; actual partial-service export |
| Reliability (10) | Pytest, timeouts, safe exception handling, structured audit, confirmation expiry/replay defense, injected failures | Executed test XML and failure exports |
| Repository/CI (5) | Pinned direct dependencies, local Git source, Dockerfiles, manifests, PR lint/format/test workflow | Local checks; remote push and hosted CI require a GitHub repository |
| Defense (10) | Architecture, tool permissions, five captured conversations, failure investigations, demo commands | Local evidence plus explicit remaining live demonstration steps |

This table describes coverage, not an awarded score. Successful live Airflow execution,
Kubernetes deployment, GitHub publication and an evaluator's engineering defense are separate
from local source implementation and automated tests.

## Dataset reproducibility and model selection

The bootstrap exports sklearn's Iris dataset and stores its content through DVC. A committed
pointer records the content hash. Each training evaluation records the pointer's Git commit,
DVC digest, dataset path and SHA-256, after checking actual bytes against that committed pointer.
An isolated clone retrieves the data from the configured remote and verifies the digest.
The JSON reproduction export is the source of truth for actual IDs; this report does not
substitute illustrative commit hashes.

The model is `StandardScaler` followed by deterministic `LogisticRegression`; an 80/20
stratified split uses seed 42. Metrics are macro F1 and accuracy. The ordinary quality threshold
is F1 >= 0.85. MLflow stores evaluation metrics, hyperparameters, model/split artifacts, and
quality metadata. The agent ranks the most recent five finished runs with finite metrics in
the configured experiment. It explains maximization/minimization and cautions that the
metric winner still needs quality, serving and rollout checks.

## Tool permissions and operational safety

All schemas reject extra arguments. The agent has no arbitrary shell tool. DVC/Git commands
use fixed argument lists, no shell execution, relative approved data paths and validated
revision syntax. MLflow tools are read-only. Airflow trigger accepts only the configured
training DAG and a restricted failure-injection setting. Kubernetes reads are scoped to the
configured namespace/application; restart is restricted to the configured Deployment.

Every mutation first returns an action proposal and an expiring single-use confirmation
capability. The authenticated operator must explicitly confirm it in the same server/CLI
session. The model cannot set consent in arguments or directly call the confirmation API.
RBAC restricts Kubernetes privileges independently. Secrets are supplied through environment
variables, and raw service exceptions are excluded from logs and responses.

## Five conversations and evidence

The exact prompts, generated answers and raw tool envelopes are in `evidence/01-*.json`
through `evidence/05-*.json`. These files are produced by actual tool calls, with error status
for unavailable infrastructure. They are not synthetic transcripts.

| Scenario | Operational question | Evidence and interpretation |
|---|---|---|
| Dataset provenance | Which version is tracked and how is it reproduced? | Committed DVC hash, Git reference, status and isolated retrieval export |
| Model selection | Compare recent runs by F1 | Recorded MLflow run metrics, parameters, provenance and selected candidate |
| Pipeline execution/status | What is the training workflow state? | Airflow result envelope; successful run/task evidence requires live Airflow and a separately confirmed trigger |
| Deployment diagnosis | Why is the prediction API unavailable? | Kubernetes result envelope; Pod/log/event results require a configured cluster |
| Multi-tool reasoning | Best model + dataset + deployment + retraining? | All four integrations are called; missing service results remain unknown and retraining is not triggered |

To complete the live demonstration, run the README's Compose and Kubernetes commands,
confirm an approved training request, wait for terminal DAG/task states, verify two ready
replicas and `/metadata`, and refresh the evidence exports. Optional screenshots belong in
`screenshots/`; exported JSON is acceptable evidence under the assignment.

## Failure investigation 1: validation failure

**Injection:** `failure=validation` makes validation raise a controlled missing-feature
diagnostic. The local capture executes this failure and records its exception. Tests verify
the validation error path; the Airflow DAG uses `all_success` dependencies so later stages
cannot train or promote after this failure.

**Root cause:** The deliberately injected schema validation condition, before model fitting.
This is distinguishable from an MLflow outage or an unhealthy inference Pod.

**Diagnosis:** Query the recent failed DAG run, retrieve task instances, identify `validation`
as failed, then read its log. For a live Airflow run, the agent's returned tool evidence
must show those task states before claiming a pipeline diagnosis.

**Resolution:** Remove the injection, validate the source schema and rerun the approved DAG
with confirmation. A normal local training run validates successfully; live recovery must
be checked from the resulting Airflow task states.

## Failure investigation 2: quality gate failure

**Injection:** `failure=quality` keeps real model metrics but sets a deliberately impossible
minimum F1 of 1.01. Evaluation remains observable while `quality_gate` raises an error.

**Root cause:** An explicit threshold policy failure, not an invented degradation result.
No approved artifact is created, and a failed-quality model is not registered or served.
Any older approval is removed before rerun so it cannot survive a failed attempt.

**Diagnosis:** Read MLflow's actual F1 and `quality.passed=false`, then inspect the failed
Airflow `quality_gate` task and its log if live Airflow is available. The local failure export
records the actual measured score, threshold and absence of an approval artifact.

**Resolution:** Restore the normal 0.85 policy for this controlled test and rerun. In a real
quality regression, investigate data, features and parameters before requesting retraining;
never lower a legitimate gate solely to permit deployment.

## Known limitations and improvements

The delivered local evidence must be read with its explicit service statuses. Docker and
kubectl are absent from the validation machine, so a successful live Airflow/Kubernetes
demonstration is not claimed. No GitHub remote or credentials were provided, so publication
and hosted CI results are not claimed. Ollama planner behavior is covered using mocked
structured responses; a live downloaded model is required to demonstrate LLM planning.

The reference Python environment uses pinned direct dependencies; transitive dependency
locking and container image digest pinning would strengthen reproducibility. The local DVC
remote is not shared storage. Confirmation capabilities are process-local and do not support
multiple workers. The Compose stack uses local standalone Airflow and an educational MLflow
deployment, not a production topology. Drift detection, richer telemetry, distributed
confirmation storage, federated identity and immutable model/image promotion are next steps.

## Engineering defense prompts

- Why record both Git commit and DVC digest? Git identifies the pointer/source revision;
  the content digest identifies dataset bytes. Neither should be guessed from today's workspace.
- Why separate liveness and readiness? A live process can lack a usable model; readiness
  prevents routing traffic while preserving useful diagnostics.
- Why does highest F1 not imply production readiness? Quality policy, compatibility,
  freshness, serving identity and rollout health remain separate evidence requirements.
- Why not retrain for a Pod outage? Probe failures, resource exhaustion and image errors
  can be infrastructure problems; retraining lacks support without model/data evidence.
- How is unauthorized restart prevented? Typed arguments, independent namespace/application
  validation, explicit single-use human confirmation, and namespace-scoped RBAC.
