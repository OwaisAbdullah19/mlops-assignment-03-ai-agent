"""Create local-only secrets without displaying their values."""

import secrets
from pathlib import Path

from cryptography.fernet import Fernet


def main():
    target = Path(".env")
    if target.exists():
        raise SystemExit(".env exists; edit it explicitly instead of overwriting secrets")
    template = Path(".env.example").read_text(encoding="utf-8")
    template = template.replace("AGENT_API_TOKEN=\n", "AGENT_API_TOKEN=" + secrets.token_urlsafe(32) + "\n")
    template += (
        "\nAIRFLOW_DB_PASSWORD="
        + secrets.token_urlsafe(24)
        + "\nAIRFLOW_JWT_SECRET="
        + secrets.token_urlsafe(48)
        + "\nAIRFLOW_FERNET_KEY="
        + Fernet.generate_key().decode()
        + "\n"
    )
    target.write_text(template, encoding="utf-8")
    print("Created ignored .env with random local credentials. Load it with scripts/env.ps1.")


if __name__ == "__main__":
    main()
