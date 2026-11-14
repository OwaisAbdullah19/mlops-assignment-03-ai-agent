# Technical report — Assignment 03

**Project:** Evidence-based MLOps AI Agent  
**Dataset/task:** Iris multiclass classification with a reproducible sklearn pipeline  
**Validation date:** 14 November 2026, Asia/Karachi

## System architecture

[architecture.md](architecture.md) documents the complete control flow, training lifecycle,
typed tool contracts and permissions. A conversational CLI and authenticated FastAPI control
API feed an evidence-collecting orchestrator. The tool registry dispatches to DVC/Git,
MLflow's Python client, authenticated Airflow 3 APIs, and Kubernetes's Python client.

There are three explicitly identified planning modes. The rule router supports the five
demonstration scenarios without an LLM. Ollama and llama.cpp perform structured model tool
calling. The prepared CPU demo uses verified Qwen2.5 0.5B GGUF and llama.cpp b12375;
`live-llm-demo.json` records a successful real model-selected MLflow experiments query.
`live-llm-http-demo.json` records the authenticated natural-language question "Which
experiments are available in MLflow?" and the model-selected `mlflow_experiments` result.
Unsupported or unavailable LLM responses cannot become operational facts. A fixed
cross-service workflow handles the mandatory integration request in every mode. Final
responses separate known facts, uncertainty, and recommended actions and attach evidence IDs.

## Implementation against the assessment

| Component | Delivered implementation | Validation |
|---|---|---|
| DVC (15) | Five read tools, historical Git pointer resolution, DVC hash comparison, status, diff, isolated reproduction script | Real local DVC evidence plus path/provenance tests |
| MLflow (15) | Six client tools, bounded recent-run ranking, metric direction, parameters/artifacts, registry versions, recorded data provenance | Real tracked training/ranking where configured; mocked failure/ranking tests |
| Airflow (15) | Airflow 3 JWT `/api/v2` client, five tools, five-stage TaskFlow DAG, retries and task diagnostics | Real successful five-stage DAG, two injected failed DAGs, retries, blocked downstream tasks and failure logs |
| Kubernetes (15) | Six tools, namespace/app checks, confirmed restart, two-replica Deployment, ClusterIP, ConfigMap, resources and health probes | Real two-replica rollout, served model/prediction, namespace RBAC denial and authorization tests |
| Integration (15) | Mandatory four-service scenario, timestamped evidence, run-to-dataset/deployment correlation, policy-based retraining review | Live service exports plus cross-service and no-automatic-trigger tests |
| Reliability (10) | Pytest, timeouts, safe exception handling, structured audit, confirmation expiry/replay defense, injected failures | Executed test XML and failure exports |
| Repository/CI (5) | Pinned direct dependencies, Git source, Dockerfiles, manifests, PR lint/format/test workflow | Private GitHub repository published; hosted Python 3.11 lint/format/tests passed |
| Defense (10) | Architecture, tool permissions, five captured conversations, failure investigations, demo commands | Local evidence plus explicit remaining live demonstration steps |

This table describes coverage, not an awarded score. Successful live Airflow execution,
Kubernetes deployment, GitHub publication and an evaluator's engineering defense are separate
from local source implementation and automated tests.

## Measured local results

The actual Windows validation environment used Python 3.13.9 with the pinned project
dependencies. `pytest` completed **35 tests successfully**; Ruff lint/format checks, parsing
of all eight infrastructure/CI YAML files, and `pip check` passed. Six dependency warnings
(Starlette/AnyIO deprecation and sklearn/SciPy optimizer-option warnings) were reported;
they did not fail the tests. Docker inference and successful hosted CI use Python 3.11.

A real temporary HTTP MLflow server recorded these finished candidates:

| Logistic regression C | MLflow run ID | Macro F1 | Accuracy |
|---|---|---|---|
| 0.1 | `df8eaacfb78249409fce94a031b82d2e` | 0.865320 | 0.866667 |
| 1.0 | `de3c8116f7314c4caf07c3a979d0f584` | 0.933333 | 0.933333 |
| 10.0 | `ce387cbddbdb48fa82cb5c62d189b09e` | 1.000000 | 1.000000 |

The winner was exported from MLflow, checksum-verified, loaded into FastAPI, and returned
readiness HTTP 200 and prediction `[0]` (setosa) for `[5.1, 3.5, 1.4, 0.2]`. The perfect
score covers only this 30-example Iris holdout; it does not establish production readiness.
Two earlier interrupted artifact-upload attempts remain recorded as FAILED and are excluded
from candidate selection. The temporary HTTP server was stopped after evidence collection.

The recorded database and artifacts were migrated using a consistent SQLite snapshot to
the isolated Docker MLflow service on port 5002. The winner is served by two ready K3s
replicas, with matching declared and loaded run identity. Live `/metadata` and `/predict`
requests returned HTTP 200. Actual Pod restart counts are retained in the evidence. The agent uses a namespaced
service account: a real request to list Pods in `default` returned HTTP 403. The deployment,
prediction, RBAC denial and LLM runtime/model digests have separate live evidence exports.

The isolated DVC clone retrieved digest `4224576f0267bf88902f87f0f6200967` and verified
that the retrieved file matches its committed pointer. Dataset status checks target the
dataset's `.dvc` file, so a training stage without a `dvc.lock` is not mistaken for changed
CSV contents. Full measurements and environment versions are in
[`evidence/local-validation.json`](evidence/local-validation.json).

