"""Provide small source settings for tests that never contact BigQuery."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def sources():
    """Read a fresh copy of the example source definitions for each test."""
    path = Path(__file__).resolve().parents[1] / "config/config.example.yaml"
    config = yaml.safe_load(path.read_text())
    return {source["name"]: deepcopy(source) for source in config["sources"]}
