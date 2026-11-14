FROM python:3.11.13-slim
WORKDIR /app
COPY pyproject.toml ./
COPY agent ./agent
COPY api ./api
COPY training ./training
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home appuser
COPY --chown=10001:10001 artifacts/model.joblib artifacts/metadata.json artifacts/approved.json ./artifacts/
USER 10001
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
