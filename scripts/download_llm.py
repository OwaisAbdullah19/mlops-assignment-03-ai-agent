"""Download the official small Qwen GGUF at a pinned revision, verifying its LFS SHA-256."""

import hashlib
import json
from pathlib import Path

import httpx


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main():
    repo = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
    filename = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
    folder = Path(".runtime/models")
    folder.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        response = client.get(f"https://huggingface.co/api/models/{repo}", params={"blobs": "true"})
        response.raise_for_status()
        metadata = response.json()
        entry = next(item for item in metadata["siblings"] if item["rfilename"] == filename)
        digest = entry["lfs"]["sha256"]
        destination = folder / filename
        if not destination.exists():
            temporary = destination.with_suffix(".partial")
            url = f"https://huggingface.co/{repo}/resolve/{metadata['sha']}/{filename}"
            with client.stream("GET", url) as download:
                download.raise_for_status()
                with temporary.open("wb") as output:
                    size, reported = 0, 0
                    for block in download.iter_bytes(1024 * 1024):
                        output.write(block)
                        size += len(block)
                        if size - reported >= 50 * 1024 * 1024:
                            print(
                                f"Downloaded {size // (1024 * 1024)} MiB of the local tool-calling model",
                                flush=True,
                            )
                            reported = size
            if sha256(temporary) != digest:
                raise SystemExit("Model checksum mismatch")
            temporary.replace(destination)
        if sha256(destination) != digest:
            raise SystemExit("Existing model checksum mismatch")
        (folder / "provenance.json").write_text(
            json.dumps(
                {"repository": repo, "revision": metadata["sha"], "file": filename, "sha256": digest},
                indent=2,
            ),
            encoding="utf-8",
        )
        print("Official Qwen model downloaded and checksum verified", flush=True)


if __name__ == "__main__":
    main()
