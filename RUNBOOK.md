# Assignment 03: commands and demonstration guide

Use this guide on the **prepared Lenovo laptop**, in **VS Code -> Terminal -> PowerShell**.
Run commands one block at a time and wait for each command to finish. These instructions
reuse the existing environment, data, models, containers, and cluster. A fresh-machine
installation is covered in [README.md](README.md).

## 1. Open the project

```powershell
cd "C:\Users\Lenovo\Desktop\mlops a3"
$py = ".\.venv\Scripts\python.exe"
```

Repeat this block whenever you open a new terminal. `$py` is a shortcut to the project's
Python; you do not need to activate the virtual environment.

## 2. Start the services after a reboot

Keep Ubuntu WSL running:

```powershell
& $py -m scripts.local_services start --service wsl
```

Start PostgreSQL, MLflow, and Airflow:

```powershell
& $py -m scripts.wsl env MLFLOW_PUBLISHED_PORT=5002 docker compose -p mlops-a3 up -d
```

Start the existing Kubernetes cluster and wait for its node:

```powershell
& $py -m scripts.wsl bash scripts/setup_kubernetes.sh
```

Refresh the short-lived Kubernetes and Airflow credentials. This also unpauses the training DAG:

```powershell
& $py -m scripts.connect_stack --kubernetes --airflow
```

Restart the agent to load the refreshed credentials, and start the local language model:

```powershell
& $py -m scripts.local_services stop --service agent
& $py -m scripts.local_services start
```

Allow several minutes for cold startup. These commands keep credentials in the private
local configuration; you do not need to copy tokens.

## 3. Check that everything is reachable

```powershell
& $py -m scripts.status
```

Expected: each service has `"http_status": 200`. Also inspect Airflow's response for
healthy scheduler, metadata database, DAG processor, and triggerer components.

| Service | Prepared address | Purpose |
|---|---|---|
| Agent API | http://localhost:8001/docs | Chat, tools, and confirmation endpoints |
| Local language model | http://localhost:11434/health | LLM health; no chat web page |
| MLflow | http://localhost:5002 | Experiments, model metrics, parameters, artifacts |
| Airflow | http://localhost:8080 | DAG graph, runs, task states, and logs |
| Prediction API | http://localhost:8002/docs | Model metadata, health, and predictions |

If the inference endpoint on port 8002 is unreachable after a cluster restart, restore
its forwarding process:

```powershell
& $py -m scripts.wsl docker exec -d mlops-a3-k3s kubectl -n mlops-agent port-forward service/iris-api 8002:80 --address 0.0.0.0
& $py -m scripts.status
```

Skip that forwarding command if port 8002 already works.

## 4. Check Kubernetes and make a prediction

Check the node and application:

```powershell
& $py -m scripts.wsl docker exec mlops-a3-k3s kubectl get nodes
& $py -m scripts.wsl docker exec mlops-a3-k3s kubectl -n mlops-agent get deployments,pods,services
```

Expected: the node is `Ready`, the `iris-api` Deployment has `2/2` ready replicas,
the application Pods are ready, and the Service is `ClusterIP`.

Check readiness and the identity of the loaded model:

```powershell
Invoke-RestMethod http://localhost:8002/health/ready
Invoke-RestMethod http://localhost:8002/metadata
```

Make a prediction:

```powershell
Invoke-RestMethod `
  -Uri http://localhost:8002/predict `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"instances":[[5.1,3.5,1.4,0.2]]}'