Real integration checks also found and resolved DVC's incompatible newer `pathspec`,
MLflow's incompatible SQLAlchemy 2.1 pool import, a Windows artifact-directory path requiring
a `file:` URI, and Windows console encoding for MLflow's Unicode messages. These corrections
were verified through dataset retrieval, actual artifact upload/download and inference.

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
| Pipeline execution/status | What is the training workflow state? | Actual failed DAGs, task states, three-attempt retries and original failure logs |
| Deployment diagnosis | Why is the prediction API unavailable? | Actual two-ready-replica state; the agent does not invent an outage when the service is healthy |
| Multi-tool reasoning | Best model + dataset + deployment + retraining? | All four integrations are called; missing service results remain unknown and retraining is not triggered |

The setup operator submitted three reviewed proposals through the agent API and separately
confirmed each exact action for the user-requested demonstration. No model self-approved a
mutation. `evidence/live-pipeline-executions.json` contains the accepted trigger responses,
terminal DAG/task states and failure logs, without confirmation capabilities:

| Failure setting | Actual Airflow DAG run | Terminal result |
|---|---|---|
| none | `agent__67f959bfee9448c9acb5f47cbfaa849d` | Success; all five stages succeeded on attempt 1 |
| validation | `agent__3fe7c824bf6d4ea1b42111608b6c4d17` | Validation failed on attempt 3; all four downstream stages were upstream_failed |
| quality | `agent__8f8761ce860c4d0d88b51674064dfbb1` | Evaluation completed; quality gate failed on attempt 3 |

The quality demonstration's first evaluation attempt encountered a real ten-second
`git rev-parse HEAD` timeout under resource pressure. Its configured retry succeeded;
`live-evaluation-retry.json` preserves the original diagnostic. No run was retriggered to
hide that failure. Exported JSON is accepted assignment evidence; screenshots are optional.

## Failure investigation 1: validation failure

**Injection:** `failure=validation` makes validation raise a controlled missing-feature
diagnostic. The local capture executes this failure and records its exception. Tests verify
the validation error path; the Airflow DAG uses `all_success` dependencies so later stages
cannot train or promote after this failure.

**Root cause:** The deliberately injected schema validation condition, before model fitting.
This is distinguishable from an MLflow outage or an unhealthy inference Pod.

**Diagnosis:** Query the recent failed DAG run, retrieve task instances, identify `validation`
as failed, then read its log. The live export shows validation failed after three attempts
and all downstream stages blocked. Diagnostic selection filters actual failed tasks before
applying its two-task log limit, so upstream_failed entries cannot hide the original cause.

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
Airflow `quality_gate` task and its log. The live log records `F1=0.9333 < 1.01` on the
third failed attempt. The local failure export also records the measured score, threshold
and absence of an approval artifact.

**Resolution:** Restore the normal 0.85 policy for this controlled test and rerun. In a real
quality regression, investigate data, features and parameters before requesting retraining;
never lower a legitimate gate solely to permit deployment.

## Known limitations and improvements

The prepared environment uses the existing Ubuntu WSL2 Docker Engine and a dedicated
K3s v1.33.3 cluster. Kubernetes and llama.cpp have real successful evidence exports;
Ollama's native protocol is covered by a mocked contract test. The small CPU model was
tested on MLflow lookup requests, including natural-language HTTP selection, rather than a
broad language-understanding benchmark.
Cold prompt processing can take minutes; the prepared LLM timeout is 360 seconds and
generation is bounded. The private repository is published at
[OwaisAbdullah19/mlops-assignment-03-ai-agent](https://github.com/OwaisAbdullah19/mlops-assignment-03-ai-agent).
`evidence/github-ci.json` records the actual successful hosted CI run and its checked commit.

An unexpected deployment failure provided a practical diagnosis exercise: Pods initially
remained Pending with the event `node.cloudprovider.kubernetes.io/uninitialized`. The local
cluster has no cloud provider; removing that retained bootstrap taint allowed scheduling.
Initial liveness probes then killed slow cold-start imports. A startup probe gates liveness
for up to five minutes, and numerical libraries use one thread. The final replacement Pods
became ready. Unused Helm/cloud controllers were disabled for this local
cluster after their startup retries. Events, readiness checks and final model identity,
rather than a successful `apply` command alone, established recovery.

The reference Python environment uses pinned direct dependencies; transitive dependency
locking and container image digest pinning would strengthen reproducibility. The local DVC
remote is not shared storage. Confirmation capabilities are process-local and do not support
multiple workers. The Compose stack uses local standalone Airflow and an educational MLflow
deployment, not a production topology. Drift detection, richer telemetry, distributed
confirmation storage, federated identity and immutable model/image promotion are next steps.

The laptop's existing WSL configuration limits Linux to 4 GB without swap; global settings
were preserved. Cold-start resource pressure caused a real MLflow Gunicorn worker timeout.
The final configuration uses one worker with a 120-second server limit and bounded 60-second
agent requests. A 15-second job heartbeat gives the DAG processor a health interval suited
to the observed delays. Transient failed captures remain in `resource-timeouts.json` rather
than being misrepresented as successful results. The launcher also retains an owned WSL
session so background systemd services are not lost between commands.

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
