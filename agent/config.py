import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    repo: Path = field(default_factory=lambda: Path(os.getenv("REPO_ROOT", ".")).resolve())
    tracking_uri: str = field(
        default_factory=lambda: os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    )
    experiment: str = field(default_factory=lambda: os.getenv("MLFLOW_EXPERIMENT_NAME", "iris-training"))
    airflow_url: str = field(default_factory=lambda: os.getenv("AIRFLOW_URL", "http://localhost:8080"))
    airflow_token: str = field(default_factory=lambda: os.getenv("AIRFLOW_TOKEN", ""))
    dag_id: str = field(default_factory=lambda: os.getenv("AIRFLOW_DAG_ID", "ml_training"))
    namespace: str = field(default_factory=lambda: os.getenv("KUBE_NAMESPACE", "mlops-agent"))
    deployment: str = field(default_factory=lambda: os.getenv("KUBE_DEPLOYMENT", "iris-api"))
    selector: str = field(default_factory=lambda: os.getenv("KUBE_SELECTOR", "app=iris-api"))
    timeout: float = field(default_factory=lambda: float(os.getenv("TOOL_TIMEOUT_SECONDS", "15")))
    llm_timeout: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_SECONDS", "120")))
    freshness_days: int = field(default_factory=lambda: int(os.getenv("FRESHNESS_DAYS", "30")))
    planner: str = field(default_factory=lambda: os.getenv("AGENT_PLANNER", "rules"))
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen3:8b"))