```

The previously verified prediction for this sample was class `0`, setosa. The metadata
identifies the actual loaded MLflow run; compare it with MLflow and the Deployment annotation.

```powershell
& $py -m scripts.wsl docker exec mlops-a3-k3s kubectl -n mlops-agent get deployment iris-api -o 'jsonpath={.spec.template.metadata.annotations}'
```

## 5. Open MLflow and Airflow

Open the pages in your browser:

```powershell
Start-Process "http://localhost:5002"
Start-Process "http://localhost:8080"
Start-Process "http://localhost:8002/docs"
```

In MLflow, open `iris-training`. Inspect the runs' F1, accuracy, `C` parameter,
artifacts, dataset tags, and quality status. The best metric alone does not establish
that a model is safe to deploy.

Airflow's username is `admin`. Retrieve its generated password locally:

```powershell
& $py -m scripts.wsl docker compose -p mlops-a3 exec airflow cat /opt/airflow/simple_auth_manager_passwords.json.generated
```

Keep this password out of shared screenshots. In Airflow, open `ml_training` and inspect
its graph, run history, task attempts, and logs.

## 6. Run the mandatory cross-service question

```powershell
& $py -m scripts.demo
```

This asks for the best recent model, its recorded dataset version, deployment status,
recent workflow state, and whether retraining is necessary. It queries all four integrations.
It must distinguish facts from uncertainty and must not automatically start retraining.

This command updates `evidence/latest-demo.json` with the actual response.

Test actual language-model tool selection separately:

```powershell
& $py -m scripts.demo --message "Which experiments are available in MLflow?"
```

The prepared HTTP agent uses llama.cpp with Qwen2.5 0.5B. Cold CPU inference can take
several minutes, and this small model may choose the wrong tool. The mandatory cross-service
question uses an explicit evidence-collection workflow in every planner mode.

## 7. Open interactive chat

For the prepared LLM chat:

```powershell
& $py -m scripts.chat
```

Alternatively, double-click `Chat.cmd`. Type `exit` to leave the chat.

For a predictable walkthrough of the five predefined scenarios, use the **rules planner**:

```powershell
. .\scripts\env.ps1
$env:AGENT_PLANNER = "rules"
& $py -m agent.main
```

This explicitly uses deterministic routing, not LLM reasoning. It still executes actual
integration tools. It changes the planner only for this terminal's directly launched process;
it does not change `.env` or the running HTTP agent.

If PowerShell blocks `env.ps1`, allow scripts for this terminal session, then retry:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### Enter these prompts inside chat, not in PowerShell

**Conversation 1: dataset provenance**

```text
Which dataset version is currently tracked, and how can I reproduce it?
```

Look for the recorded Git reference, DVC content digest, dataset status, and reproduction steps.

**Conversation 2: model comparison**

```text
Compare the last five training runs and recommend the best model by F1
```

Look for actual run IDs, recorded metrics, selection scope, and quality cautions.

**Conversation 3: start training**

```text
Trigger the model training pipeline
```

Review the proposed DAG and arguments. To execute that exact proposal, type:

```text
confirm PASTE_THE_RETURNED_CONFIRMATION_TOKEN_HERE
```

Use the actual token from the response in the same chat session. Tokens are single-use
and expire after 120 seconds. If it expires, request a new proposal and review it again.

Then ask:

```text
Report training pipeline status and diagnose failed tasks
```

Repeat the status question until the run finishes. An accepted trigger is not proof of
successful training. Check the new run in Airflow; the normal run should finish with all
five tasks successful.

**Conversation 4: deployment diagnosis**

```text
Why is my prediction API unavailable?
```

The agent should investigate the deployment. If the application is healthy, it should report
that rather than invent an outage.

**Conversation 5: combine all four systems**

```text
Find the best recent model, identify the dataset version used to train it, check the deployment status, and explain whether retraining is necessary
```

Check that the answer connects MLflow, recorded DVC provenance, Kubernetes, and Airflow.

## 8. Demonstrate the two intentional failures

Use the same interactive rules-planner session from step 7. These commands deliberately
create failed test runs; the failed runs should remain visible as diagnostic evidence.

### Failure A: validation

Enter:

```text
Trigger training with validation failure
```

Review the proposal, then enter `confirm` followed by its actual token. Ask:

```text
Report training pipeline status and diagnose failed tasks
```

Expected: `validation` fails after up to three attempts. The other four tasks are
`upstream_failed`, and no approved model is produced. Inspect the validation task's log.

### Failure B: quality gate

After the first run is terminal, enter:

```text
Trigger training with quality failure
```

Review and confirm the new proposal. Ask for pipeline status again until it is terminal.

Expected: real training and evaluation execute, but `quality_gate` fails because this test
uses an impossible F1 threshold of `1.01`. No model is approved by that run.

### Demonstrate recovery

Enter:

```text
Trigger the model training pipeline
```

Review and confirm it. Check the new run until all five tasks succeed. The normal threshold
is F1 >= `0.85`; an injected failure does not justify changing a legitimate production policy.

Finish the chat:

```text
exit
```

## 9. Check DVC and automated tests

Back in PowerShell, inspect the committed dataset pointer and current data status:

```powershell
Get-Content data/iris.csv.dvc
& $py -m dvc status data/iris.csv.dvc
```

Expected: the tracked dataset is unchanged.

Run lint, formatting checks, and tests:

```powershell
& $py -m ruff check .
& $py -m ruff format --check .
& $py -m pytest -q -p no:cacheprovider --basetemp "$env:TEMP\mlops-a3-check-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

The last verified result was **35 passed**. Check your new result rather than assuming it
will match. Test repositories are created in the system temporary directory, so they do not
appear as nested Git repositories in the VS Code project. These tests include mocks and local
real training; they do not replace the live service checks above.

### Optional: prove dataset reproduction again

This retrieves the committed dataset in a new isolated clone and checks its digest:

