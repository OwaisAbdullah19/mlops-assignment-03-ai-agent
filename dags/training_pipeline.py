"""Airflow 3 TaskFlow DAG. Artifacts are isolated by DAG run, including retries."""

import logging
import os
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

from airflow.sdk import dag, get_current_context, task

log = logging.getLogger(__name__)


@dag(
    dag_id="ml_training",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(seconds=10)},
    tags=["mlops", "iris"],
)
def training_pipeline():
    def context():
        ctx = get_current_context()
        config = ctx["dag_run"].conf or {}
        run_key = sha256(ctx["run_id"].encode()).hexdigest()[:20]
        root = Path(os.getenv("TRAINING_ROOT", "/opt/project"))
        os.chdir(root)
        output = str(root / "artifacts" / run_key)
        return config, output

    @task
    def validation():
        from training.train import provenance, validate

        config, _ = context()
        log.info("Validating schema, finite values, class support and committed dataset digest")
        validate("data/iris.csv", config.get("failure", "none"))
        return provenance("data/iris.csv")

    @task
    def preprocessing(provenance_tags):
        from training.train import preprocess

        _, output = context()
        log.info(
            "Creating deterministic stratified split for dataset %s", provenance_tags["dataset.dvc_digest"]
        )
        preprocess("data/iris.csv", output)
        return output

    @task
    def training(output):
        from training.train import train

        config, _ = context()
        train(output, c=float(config.get("C", 1.0)))
        return output

    @task
    def evaluation_mlflow(output):
        from training.train import evaluate

        config, _ = context()
        result = evaluate(
            "data/iris.csv", output, c=float(config.get("C", 1.0)), failure=config.get("failure", "none")
        )
        log.info("Recorded MLflow run %s metrics %s", result["run_id"], result["metrics"])
        return output

    @task
    def quality_gate(output):
        from training.train import quality_gate as check

        metadata = check(output)
        log.info("Quality gate passed for run %s; promotion remains manual", metadata["run_id"])

    quality_gate(evaluation_mlflow(training(preprocessing(validation()))))


training_pipeline()
