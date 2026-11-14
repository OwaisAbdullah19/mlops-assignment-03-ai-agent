from datetime import datetime, timezone

from agent.schemas import Namespace, Pod, Restart
from agent.security import redact


class KubernetesTools:
    def __init__(self, settings, core=None, apps=None):
        self.settings = settings
        self._core, self._apps = core, apps

    def clients(self):
        if self._core is None:
            from kubernetes import client, config
            from kubernetes.config.config_exception import ConfigException

            try:
                config.load_incluster_config()
            except ConfigException:
                config.load_kube_config()
            self._core, self._apps = client.CoreV1Api(), client.AppsV1Api()
        return self._core, self._apps

    def _scope(self, namespace):
        if namespace != self.settings.namespace:
            raise PermissionError("Namespace is outside the approved scope")

    def pods(self, namespace="mlops-agent"):
        self._scope(namespace)
        core, _ = self.clients()
        items = core.list_namespaced_pod(
            namespace, label_selector=self.settings.selector, _request_timeout=self.settings.timeout
        ).items
        rows = []
        for p in items:
            statuses = p.status.container_statuses or []
            containers = [
                {
                    "name": c.name,
                    "ready": c.ready,
                    "restarts": c.restart_count,
                    "reason": c.state.waiting.reason if c.state and c.state.waiting else None,
                    "image": c.image,
                }
                for c in statuses
            ]
            ready_condition = any(
                c.type == "Ready" and c.status == "True" for c in (p.status.conditions or [])
            )
            rows.append(
                {
                    "name": p.metadata.name,
                    "phase": p.status.phase,
                    "ready": ready_condition,
                    "containers": containers,
                    "unhealthy": p.status.phase != "Running" or not ready_condition,
                    "conditions": [
                        {"type": c.type, "status": c.status, "reason": c.reason}
                        for c in (p.status.conditions or [])
                    ],
                }
            )
        return {"namespace": namespace, "pods": rows}

    def deployments(self, namespace="mlops-agent"):
        self._scope(namespace)
        _, apps = self.clients()
        items = apps.list_namespaced_deployment(
            namespace, label_selector=self.settings.selector, _request_timeout=self.settings.timeout
        ).items
        return {
            "namespace": namespace,
            "deployments": [
                {
                    "name": d.metadata.name,
                    "desired": d.spec.replicas,
                    "ready": d.status.ready_replicas or 0,
                    "available": d.status.available_replicas or 0,
                    "generation": d.metadata.generation,
                    "observed_generation": d.status.observed_generation,
                    "updated": d.status.updated_replicas or 0,
                    "images": [c.image for c in d.spec.template.spec.containers],
                    "annotations": {
                        k: v
                        for k, v in (d.spec.template.metadata.annotations or {}).items()
                        if k.startswith("mlops/")
                    },
                }
                for d in items
            ],
        }

    def services(self, namespace="mlops-agent"):
        self._scope(namespace)
        core, _ = self.clients()
        items = core.list_namespaced_service(
            namespace, label_selector=self.settings.selector, _request_timeout=self.settings.timeout
        ).items
        return {
            "services": [
                {
                    "name": s.metadata.name,
                    "type": s.spec.type,
                    "cluster_ip": s.spec.cluster_ip,
                    "selector": s.spec.selector,
                    "ports": [{"port": p.port, "target_port": p.target_port} for p in s.spec.ports],
                }
                for s in items
            ]
        }

    def events(self, namespace="mlops-agent"):
        self._scope(namespace)
        core, _ = self.clients()
        pods = {p["name"] for p in self.pods(namespace)["pods"]}
        items = core.list_namespaced_event(namespace, _request_timeout=self.settings.timeout).items
        return {
            "events": [
                {
                    "reason": e.reason,
                    "message": redact(e.message or "")[:2000],
                    "type": e.type,
                    "object": e.involved_object.name,
                }
                for e in items
                if e.involved_object.name in pods
            ][-50:]
        }

    def logs(self, pod, namespace="mlops-agent", previous=False):
        self._scope(namespace)
        if pod not in {p["name"] for p in self.pods(namespace)["pods"]}:
            raise PermissionError("Pod is outside the approved application")
        core, _ = self.clients()
        logs = core.read_namespaced_pod_log(
            pod,
            namespace,
            previous=previous,
            tail_lines=100,
            limit_bytes=16000,
            _request_timeout=self.settings.timeout,
        )
        return {"pod": pod, "previous": previous, "logs": redact(logs)}

    def restart(self, namespace="mlops-agent", deployment="iris-api"):
        self._scope(namespace)
        if deployment != self.settings.deployment:
            raise PermissionError("Deployment is outside the approved application")
        _, apps = self.clients()
        apps.patch_namespaced_deployment(
            deployment,
            namespace,
            {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/restartedAt": datetime.now(timezone.utc).isoformat()
                            }
                        }
                    }
                }
            },
            _request_timeout=self.settings.timeout,
        )
        return {
            "namespace": namespace,
            "deployment": deployment,
            "restart_requested": True,
            "note": "Check rollout status; acknowledgement does not prove health.",
        }

    def register(self, r):
        r.add(
            "kubernetes_pods",
            "List application Pods, health, restarts, and container waiting reasons",
            Namespace,
            self.pods,
        )
        r.add(
            "kubernetes_deployments",
            "Inspect replicas, rollout generation, image and model run ID annotations",
            Namespace,
            self.deployments,
        )
        r.add("kubernetes_services", "Inspect application Services", Namespace, self.services)
        r.add("kubernetes_events", "Inspect application warning events", Namespace, self.events)
        r.add("kubernetes_logs", "Read recent or previous logs of an application Pod", Pod, self.logs)
        r.add(
            "kubernetes_restart",
            "Request application rollout restart; explicit confirmation required",
            Restart,
            self.restart,
            True,
        )
