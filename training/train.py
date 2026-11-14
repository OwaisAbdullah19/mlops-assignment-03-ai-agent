import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from training.data import FEATURES


def validate(dataset, failure="none"):
    frame = pd.read_csv(dataset)
    if failure == "validation":
        raise ValueError("Injected validation failure: required feature petal_width missing")
    if list(frame.columns) != FEATURES + ["target"]:
        raise ValueError("Dataset schema mismatch")
    if len(frame) < 100 or frame.isna().any().any():
        raise ValueError("Insufficient rows or missing values")
    if not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise ValueError("Non-finite dataset values")
    if set(frame.target.unique()) != {0, 1, 2} or frame.target.value_counts().min() < 10:
        raise ValueError("Invalid target classes or insufficient per-class support")
    return frame


def provenance(dataset):
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=10
    ).stdout.strip()
    pointer_path = str(dataset).replace("\\", "/") + ".dvc"
    pointer_text = subprocess.run(
        ["git", "show", f"{commit}:{pointer_path}"], check=True, capture_output=True, text=True, timeout=10
    ).stdout
    pointer = yaml.safe_load(pointer_text)["outs"][0]
    digest = hashlib.md5(Path(dataset).read_bytes(), usedforsecurity=False).hexdigest()
    if pointer.get("md5") != digest:
        raise ValueError("Dataset bytes differ from the DVC pointer at HEAD; version data and commit first")
    return {
        "dataset.path": str(dataset).replace("\\", "/"),
        "dataset.git_commit": commit,
        "dataset.dvc_digest": digest,
        "dataset.sha256": hashlib.sha256(Path(dataset).read_bytes()).hexdigest(),
    }


def preprocess(dataset, output, failure="none"):
    # A failed rerun must never leave an older approval available for packaging.
    (Path(output) / "approved.json").unlink(missing_ok=True)
    frame = validate(dataset, failure)
    x_train, x_test, y_train, y_test = train_test_split(
        frame[FEATURES], frame.target, test_size=0.2, random_state=42, stratify=frame.target
    )
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump((x_train, x_test, y_train, y_test), out / "split.joblib")


def train(output, c=1.0):
    out = Path(output)
    x_train, _, y_train, _ = joblib.load(out / "split.joblib")
    model = make_pipeline(StandardScaler(), LogisticRegression(C=c, max_iter=500, random_state=42))
    model.fit(x_train, y_train)
    joblib.dump(model, out / "model.joblib")


def evaluate(dataset, output, c=1.0, failure="none", track=True):
    out = Path(output)
    (out / "approved.json").unlink(missing_ok=True)
    _, x_test, _, y_test = joblib.load(out / "split.joblib")
    prediction = joblib.load(out / "model.joblib").predict(x_test)
    metrics = {
        "f1": float(f1_score(y_test, prediction, average="macro")),
        "accuracy": float(accuracy_score(y_test, prediction)),
    }
    tags = provenance(dataset)
    minimum = 1.01 if failure == "quality" else 0.85
    metadata = {
        "metrics": metrics,
        "min_f1": minimum,
        "provenance": tags,
        "run_id": None,
        "quality_passed": metrics["f1"] >= minimum,
        "model_sha256": hashlib.sha256((out / "model.joblib").read_bytes()).hexdigest(),
        "feature_names": FEATURES,
        "classes": ["setosa", "versicolor", "virginica"],
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    if track:
        os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", os.getenv("TOOL_TIMEOUT_SECONDS", "15"))
        os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
        import mlflow

        mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
        mlflow.set_experiment(os.getenv("MLFLOW_EXPERIMENT_NAME", "iris-training"))
        with mlflow.start_run() as run:
            metadata["run_id"] = run.info.run_id
            mlflow.log_params({"C": c, "random_state": 42, "test_size": 0.2, "min_f1": minimum})
            mlflow.set_tags(
                {
                    **tags,
                    "quality.passed": str(metadata["quality_passed"]).lower(),
                    "training.failure_injection": failure,
                }
            )
            mlflow.log_metrics(metrics)
            (out / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            mlflow.log_artifacts(str(out), artifact_path="training")
            # Registry contains only quality-approved artifacts. No automatic deployment.
            if metadata["quality_passed"]:
                from mlflow import MlflowClient

                client = MlflowClient()
                if not client.search_registered_models(filter_string="name = 'iris-classifier'"):
                    client.create_registered_model("iris-classifier")
                client.create_model_version(
                    "iris-classifier",
                    f"{run.info.artifact_uri}/training",
                    run_id=run.info.run_id,
                    tags={"quality.passed": "true", "dataset.dvc_digest": tags["dataset.dvc_digest"]},
                )
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def quality_gate(output):
    metadata = json.loads((Path(output) / "metadata.json").read_text(encoding="utf-8"))
    if not metadata["quality_passed"]:
        raise ValueError(f"Quality gate failed: F1={metadata['metrics']['f1']:.4f} < {metadata['min_f1']}")
    (Path(output) / "approved.json").write_text(
        json.dumps(
            {"run_id": metadata["run_id"], "model_sha256": metadata["model_sha256"], "approved": True}
        ),
        encoding="utf-8",
    )
    return metadata


def main():
    if os.getenv("TRAINING_DEBUG_STACKS") == "1":
        import faulthandler

        faulthandler.dump_traceback_later(30, repeat=True)
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="data/iris.csv")
    p.add_argument("--output", default="artifacts")
    p.add_argument("--c", type=float, default=1.0)
    p.add_argument("--failure", choices=["none", "validation", "quality"], default="none")
    p.add_argument(
        "--no-track",
        action="store_true",
        help="Local validation only; still requires real committed provenance",
    )
    args = p.parse_args()
    print("Stage: validation and preprocessing", flush=True)
    preprocess(args.dataset, args.output, args.failure)
    print("Stage: training", flush=True)
    train(args.output, args.c)
    print("Stage: evaluation and MLflow artifacts", flush=True)
    metadata = evaluate(args.dataset, args.output, args.c, args.failure, not args.no_track)
    print("Stage: quality gate", flush=True)
    quality_gate(args.output)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
