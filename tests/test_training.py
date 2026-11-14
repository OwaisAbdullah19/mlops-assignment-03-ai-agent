import hashlib
import json
import subprocess

import pytest
import yaml
from fastapi.testclient import TestClient

from api.main import app
from training.data import generate
from training.train import evaluate, preprocess, quality_gate, train, validate


@pytest.fixture
def trained(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    generate()
    subprocess.run(["git", "init", "-q"], check=True)
    digest = hashlib.md5((tmp_path / "data/iris.csv").read_bytes(), usedforsecurity=False).hexdigest()
    (tmp_path / "data/iris.csv.dvc").write_text(
        yaml.safe_dump({"outs": [{"md5": digest, "path": "iris.csv"}]})
    )
    subprocess.run(["git", "add", "data/iris.csv.dvc"], check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "test provenance",
        ],
        check=True,
    )
    preprocess("data/iris.csv", "artifacts")
    train("artifacts")
    evaluate("data/iris.csv", "artifacts", track=False)
    return tmp_path


def test_real_training_and_inference_identity(trained, monkeypatch):
    quality_gate("artifacts")
    monkeypatch.setenv("MODEL_PATH", str(trained / "artifacts/model.joblib"))
    monkeypatch.setenv("MODEL_METADATA_PATH", str(trained / "artifacts/metadata.json"))
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 200
        result = client.post("/predict", json={"instances": [[5.1, 3.5, 1.4, 0.2]]})
        assert result.status_code == 200
        assert result.json()["predictions"] == [0]
        assert client.get("/metadata").json()["quality_passed"] is True
        assert client.post("/predict", json={"instances": [[1, 2, 3]]}).status_code == 422


def test_injected_validation_failure(tmp_path):
    path = tmp_path / "iris.csv"
    generate(path)
    with pytest.raises(ValueError, match="Injected validation failure"):
        validate(path, failure="validation")


def test_injected_quality_gate_failure_blocks_approval(trained):
    quality_gate("artifacts")
    assert (trained / "artifacts/approved.json").exists()
    evaluate("data/iris.csv", "artifacts", failure="quality", track=False)
    with pytest.raises(ValueError, match="Quality gate failed"):
        quality_gate("artifacts")
    assert not (trained / "artifacts/approved.json").exists()


def test_dataset_change_breaks_recorded_provenance(trained):
    path = trained / "data/iris.csv"
    path.write_text(path.read_text().replace("5.1,3.5", "5.2,3.5", 1))
    with pytest.raises(ValueError, match="differ from the DVC pointer"):
        evaluate("data/iris.csv", "artifacts", track=False)


def test_missing_model_keeps_readiness_false(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "missing.joblib"))
    monkeypatch.setenv("MODEL_METADATA_PATH", str(tmp_path / "missing.json"))
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        assert client.post("/predict", json={"instances": [[1, 2, 3, 4]]}).status_code == 503


def test_corrupt_model_refuses_readiness(trained, monkeypatch):
    path = trained / "artifacts/model.joblib"
    path.write_bytes(b"corrupt model")
    monkeypatch.setenv("MODEL_PATH", str(path))
    monkeypatch.setenv("MODEL_METADATA_PATH", str(trained / "artifacts/metadata.json"))
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 503


def test_failed_quality_model_refuses_readiness(trained, monkeypatch):
    path = trained / "artifacts/metadata.json"
    metadata = json.loads(path.read_text())
    metadata["quality_passed"] = False
    path.write_text(json.dumps(metadata))
    monkeypatch.setenv("MODEL_PATH", str(trained / "artifacts/model.joblib"))
    monkeypatch.setenv("MODEL_METADATA_PATH", str(path))
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 503
