import math

from agent.schemas import Compare, Empty, Model, Run, Runs


class MLflowTools:
    def __init__(self, settings, client=None):
        self.settings = settings
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import os

            from mlflow import MlflowClient

            os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] = str(int(self.settings.timeout))
            os.environ["MLFLOW_HTTP_REQUEST_MAX_RETRIES"] = "0"
            self._client = MlflowClient(tracking_uri=self.settings.tracking_uri)
        return self._client

    @staticmethod
    def serialize(run):
        return {
            "run_id": run.info.run_id,
            "experiment_id": run.info.experiment_id,
            "status": run.info.status,
            "start_time": run.info.start_time,
            "metrics": {k: v if math.isfinite(v) else None for k, v in run.data.metrics.items()},
            "params": dict(run.data.params),
            "provenance": {
                k: v for k, v in run.data.tags.items() if k.startswith(("dataset.", "quality.", "training."))
            },
        }

    def experiments(self):
        return [
            {"id": e.experiment_id, "name": e.name} for e in self.client.search_experiments(max_results=100)
        ]

    def runs(self, limit=5, metric="f1", direction="max"):
        experiment = self.client.get_experiment_by_name(self.settings.experiment)
        if experiment is None:
            return {"runs": [], "experiment": self.settings.experiment}
        runs = self.client.search_runs(
            [experiment.experiment_id], max_results=limit, order_by=["attributes.start_time DESC"]
        )
        return {
            "runs": [self.serialize(run) for run in runs],
            "metric": metric,
            "direction": direction,
            "scope": f"Most recent {limit} runs of {self.settings.experiment}",
        }

    def best(self, limit=5, metric="f1", direction="max"):
        data = self.runs(limit, metric, direction)
        eligible = [
            r for r in data["runs"] if r["status"] == "FINISHED" and r["metrics"].get(metric) is not None
        ]
        eligible.sort(key=lambda r: r["metrics"][metric], reverse=direction == "max")
        return {
            **data,
            "best": eligible[0] if eligible else None,
            "explanation": f"Ranked finished runs by {metric} ({direction}); ties retain newest first.",
            "caution": "Candidate ranking alone does not establish production readiness.",
        }

    def run(self, run_id):
        result = self.serialize(self.client.get_run(run_id))
        result["artifacts"] = [
            {"path": a.path, "is_dir": a.is_dir} for a in self.client.list_artifacts(run_id)
        ]
        return result

    def compare(self, run_ids):
        return {"runs": [self.run(run_id) for run_id in run_ids]}

    def versions(self, name="iris-classifier"):
        return [
            {
                "name": v.name,
                "version": v.version,
                "run_id": v.run_id,
                "status": v.status,
                "aliases": list(getattr(v, "aliases", [])),
            }
            for v in self.client.search_model_versions(f"name = '{name}'", max_results=100)
        ]

    def register(self, r):
        r.add("mlflow_experiments", "List MLflow experiments", Empty, self.experiments)
        r.add("mlflow_runs", "List recent runs with metrics and parameters", Runs, self.runs)
        r.add(
            "mlflow_best",
            "Rank recent finished runs using a metric; read dataset provenance tags",
            Runs,
            self.best,
        )
        r.add("mlflow_run", "Retrieve a run and available artifacts", Run, self.run)
        r.add("mlflow_compare", "Compare at least two recorded runs", Compare, self.compare)
        r.add("mlflow_versions", "Retrieve model registry versions when available", Model, self.versions)
