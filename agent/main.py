import argparse
import json
import os
import secrets
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException

from agent.config import Settings
from agent.orchestrator import Agent
from agent.schemas import Ask, Confirm
from agent.tools import build_registry


def create_app(settings=None, registry=None):
    settings = settings or Settings()
    registry = registry or build_registry(settings)
    engine = Agent(settings, registry)
    app = FastAPI(title="Evidence-based MLOps Agent", version="1.0.0")

    def authorize(authorization: Annotated[str | None, Header()] = None):
        token = os.getenv("AGENT_API_TOKEN", "")
        if not token or not secrets.compare_digest(authorization or "", "Bearer " + token):
            raise HTTPException(status_code=401, detail="Valid AGENT_API_TOKEN bearer credential required")

    @app.get("/health")
    def health():
        return {"status": "alive"}

    @app.get("/tools", dependencies=[Depends(authorize)])
    def tools():
        return registry.definitions()

    @app.post("/chat", dependencies=[Depends(authorize)])
    def chat(request: Ask):
        return engine.ask(request.message)

    @app.post("/confirm", dependencies=[Depends(authorize)])
    def confirm(request: Confirm):
        try:
            return registry.confirm(request.token, uuid4().hex).model_dump()
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None

    return app


app = create_app()


def main():
    parser = argparse.ArgumentParser(description="MLOps conversational agent")
    parser.add_argument("--message", help="Run one read/proposal request as JSON")
    parser.add_argument("--output", help="Save result JSON to this file")
    args = parser.parse_args()
    settings = Settings()
    registry = build_registry(settings)
    engine = Agent(settings, registry)

    def show(message):
        result = engine.ask(message)
        if args.output:
            from pathlib import Path

            Path(args.output).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(json.dumps(result, indent=2, default=str))
        return result

    if args.message:
        show(args.message)
    else:
        print("MLOps Agent. Type exit to quit. Mutations require a second explicit confirmation.")
        while True:
            try:
                message = input("You> ").strip()
            except EOFError:
                break
            if message.lower() in ("exit", "quit"):
                break
            if message.startswith("confirm "):
                try:
                    print(registry.confirm(message[8:].strip(), uuid4().hex).model_dump_json(indent=2))
                except PermissionError as exc:
                    print(str(exc))
            elif message:
                show(message)


if __name__ == "__main__":
    main()
