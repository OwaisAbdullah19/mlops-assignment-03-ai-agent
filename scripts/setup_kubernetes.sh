#!/usr/bin/env bash
set -euo pipefail

# Dedicated lightweight local Kubernetes server; existing containers are untouched.
cluster=mlops-a3-k3s
if ! docker container inspect "$cluster" >/dev/null 2>&1; then
  docker run -d --privileged --restart unless-stopped \
    --name "$cluster" \
    -p 127.0.0.1:6443:6443 -p 127.0.0.1:8002:8002 \
    -v mlops-a3-k3s-data:/var/lib/rancher/k3s \
    rancher/k3s:v1.33.3-k3s1 server \
    --node-name mlops-a3-node --tls-san localhost \
    --disable traefik --disable servicelb --disable metrics-server --disable local-storage \
    --disable-helm-controller --disable-cloud-controller
else
  docker start "$cluster" >/dev/null
fi
ready=false
for attempt in $(seq 1 120); do
  if docker exec "$cluster" kubectl get nodes 2>/dev/null | grep -q ' Ready '; then
    ready=true
    break
  fi
  sleep 2
done
if [[ "$ready" != true ]]; then
  printf 'Kubernetes has not become ready. Inspect docker logs %s\n' "$cluster" >&2
  exit 1
fi
docker cp "$cluster":/etc/rancher/k3s/k3s.yaml .runtime/kubeconfig-linux
chmod 600 .runtime/kubeconfig-linux
docker exec "$cluster" kubectl get nodes
# This local cluster has no cloud provider; clear any taint retained from earlier bootstrap.
if docker exec "$cluster" kubectl get node mlops-a3-node -o jsonpath='{.spec.taints}' | grep -q 'node.cloudprovider.kubernetes.io/uninitialized'; then
  docker exec "$cluster" kubectl taint nodes mlops-a3-node node.cloudprovider.kubernetes.io/uninitialized-
fi