```powershell
. .\scripts\env.ps1
& $py -m scripts.reproduce_data --output "$env:TEMP\mlops-a3-data-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

Expected: `"matches": true`. This updates `evidence/dataset-reproduction.json`.

## 10. Optional: refresh exported evidence

Run this only after the services work. It updates the five conversation exports, audit log,
capture summary, and local failure investigations. Those local failure investigations are
separate from the real Airflow failures you demonstrated in step 8.

```powershell
. .\scripts\env.ps1
$env:AGENT_PLANNER = "rules"
& $py -m scripts.capture_evidence
& $py -m scripts.demo
```

Inspect the new exports. A service error must remain an error, not be described as a success.
Existing `live-pipeline-executions.json` records the previously demonstrated run IDs; it does
not automatically become a record of newly triggered runs. Use the Airflow UI to inspect
and export the IDs, terminal states, and logs of any new demonstration runs.

Check hosted CI without rewriting its saved evidence:

```powershell
& $py -m scripts.github_status --no-write
```

Expected: the relevant latest workflow has `"conclusion": "success"`. This command needs
network access and the existing GitHub login. You can also check the repository's Actions tab.

## 11. Optional: promote a different approved model

Skip this for an ordinary demonstration: the existing model is already deployed. Use this
only when you intentionally want to replace it with another verified, approved MLflow run.
Training alone does not redeploy the application.

First copy a finished, quality-approved run ID from MLflow:

```powershell
. .\scripts\env.ps1
$runId = Read-Host "Paste the finished, quality-approved MLflow run ID"
& $py -m scripts.export_model $runId
```

Continue only if export succeeds. Render and inspect the proposed release:

```powershell
& $py -m scripts.prepare_release
Get-Content .runtime/release.yaml
```

Build its uniquely tagged image:

```powershell
$modelMetadata = Get-Content artifacts/metadata.json -Raw | ConvertFrom-Json
$modelTag = $modelMetadata.run_id.Substring(0, 12)
& $py -m scripts.wsl docker build -t "mlops-inference:$modelTag" .
```

After reviewing the release and deciding to deploy, import the image and apply it:

```powershell
& $py -m scripts.wsl bash scripts/deploy_local.sh
```

Repeat step 4 to verify two ready replicas, loaded model identity, and a successful prediction.

## 12. Check Git and push intentional changes

```powershell
git status --short
git log -1 --oneline
git remote -v
```

No output from `git status --short` means the working tree is clean. Evidence-refresh commands
can legitimately modify tracked JSON files. Review those changes before committing them.

To commit this runbook if it is still uncommitted:

```powershell
git add RUNBOOK.md
git commit -m "Add assignment demonstration runbook"
git push origin main
```

If the runbook is already committed, skip `git add` and `git commit`. Stage any other intended
changes explicitly after review. Keep `.env`, kubeconfigs, passwords, and tokens private.

Repository: https://github.com/OwaisAbdullah19/mlops-assignment-03-ai-agent

## 13. Stop the demonstration

Exit interactive chat first. Stop the project containers before releasing the retained
Ubuntu session:

```powershell
& $py -m scripts.wsl env MLFLOW_PUBLISHED_PORT=5002 docker compose -p mlops-a3 stop
& $py -m scripts.wsl docker stop mlops-a3-k3s
& $py -m scripts.local_services stop
```

This retains the data volumes and model files. Start again from step 1 next time.

## Troubleshooting commands

**Airflow authorization error or expired Kubernetes credentials:**

```powershell
& $py -m scripts.connect_stack --kubernetes --airflow
& $py -m scripts.local_services stop --service agent
& $py -m scripts.local_services start
```

Restart an interactive chat too, so it loads the refreshed configuration.

**Inspect container status and Airflow logs:**

```powershell
& $py -m scripts.wsl env MLFLOW_PUBLISHED_PORT=5002 docker compose -p mlops-a3 ps
& $py -m scripts.wsl env MLFLOW_PUBLISHED_PORT=5002 docker compose -p mlops-a3 logs --tail 80 airflow
```

**Inspect application events and logs:**

```powershell
& $py -m scripts.wsl docker exec mlops-a3-k3s kubectl -n mlops-agent get events --sort-by=.metadata.creationTimestamp
& $py -m scripts.wsl docker exec mlops-a3-k3s kubectl -n mlops-agent logs deployment/iris-api --tail=50
```

**Inspect the agent or local model:**

```powershell
& $py -m scripts.local_services status
Get-Content .runtime/services/agent.log -Tail 40
Get-Content .runtime/services/llm.log -Tail 40
```

For slow LLM requests, allow time for CPU inference or use the explicitly identified rules
planner from step 7. Infrastructure errors should be diagnosed from their actual logs and
states; retraining is not a general fix for an unavailable service.

## Explain the assignment in your own words

```text
User question
  -> Agent selects structured tools
  -> DVC / MLflow / Airflow / Kubernetes return evidence
  -> Agent explains facts, uncertainty, and recommended actions
  -> Any state-changing agent action needs separate operator confirmation
```

The training lifecycle is:

```text
Version Iris data with DVC
  -> Validate schema and committed content digest
  -> Preprocess: reproducible 80/20 stratified split
  -> Train: StandardScaler + LogisticRegression
  -> Evaluate: macro F1 and accuracy, recorded in MLflow
  -> Quality gate: F1 >= 0.85
  -> Explicitly export and approve deployment of a model image
  -> Serve predictions through FastAPI on two Kubernetes replicas
```

The dataset has 150 examples, four input features, and three classes. A perfect score on its
30-example holdout does not establish general production readiness. Dataset identity, quality,
serving compatibility, loaded model identity, and rollout health are separate checks.

For submission and defense, review [report.md](report.md), [architecture.md](architecture.md),
and [evidence/README.md](evidence/README.md). Submit the repository link, give your instructor
access to the private repository, and prepare to explain the five conversations and failures.
