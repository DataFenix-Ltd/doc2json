import yaml
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, Literal

from doc2json.core.exceptions import ConfigError
from doc2json.models.document import MAX_CHARS_DEFAULT


def _substitute_env_vars(value: Any) -> Any:
    """Substitute ${VAR} patterns with environment variables."""
    if isinstance(value, str):
        pattern = r'\$\{([^}]+)\}'
        matches = re.findall(pattern, value)
        for var_name in matches:
            env_value = os.environ.get(var_name, "")
            value = value.replace(f"${{{var_name}}}", env_value)
        return value
    elif isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_substitute_env_vars(v) for v in value]
    return value


class LargeDocStrategy(str, Enum):
    """Strategy for handling large documents."""
    FULL = "full"        # Send entire document (may fail on very large)
    TRUNCATE = "truncate"  # Truncate to max_chars with warning
    FAIL = "fail"        # Raise error if document exceeds limit


@dataclass
class SourceConfig:
    """Configuration for a source connector."""
    type: str  # Connector type: "local", "google_drive", etc.
    config: Dict[str, Any] = field(default_factory=dict)  # Connector-specific config


@dataclass
class DestinationConfig:
    """Configuration for a destination connector."""
    type: str  # Connector type: "jsonl", "postgres", etc.
    config: Dict[str, Any] = field(default_factory=dict)  # Connector-specific config


@dataclass
class SchemaConfig:
    """Configuration for a schema extraction pipeline.

    Convention: schema name determines paths:
    - Schema file: schemas/<name>.py
    - Sources: sources/<name>/ (default, if no source override)
    - Output: outputs/<name>.jsonl (default, if no destination override)
    """
    name: str  # Schema name - the single source of truth
    assess: bool = False  # Whether to run quality assessment
    large_doc_strategy: LargeDocStrategy = LargeDocStrategy.TRUNCATE
    max_chars: int = MAX_CHARS_DEFAULT  # Character limit for extraction
    source: Optional[SourceConfig] = None  # Override global source
    destination: Optional[DestinationConfig] = None  # Override global destination

    @property
    def schema_path(self) -> str:
        """Path to schema file."""
        return f"schemas/{self.name}.py"

    @property
    def sources_path(self) -> str:
        """Default path to sources directory (used if no source connector)."""
        return f"sources/{self.name}/"

    @property
    def output_path(self) -> str:
        """Default path to output JSONL file (used if no destination connector)."""
        return f"outputs/{self.name}.jsonl"


@dataclass
class LLMConfig:
    """Configuration for LLM provider."""
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_version: Optional[str] = None  # Required for Azure OpenAI


@dataclass
class InferenceConfig:
    mode: str = "auto"


@dataclass
class Config:
    """Main configuration object.

    Uses convention-based schema configuration where the schema name
    determines all paths (sources, outputs, schema file).
    Supports global source/destination connectors with per-schema overrides.
    """
    schemas: list[SchemaConfig]
    llm: LLMConfig
    source: Optional[SourceConfig] = None  # Global source connector
    destination: Optional[DestinationConfig] = None  # Global destination connector
    inference: Optional[InferenceConfig] = None

    def get_schema(self, name: str) -> Optional[SchemaConfig]:
        """Get a schema config by name."""
        for schema in self.schemas:
            if schema.name == name:
                return schema
        return None

    def get_source_config(self, schema_config: SchemaConfig) -> SourceConfig:
        """Get effective source config for a schema (schema override or global)."""
        if schema_config.source:
            return schema_config.source
        if self.source:
            return self.source
        # Default: local source with convention path
        return SourceConfig(type="local", config={"path": schema_config.sources_path})

    def get_destination_config(self, schema_config: SchemaConfig) -> DestinationConfig:
        """Get effective destination config for a schema (schema override or global)."""
        if schema_config.destination:
            return schema_config.destination
        if self.destination:
            return self.destination
        # Default: JSONL destination with convention path
        return DestinationConfig(type="jsonl", config={"path": schema_config.output_path})


DEFAULT_CONFIG = """# doc2json Configuration
# Schema name determines all paths by convention:
#   schemas/<name>.py, sources/<name>/, outputs/<name>.jsonl

schemas:
  - example  # Simple: just the schema name

llm:
    provider: anthropic
    model: claude-sonnet-4-20250514
"""


def load_config(path: str = "doc2json.yml") -> Config:
    """Loads configuration from a YAML file.

    Args:
        path: Path to the config file

    Returns:
        Parsed Config object

    Raises:
        ConfigError: If config file is missing, invalid YAML, or missing required fields
    """
    if not os.path.exists(path):
        raise ConfigError(
            f"Configuration file not found: {path}\n"
            f"Run 'doc2json init' to create a new project."
        )

    try:
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(
            f"Invalid YAML in {path}:\n{e}"
        )

    if data is None:
        raise ConfigError(f"Config file {path} is empty.")

    # Substitute environment variables
    data = _substitute_env_vars(data)

    # Parse schemas - required
    schemas = _parse_schemas(data)

    # Parse LLM config
    llm_data = data.get("llm", {})
    llm = LLMConfig(
        provider=llm_data.get("provider", "anthropic"),
        model=llm_data.get("model", "claude-sonnet-4-20250514"),
        base_url=llm_data.get("base_url"),
        api_key=llm_data.get("api_key"),
    )

    # Parse optional global source config
    source = _parse_connector_config(data.get("source"))

    # Parse optional global destination config
    destination = _parse_connector_config(data.get("destination"))

    # Parse optional inference config
    inference = None
    if "inference" in data:
        inf_data = data["inference"]
        inference = InferenceConfig(mode=inf_data.get("mode", "auto"))

    return Config(
        schemas=schemas,
        llm=llm,
        source=source,
        destination=destination,
        inference=inference,
    )


