#!/usr/bin/env bash
set -euo pipefail
# Run prepare_release and build the matching image before this explicit deployment.
cluster=mlops-a3-k3s
image=$(python3 -c 'import json; print("mlops-inference:"+json.load(open("artifacts/metadata.json"))["run_id"][:12])')
docker image inspect "$image" >/dev/null
docker save "$image" | docker exec -i "$cluster" ctr images import -
for manifest in kubernetes/namespace.yaml .runtime/release.yaml kubernetes/service.yaml kubernetes/rbac.yaml; do
  docker exec -i "$cluster" kubectl apply -f - < "$manifest"
done
docker exec "$cluster" kubectl -n mlops-agent rollout status deployment/iris-api --timeout=240s
docker exec "$cluster" kubectl -n mlops-agent get pods,deployments,services
docker exec -d "$cluster" kubectl -n mlops-agent port-forward service/iris-api 8002:80 --address 0.0.0.0
