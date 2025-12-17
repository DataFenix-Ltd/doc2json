"""Tests for configuration loading."""

import pytest
from pathlib import Path

from doc2json.config.loader import (
    load_config,
    Config,
    SchemaConfig,
    LLMConfig,
    DestinationConfig,
)
from doc2json.core.exceptions import ConfigError


class TestSchemaConfig:
    """Tests for SchemaConfig dataclass."""

    def test_paths_from_name(self):
        """Test that all paths are derived from schema name."""
        config = SchemaConfig(name="invoices")

        assert config.schema_path == "schemas/invoices.py"
        assert config.sources_path == "sources/invoices/"
        assert config.output_path == "outputs/invoices.jsonl"

    def test_assess_default_false(self):
        """Test that assess defaults to False."""
        config = SchemaConfig(name="test")
        assert config.assess is False

    def test_assess_can_be_enabled(self):
        """Test that assess can be set to True."""
        config = SchemaConfig(name="test", assess=True)
        assert config.assess is True


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_simple_schema_list(self, temp_dir):
        """Test loading config with simple schema names."""
        config_yaml = """schemas:
  - invoices
  - contracts
"""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text(config_yaml)

        config = load_config(str(config_file))

        assert len(config.schemas) == 2
        assert config.schemas[0].name == "invoices"
        assert config.schemas[0].sources_path == "sources/invoices/"
        assert config.schemas[1].name == "contracts"

    def test_load_schema_with_options(self, temp_dir):
        """Test loading config with schema options."""
        config_yaml = """schemas:
  - name: invoices
    assess: true
  - name: contracts
"""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text(config_yaml)

        config = load_config(str(config_file))

        assert config.schemas[0].name == "invoices"
        assert config.schemas[0].assess is True
        assert config.schemas[1].name == "contracts"
        assert config.schemas[1].assess is False

    def test_load_mixed_format(self, temp_dir):
        """Test loading config with mixed simple and extended format."""
        config_yaml = """schemas:
  - invoices
  - name: contracts
    assess: true
"""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text(config_yaml)

        config = load_config(str(config_file))

        assert config.schemas[0].name == "invoices"
        assert config.schemas[0].assess is False
        assert config.schemas[1].name == "contracts"
        assert config.schemas[1].assess is True

    def test_load_with_llm_config(self, temp_dir):
        """Test loading config with LLM settings."""
        config_yaml = """schemas:
  - invoices

llm:
  provider: openai
  model: gpt-4o
"""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text(config_yaml)

        config = load_config(str(config_file))

        assert config.llm.provider == "openai"
        assert config.llm.model == "gpt-4o"

    def test_default_llm_config(self, temp_dir):
        """Test default LLM configuration."""
        config_yaml = """schemas:
  - invoices
"""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text(config_yaml)

        config = load_config(str(config_file))

        assert config.llm.provider == "anthropic"
        assert config.llm.model == "claude-sonnet-4-20250514"

    def test_get_schema_by_name(self, temp_dir):
        """Test getting a schema by name."""
        config_yaml = """schemas:
  - invoices
  - contracts
"""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text(config_yaml)

        config = load_config(str(config_file))

        assert config.get_schema("invoices").name == "invoices"
        assert config.get_schema("contracts").name == "contracts"
        assert config.get_schema("nonexistent") is None

    def test_missing_config_file(self, temp_dir):
        """Test error when config file doesn't exist."""
        with pytest.raises(ConfigError) as exc_info:
            load_config(str(temp_dir / "nonexistent.yml"))

        assert "Configuration file not found" in str(exc_info.value)

    def test_empty_config_file(self, temp_dir):
        """Test error for empty config file."""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text("")

        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))

        assert "empty" in str(exc_info.value)

    def test_invalid_yaml(self, temp_dir):
        """Test error for invalid YAML syntax."""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text("schemas:\n  - [invalid")

        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))

        assert "Invalid YAML" in str(exc_info.value)

    def test_empty_schemas_list(self, temp_dir):
        """Test error for empty schemas list."""
        config_yaml = """schemas: []
"""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text(config_yaml)

        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))

        assert "cannot be empty" in str(exc_info.value)

    def test_schemas_not_list(self, temp_dir):
        """Test error when schemas is not a list."""
        config_yaml = """schemas:
  name: not_a_list
"""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text(config_yaml)

        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))

        assert "must be a list" in str(exc_info.value)

    def test_missing_name_in_extended_format(self, temp_dir):
        """Test error when extended format is missing 'name'."""
        config_yaml = """schemas:
  - assess: true
"""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text(config_yaml)

        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))

        assert "Missing 'name'" in str(exc_info.value)

    def test_no_schemas_config(self, temp_dir):
        """Test error when no schema config is provided."""
        config_yaml = """llm:
  provider: anthropic
"""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text(config_yaml)

        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))

        assert "Missing schema configuration" in str(exc_info.value)


class TestLegacyConfigSupport:
    """Tests for backward compatibility with legacy config formats."""

    def test_legacy_single_extraction(self, temp_dir):
        """Test loading legacy single extraction config."""
        config_yaml = """extraction:
  schema: my_schema
  assess: true
"""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text(config_yaml)

        config = load_config(str(config_file))

        assert len(config.schemas) == 1
        assert config.schemas[0].name == "my_schema"
        assert config.schemas[0].assess is True
        # Paths should use convention
        assert config.schemas[0].sources_path == "sources/my_schema/"

    def test_legacy_multiple_extractions(self, temp_dir):
        """Test loading legacy multiple extractions config."""
        config_yaml = """extractions:
  - schema: invoices
    assess: true
  - schema: contracts
"""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text(config_yaml)

        config = load_config(str(config_file))

        assert len(config.schemas) == 2
        assert config.schemas[0].name == "invoices"
        assert config.schemas[0].assess is True
        assert config.schemas[1].name == "contracts"

    def test_legacy_missing_schema_field(self, temp_dir):
        """Test error when legacy config is missing schema field."""
        config_yaml = """extraction:
  sources: documents/
"""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text(config_yaml)

        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))

        assert "extraction.schema" in str(exc_info.value)


class TestDestinationConfig:
    """Tests for destination configuration."""

    def test_destination_with_extra_fields(self, temp_dir):
        """Test that extra destination fields are captured in config dict."""
        config_yaml = """schemas:
  - test

destination:
  type: custom
  api_endpoint: https://api.example.com
  api_key: secret123
"""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text(config_yaml)

        config = load_config(str(config_file))

        assert config.destination.type == "custom"
        assert config.destination.config["api_endpoint"] == "https://api.example.com"
        assert config.destination.config["api_key"] == "secret123"

    def test_destination_standard_fields(self, temp_dir):
        """Test standard destination fields in config dict."""
        config_yaml = """schemas:
  - test

destination:
  type: postgres
  host: localhost
  port: 5432
  database: mydb
  user: admin
  password: secret
"""
        config_file = temp_dir / "doc2json.yml"
        config_file.write_text(config_yaml)

        config = load_config(str(config_file))

        assert config.destination.type == "postgres"
        assert config.destination.config["host"] == "localhost"
        assert config.destination.config["port"] == 5432
        assert config.destination.config["database"] == "mydb"


class TestLLMConfig:
    """Tests for LLMConfig dataclass."""

    def test_defaults(self):
        """Test default LLM configuration."""
        config = LLMConfig()
        assert config.provider == "anthropic"
        assert config.model == "claude-sonnet-4-20250514"

    def test_custom_provider(self):
        """Test custom provider settings."""
        config = LLMConfig(provider="openai", model="gpt-4o")
        assert config.provider == "openai"
        assert config.model == "gpt-4o"
