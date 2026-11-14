"""Download quality-approved MLflow artifacts for an explicit image build."""

import argparse
import hashlib
import json
import os
from pathlib import Path


def main():
    from mlflow import MlflowClient

    p = argparse.ArgumentParser()
    p.add_argument("run_id")
    args = p.parse_args()
    client = MlflowClient(tracking_uri=os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    run = client.get_run(args.run_id)
    if run.info.status != "FINISHED" or run.data.tags.get("quality.passed") != "true":
        raise SystemExit("Only finished, quality-approved runs may be exported")
    out = Path("artifacts")
    out.mkdir(exist_ok=True)
    for name in ("model.joblib", "metadata.json"):
        downloaded = Path(client.download_artifacts(args.run_id, f"training/{name}", str(out)))
        (out / name).write_bytes(downloaded.read_bytes())
    metadata = json.loads((out / "metadata.json").read_text())
    digest = hashlib.sha256((out / "model.joblib").read_bytes()).hexdigest()
    if (
        metadata["run_id"] != args.run_id
        or not metadata["quality_passed"]
        or digest != metadata["model_sha256"]
    ):
        raise SystemExit("Export metadata mismatch")
    (out / "approved.json").write_text(
        json.dumps({"run_id": args.run_id, "approved": True, "model_sha256": digest})
    )
    print(f"Exported verified run {args.run_id}. Build a new uniquely tagged image before deployment.")


if __name__ == "__main__":
    main()
