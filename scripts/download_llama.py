"""Fetch and verify the official pinned Windows CPU llama.cpp release."""

import hashlib
import json
import zipfile
from pathlib import Path

import httpx


def main():
    build = "b12375"
    filename = f"llama-{build}-bin-win-cpu-x64.zip"
    root = Path(".runtime")
    root.mkdir(exist_ok=True)
    archive = root / "llama.zip"
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        response = client.get(f"https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/{build}")
        response.raise_for_status()
        asset = next(a for a in response.json()["assets"] if a["name"] == filename)
        if not archive.exists():
            with client.stream("GET", asset["browser_download_url"]) as download:
                download.raise_for_status()
                with archive.open("wb") as output:
                    for block in download.iter_bytes(1024 * 1024):
                        output.write(block)
        with archive.open("rb") as source:
            digest = "sha256:" + hashlib.file_digest(source, "sha256").hexdigest()
        if digest != asset.get("digest"):
            raise SystemExit("Runtime checksum mismatch; remove the incomplete archive and retry")
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(root / "llama")
        (root / "llama-release.json").write_text(json.dumps(asset, indent=2), encoding="utf-8")
        print(f"Official CPU runtime {build} downloaded and checksum verified")


if __name__ == "__main__":
    main()
