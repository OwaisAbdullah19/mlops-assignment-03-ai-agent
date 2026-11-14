# Evidence index

Files here are exported from actual local commands. Test fixtures in `tests/` are explicitly
mocked; they are never presented as live service results.

| Export | Meaning |
|---|---|
| `pytest.xml` | Executed automated test results |
| `dataset-reproduction.json` | Actual Git/DVC isolated-clone retrieval and checksum verification |
| `01-dataset.json` | Dataset inspection conversation and raw tool result envelopes |
| `02-model-selection.json` | Actual MLflow ranking conversation, metrics and provenance |
| `03-pipeline.json` | Actual Airflow query outcome; unavailable service is an error |
| `04-deployment.json` | Actual Kubernetes query outcome; unavailable cluster is an error |
| `05-multi-tool.json` | Cross-service conversation combining successful evidence with explicit unknowns |
| `failure-investigations.json` | Two deliberately executed local training failures |
| `capture-summary.json` | Per-scenario tool success/error index |
| `tool-audit.jsonl` | Structured tool name, status, duration and request ID logs |
| `local-validation.json` | Environment versions, local inference response and validation scope |

Re-run `python -m scripts.capture_evidence` after configuring live services. Successful
Airflow execution and Kubernetes rollout evidence must be captured on a machine with Docker
and a Kubernetes cluster. Current error results must not be described as successful deployments.
For pipeline execution, additionally capture the explicitly confirmed trigger response and
subsequent terminal DAG/task states. `capture_evidence` is deliberately read-only with respect
to external services and never launches a DAG or modifies a cluster.

Inspect exports before publication; remove credentials and sensitive operational details.
