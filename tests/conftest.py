import pytest

from agent.config import Settings
from agent.registry import Registry


@pytest.fixture
def settings(tmp_path):
    return Settings(repo=tmp_path, airflow_token="test-only-token", freshness_days=30)


@pytest.fixture
def registry(settings):
    return Registry(settings)
