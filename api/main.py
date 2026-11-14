import hashlib
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from training.data import FEATURES

logger = logging.getLogger("mlops.inference")


@asynccontextmanager
async def lifespan(app):
    app.state.model = None
    app.state.metadata = None
    try:
        path = Path(os.getenv("MODEL_PATH", "artifacts/model.joblib"))
        metadata = json.loads(Path(os.getenv("MODEL_METADATA_PATH", "artifacts/metadata.json")).read_text())
        if not metadata.get("quality_passed"):
            raise ValueError("Model failed quality gate")
        if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["model_sha256"]:
            raise ValueError("Model checksum mismatch")
        app.state.model = joblib.load(path)
        app.state.metadata = metadata
    except Exception:
        logger.error("Model initialization failed; readiness remains false")
    yield


app = FastAPI(title="Iris inference", version="1.0.0", lifespan=lifespan)


class Prediction(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    instances: list[list[float]] = Field(min_length=1, max_length=100)


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready():
    if app.state.model is None:
        raise HTTPException(status_code=503, detail="Model unavailable")
    return {"status": "ready"}


@app.get("/metadata")
def metadata():
    ready()
    return {"app_version": os.getenv("APP_VERSION", "1.0.0"), **app.state.metadata}


@app.post("/predict")
def predict(request: Prediction):
    ready()
    if any(len(row) != 4 for row in request.instances):
        raise HTTPException(status_code=422, detail="Each instance must contain four Iris features")
    x = np.asarray(request.instances, dtype=float)
    if not np.isfinite(x).all() or (x < 0).any() or (x > 30).any():
        raise HTTPException(
            status_code=422, detail="Feature values must be finite measurements between 0 and 30 cm"
        )
    frame = pd.DataFrame(x, columns=FEATURES)
    return {
        "predictions": app.state.model.predict(frame).tolist(),
        "probabilities": app.state.model.predict_proba(frame).tolist(),
        "model_run_id": app.state.metadata.get("run_id"),
    }
