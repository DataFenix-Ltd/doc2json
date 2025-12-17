"""Shared pytest fixtures for doc2json tests."""

import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_schema_code():
    """Return valid Pydantic schema code for testing."""
    return '''__version__ = "1"

from pydantic import BaseModel, Field
from typing import Optional

class Schema(BaseModel):
    """Test schema for extraction."""
    title: str = Field(description="Document title")
    amount: Optional[float] = Field(default=None, description="Monetary amount")
    date: Optional[str] = Field(default=None, description="Date in any format")
'''


@pytest.fixture
def sample_schema_file(temp_dir, sample_schema_code):
    """Create a temporary schema file."""
    schemas_dir = temp_dir / "schemas"
    schemas_dir.mkdir()
    schema_file = schemas_dir / "test_schema.py"
    schema_file.write_text(sample_schema_code)
    return schema_file


@pytest.fixture
def sample_config_yaml():
    """Return valid config YAML for testing."""
    return """extraction:
  schema: example
  sources: sources/
  assess: true

llm:
  provider: anthropic
  model: claude-sonnet-4-20250514
"""


@pytest.fixture
def sample_config_file(temp_dir, sample_config_yaml):
    """Create a temporary config file."""
    config_file = temp_dir / "doc2json.yml"
    config_file.write_text(sample_config_yaml)
    return config_file


@pytest.fixture
def sample_text_file(temp_dir):
    """Create a sample text document."""
    sources_dir = temp_dir / "sources"
    sources_dir.mkdir()
    text_file = sources_dir / "invoice.txt"
    text_file.write_text("""INVOICE #12345
Date: 2024-01-15

Bill To: Acme Corp
Amount Due: $1,250.00

Services rendered for consulting work.
""")
    return text_file
