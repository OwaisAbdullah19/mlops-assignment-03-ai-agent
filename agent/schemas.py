from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Identifier = Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:@+\-]*$")]
Revision = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_./\-]*$")]


class Inputs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Empty(Inputs):
    pass


class Dataset(Inputs):
    dataset: str = "data/iris.csv"
    revision: Revision = "HEAD"
    expected_digest: str | None = None


class Diff(Inputs):
    old: Revision
    new: Revision = "HEAD"


class Run(Inputs):
    run_id: Identifier


class Runs(Inputs):
    limit: int = Field(default=5, ge=1, le=100)
    metric: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")] = "f1"
    direction: Literal["max", "min"] = "max"


class Compare(Inputs):
    run_ids: list[Identifier] = Field(min_length=2, max_length=10)


class Model(Inputs):
    name: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_.\-]*$")] = "iris-classifier"


class Dag(Inputs):
    dag_id: Identifier = "ml_training"
    limit: int = Field(default=5, ge=1, le=100)


class DagRun(Inputs):
    dag_id: Identifier = "ml_training"
    run_id: Identifier


class TaskLog(DagRun):
    task_id: Identifier
    try_number: int = Field(default=1, ge=1, le=100)


class Trigger(Inputs):
    dag_id: Identifier = "ml_training"
    failure: Literal["none", "validation", "quality"] = "none"


class Namespace(Inputs):
    namespace: Identifier = "mlops-agent"


class Pod(Namespace):
    pod: Identifier
    previous: bool = False


class Restart(Namespace):
    deployment: Identifier = "iris-api"


class ToolCall(Inputs):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool: str
    status: Literal["ok", "error", "denied", "confirmation_required"]
    data: Any = None
    error: str | None = None
    request_id: str
    duration_ms: float = 0
    observed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Ask(Inputs):
    message: str = Field(min_length=1, max_length=4000)


class Confirm(Inputs):
    token: str = Field(min_length=20, max_length=200)
