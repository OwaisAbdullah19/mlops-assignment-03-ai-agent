#!/usr/bin/env bash
set -euo pipefail
# Migrate the consistent snapshot and artifacts; never replace an existing backend.
docker volume create mlops-a3_mlflow-data >/dev/null
docker run --rm --entrypoint sh -v mlops-a3_mlflow-data:/mlflow \
  -v "$PWD/.runtime:/source:ro" postgres:16.9-alpine -c '
    if [ -e /mlflow/mlflow.db ]; then
      echo "Existing container MLflow backend preserved"
    else
      cp /source/mlflow-seed.db /mlflow/mlflow.db
      mkdir -p /mlflow/artifacts
      cp -R /source/mlartifacts/. /mlflow/artifacts/
      echo "MLflow database snapshot and verified training artifacts migrated"
    fi
  '
