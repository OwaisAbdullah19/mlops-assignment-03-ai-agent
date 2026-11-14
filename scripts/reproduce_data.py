"""Retrieve a committed dataset into a NEW isolated clone and verify its digest."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import yaml


def run(*args, cwd=None):
    return subprocess.run(
        args, cwd=cwd, check=True, capture_output=True, text=True, timeout=120
    ).stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--output", default=".runtime/reproduced")
    args = parser.parse_args()
    root = Path.cwd()
    target = Path(args.output).resolve()
    if target.exists():
        raise SystemExit("Output must be a new directory")
    commit = run("git", "rev-parse", "--verify", f"{args.revision}^{{commit}}")
    remote = run("dvc", "config", "remote.local.url")
    run("git", "clone", "--no-hardlinks", str(root), str(target))
    run("git", "checkout", "--detach", commit, cwd=target)
    run("dvc", "remote", "add", "--local", "--force", "-d", "local", remote, cwd=target)
    run("dvc", "pull", "data/iris.csv.dvc", cwd=target)
    pointer = yaml.safe_load((target / "data/iris.csv.dvc").read_text())["outs"][0]
    actual = hashlib.md5((target / "data/iris.csv").read_bytes(), usedforsecurity=False).hexdigest()
    if actual != pointer["md5"]:
        raise SystemExit("Reproduction checksum mismatch")
    result = {
        "git_commit": commit,
        "dvc_digest": actual,
        "matches": True,
        "target": str(target),
        "dvc_status": json.loads(run("dvc", "status", "data/iris.csv.dvc", "--json", cwd=target)),
    }
    Path("evidence").mkdir(exist_ok=True)
    Path("evidence/dataset-reproduction.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
