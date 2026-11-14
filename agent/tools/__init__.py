"""Real integrations; service imports are lazy so unit tests need no cluster."""


def build_registry(settings):
    from agent.registry import Registry
    from agent.tools.airflow_tools import AirflowTools
    from agent.tools.dvc_tools import DVCTools
    from agent.tools.kubernetes_tools import KubernetesTools
    from agent.tools.mlflow_tools import MLflowTools

    registry = Registry(settings)
    for cls in (DVCTools, MLflowTools, AirflowTools, KubernetesTools):
        cls(settings).register(registry)
    return registry
