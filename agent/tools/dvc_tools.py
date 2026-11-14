import json
import subprocess
from pathlib import PurePosixPath

import yaml

from agent.schemas import Dataset, Diff, Empty


class DVCTools:
    def __init__(self, settings):
        self.settings = settings

    def _run(self, args):
        return subprocess.run(
            args,
            cwd=self.settings.repo,
            capture_output=True,
            text=True,
            check=True,
            timeout=self.settings.timeout,
            shell=False,
        ).stdout.strip()

    def list_datasets(self):
        return json.loads(self._run(["dvc", "list", ".", "-R", "--dvc-only", "--json"]))

    def version(self, dataset="data/iris.csv", revision="HEAD", expected_digest=None):
        path = PurePosixPath(dataset)
        if path.is_absolute() or ".." in path.parts or ":" in dataset or "\\" in dataset:
            raise ValueError("Dataset path must be relative")
        if not dataset.startswith("data/") or not dataset.endswith(".csv"):
            raise ValueError("Only approved CSV dataset paths are supported")
        commit = self._run(["git", "rev-parse", "--verify", f"{revision}^{{commit}}"])
        pointer = yaml.safe_load(self._run(["git", "show", f"{commit}:{dataset}.dvc"]))
        output = pointer["outs"][0]
        digest = output.get(output.get("hash", "md5"))
        return {
            "dataset": dataset,
            "git_commit": commit,
            "dvc_digest": digest,
            "recorded_digest": expected_digest,
            "matches_recorded_digest": digest == expected_digest if expected_digest else None,
            "reference": f"{commit}:{dataset}.dvc",
        }

    def status(self):
        return {
            "changes": json.loads(self._run(["dvc", "status", "data/iris.csv.dvc", "--json"])),
            "scope": "Training dataset pointer; unbuilt pipeline stages are excluded",
        }

    def diff(self, old, new="HEAD"):
        return json.loads(self._run(["dvc", "diff", "--json", "--show-hash", old, new]))

    def reproduce(self, dataset="data/iris.csv", revision="HEAD", expected_digest=None):
        version = self.version(dataset, revision, expected_digest)
        version["instructions"] = [
            "Use an isolated clone to preserve the current workspace.",
            f"git checkout --detach {version['git_commit']}",
            f"dvc pull {dataset}.dvc",
            "dvc status --json",
        ]
        version["note"] = "Requires configured DVC remote and credentials; commands were not executed."
        return version

    def register(self, r):
        r.add("dvc_list", "List DVC-tracked datasets", Empty, self.list_datasets)
        r.add("dvc_version", "Read dataset hash at a recorded Git revision", Dataset, self.version)
        r.add("dvc_status", "Detect changes to the DVC-tracked training dataset", Empty, self.status)
        r.add("dvc_diff", "Compare two Git revisions of DVC data", Diff, self.diff)
        r.add(
            "dvc_reproduce",
            "Explain reproducible dataset checkout in an isolated clone",
            Dataset,
            self.reproduce,
        )
