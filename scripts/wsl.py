"""Execute a command in this workspace using the existing Ubuntu WSL distribution."""

import os
import shlex
import subprocess
import sys
from pathlib import Path


def main():
    if os.name != "nt":
        raise SystemExit("Use the command directly on Linux")
    args = sys.argv[1:]
    if not args:
        raise SystemExit("Usage: python -m scripts.wsl COMMAND [ARGUMENTS...]")
    root = Path(__file__).resolve().parents[1]
    path = root.as_posix()
    linux_root = "/mnt/" + path[0].lower() + path[2:]
    setup = (
        "set -euo pipefail\n"
        f"cd {shlex.quote(linux_root)}\n"
        f"export PATH={shlex.quote(linux_root + '/.runtime/bin')}:$PATH\n"
        f"export KUBECONFIG={shlex.quote(linux_root + '/.runtime/kubeconfig-linux')}\n"
    )
    result = subprocess.run(
        ["wsl", "-d", "Ubuntu", "--", "bash", "-s"],
        input=(setup + "exec " + shlex.join(args) + "\n").encode(),
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
