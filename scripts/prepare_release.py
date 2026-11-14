"""Render a reviewable Kubernetes release; does not change cluster state."""

import hashlib
import json
from pathlib import Path

import yaml


def main():
    metadata = json.loads(Path("artifacts/metadata.json").read_text())
    approval = json.loads(Path("artifacts/approved.json").read_text())
    digest = hashlib.sha256(Path("artifacts/model.joblib").read_bytes()).hexdigest()
    if (
        not metadata.get("run_id")
        or not metadata["quality_passed"]
        or not approval.get("approved")
        or approval.get("run_id") != metadata["run_id"]
        or digest != metadata["model_sha256"]
        or digest != approval.get("model_sha256")
    ):
        raise SystemExit("Missing approval or mismatched model identity")
    tag = metadata["run_id"][:12]
    deployment = yaml.safe_load(Path("kubernetes/deployment.yaml").read_text())
    deployment["spec"]["template"]["metadata"]["annotations"] = {"mlops/model-run-id": metadata["run_id"]}
    deployment["spec"]["template"]["spec"]["containers"][0]["image"] = f"mlops-inference:{tag}"
    deployment["spec"]["template"]["metadata"]["labels"]["app.kubernetes.io/version"] = tag
    configmap = yaml.safe_load(Path("kubernetes/configmap.yaml").read_text())
    configmap["data"]["APP_VERSION"] = tag
    target = Path(".runtime/release.yaml")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump_all([configmap, deployment], sort_keys=False))
    print(f"Rendered {target}; build image mlops-inference:{tag} and review before applying.")


if __name__ == "__main__":
    main()
