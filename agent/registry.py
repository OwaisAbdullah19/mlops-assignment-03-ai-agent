import json
import logging
import subprocess
import time
from dataclasses import dataclass
from typing import Callable

import httpx
from pydantic import BaseModel, ValidationError

from agent.schemas import ToolCall, ToolResult
from agent.security import Confirmations

logger = logging.getLogger("mlops.tools")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


@dataclass
class Tool:
    name: str
    description: str
    schema: type[BaseModel]
    function: Callable
    mutates: bool = False


class Registry:
    def __init__(self, settings):
        self.settings = settings
        self.tools = {}
        self.confirmations = Confirmations()

    def add(self, name, description, schema, function, mutates=False):
        self.tools[name] = Tool(name, description, schema, function, mutates)

    def definitions(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.schema.model_json_schema(),
                },
            }
            for t in self.tools.values()
        ]

    def execute(self, call: ToolCall, request_id: str, *, approved=False):
        start = time.monotonic()
        try:
            tool = self.tools.get(call.name)
            if tool is None:
                raise ValueError("Unknown tool")
            arguments = tool.schema.model_validate(call.arguments).model_dump()
            if call.name.startswith("kubernetes_"):
                if arguments.get("namespace", self.settings.namespace) != self.settings.namespace:
                    raise PermissionError("Namespace is outside the approved scope")
                if "deployment" in arguments and arguments["deployment"] != self.settings.deployment:
                    raise PermissionError("Deployment is outside the approved scope")
            if call.name == "airflow_trigger" and arguments["dag_id"] != self.settings.dag_id:
                raise PermissionError("DAG is outside the approved scope")
            if tool.mutates and not approved:
                normalized = ToolCall(name=call.name, arguments=arguments)
                token = self.confirmations.issue(normalized)
                result = ToolResult(
                    tool=call.name,
                    status="confirmation_required",
                    request_id=request_id,
                    data={
                        "action": normalized.model_dump(),
                        "confirmation_token": token,
                        "expires_in_seconds": self.confirmations.ttl,
                    },
                )
            else:
                result = ToolResult(
                    tool=call.name, status="ok", request_id=request_id, data=tool.function(**arguments)
                )
        except PermissionError as exc:
            result = ToolResult(tool=call.name, status="denied", request_id=request_id, error=str(exc))
        except (ValidationError, ValueError):
            result = ToolResult(
                tool=call.name, status="error", request_id=request_id, error="Invalid tool request"
            )
        except (TimeoutError, subprocess.TimeoutExpired, httpx.TimeoutException):
            result = ToolResult(
                tool=call.name,
                status="error",
                request_id=request_id,
                error="Tool timed out; state is unknown",
            )
        except Exception:
            # Exceptions may include credentials/HTTP payloads; never send or log their raw text.
            result = ToolResult(
                tool=call.name,
                status="error",
                request_id=request_id,
                error="Service unavailable or operation failed; state is unknown",
            )
        result.duration_ms = round((time.monotonic() - start) * 1000, 2)
        logger.info(
            json.dumps(
                {
                    "tool": call.name if call.name in self.tools else "unknown",
                    "status": result.status,
                    "duration_ms": result.duration_ms,
                    "request_id": request_id,
                }
            )
        )
        return result

    def confirm(self, token, request_id):
        call = self.confirmations.consume(token)
        return self.execute(call, request_id, approved=True)
