"""Initialize real Git/DVC provenance and a workspace-local DVC remote."""

import subprocess
from pathlib import Path

from training.data import generate


def run(*args):
    subprocess.run(args, check=True, timeout=120)


def main():
    if not Path(".git").exists():
        run("git", "init", "-b", "main")
    if not Path(".dvc").exists():
        run("dvc", "init")
    remote = Path(".runtime/dvc-remote").resolve()
    remote.mkdir(parents=True, exist_ok=True)
    run("dvc", "remote", "add", "--local", "--force", "-d", "local", str(remote))
    if not Path("data/iris.csv").exists():
        generate()
    run("dvc", "add", "data/iris.csv")
    run("dvc", "push")
    print(
        "Dataset generated, cached and pushed. Review and commit data/iris.csv.dvc, data/.gitignore and .dvc."
    )


if __name__ == "__main__":
    main()