def _expand_env_vars(value: Any) -> Any:
    """Expand environment variables in string values.

    Supports ${VAR} and $VAR syntax.
    """
    if not isinstance(value, str):
        return value

    # Expand ${VAR} syntax
    import re
    pattern = r'\$\{([^}]+)\}'

    def replace(match):
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))

    expanded = re.sub(pattern, replace, value)

    # Also support $VAR at start of string (simple case)
    if expanded.startswith('$') and not expanded.startswith('${'):
        var_name = expanded[1:].split()[0] if ' ' in expanded else expanded[1:]
        env_value = os.environ.get(var_name)
        if env_value:
            return env_value

    return expanded


def _parse_connector_config(data: Optional[dict]) -> Optional[SourceConfig]:
    """Parse a source or destination connector config."""
    if data is None:
        return None

    if not isinstance(data, dict):
        raise ConfigError("Connector config must be a dictionary.")

    conn_type = data.get("type")
    if not conn_type:
        raise ConfigError("Connector config requires 'type' field.")

    # Everything except 'type' goes into config, with env var expansion
    config = {k: _expand_env_vars(v) for k, v in data.items() if k != "type"}

    return SourceConfig(type=conn_type, config=config)


def _parse_schemas(data: dict) -> list[SchemaConfig]:
    """Parse schema configurations from config data.

    Supports both new 'schemas' format and legacy 'extraction'/'extractions' formats.
    """
    # New format: schemas list
    if "schemas" in data:
        schemas_data = data["schemas"]
        if not isinstance(schemas_data, list):
            raise ConfigError(
                "'schemas' must be a list.\n"
                "Example:\n\n"
                "schemas:\n"
                "  - invoices\n"
                "  - contracts"
            )
        if not schemas_data:
            raise ConfigError("'schemas' list cannot be empty.")

        schemas = []
        for i, item in enumerate(schemas_data):
            if isinstance(item, str):
                # Simple format: just schema name
                schemas.append(SchemaConfig(name=item))
            elif isinstance(item, dict):
                # Extended format: schema with options
                if "name" not in item:
                    raise ConfigError(
                        f"Missing 'name' in schemas[{i}].\n"
                        "Use either:\n"
                        "  - schema_name\n"
                        "Or:\n"
                        "  - name: schema_name\n"
                        "    assess: true"
                    )
                # Parse large_doc_strategy
                strategy_str = item.get("large_doc_strategy", "truncate")
                try:
                    strategy = LargeDocStrategy(strategy_str)
                except ValueError:
                    valid = ", ".join(s.value for s in LargeDocStrategy)
                    raise ConfigError(
                        f"Invalid large_doc_strategy '{strategy_str}' in schemas[{i}]. "
                        f"Valid options: {valid}"
                    )

                # Parse per-schema source/destination overrides
                source_override = _parse_connector_config(item.get("source"))
                dest_override = _parse_connector_config(item.get("destination"))

                schemas.append(SchemaConfig(
                    name=item["name"],
                    assess=item.get("assess", False),
                    large_doc_strategy=strategy,
                    max_chars=item.get("max_chars", MAX_CHARS_DEFAULT),
                    source=source_override,
                    destination=dest_override,
                ))
            else:
                raise ConfigError(
                    f"Invalid schema entry at index {i}. "
                    "Must be a string or object with 'name' field."
                )
        return schemas

    # Legacy format: extraction (single)
    if "extraction" in data:
        ext_data = data["extraction"]
        if not ext_data.get("schema"):
            raise ConfigError(
                "Missing required field: extraction.schema\n"
                "Consider migrating to the new 'schemas' format:\n\n"
                "schemas:\n"
                "  - my_schema"
            )
        return [SchemaConfig(
            name=ext_data["schema"],
            assess=ext_data.get("assess", False),
        )]

    # Legacy format: extractions (multiple)
    if "extractions" in data:
        extractions_data = data["extractions"]
        if not isinstance(extractions_data, list):
            raise ConfigError("'extractions' must be a list.")

        schemas = []
        for i, ext_data in enumerate(extractions_data):
            if not ext_data.get("schema"):
                raise ConfigError(
                    f"Missing 'schema' in extractions[{i}].\n"
                    "Consider migrating to the new 'schemas' format."
                )
            schemas.append(SchemaConfig(
                name=ext_data["schema"],
                assess=ext_data.get("assess", False),
            ))
        return schemas

    raise ConfigError(
        "Missing schema configuration.\n\n"
        "Add a 'schemas' section:\n\n"
        "schemas:\n"
        "  - invoices\n"
        "  - contracts\n\n"
        "Schema name determines all paths:\n"
        "  schemas/<name>.py\n"
        "  sources/<name>/\n"
        "  outputs/<name>.jsonl"
    )
