"""Snowflake destination connector."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TABLE = "EXTRACTIONS"
DEFAULT_METADATA_TABLE = "EXTRACTION_METADATA"

# Declarative schema definitions for auto-migration
# Format: (column_name, type, default_expr_or_None)
EXTRACTIONS_SCHEMA: list[tuple[str, str, str | None]] = [
    ("ID", "NUMBER IDENTITY(1,1)", None),
    ("SOURCE_FILE", "VARCHAR NOT NULL", None),
    ("SCHEMA_NAME", "VARCHAR NOT NULL", None),
    ("SCHEMA_VERSION", "VARCHAR", None),
    ("EXTRACTED_AT", "TIMESTAMP_TZ", "CURRENT_TIMESTAMP()"),
    ("DATA", "VARIANT", None),
    ("ERROR", "VARCHAR", None),
    ("TRUNCATED", "BOOLEAN", None),
]

METADATA_SCHEMA: list[tuple[str, str, str | None]] = [
    ("ID", "NUMBER IDENTITY(1,1)", None),
    ("EXTRACTION_ID", "NUMBER", None),
    ("SOURCE_FILE", "VARCHAR NOT NULL", None),
    ("STARTED_AT", "TIMESTAMP_TZ", None),
    ("COMPLETED_AT", "TIMESTAMP_TZ", None),
    ("DURATION_MS", "NUMBER", None),
    ("SUCCESS", "BOOLEAN", None),
    ("PROVIDER", "VARCHAR", None),
    ("MODEL", "VARCHAR", None),
    ("CHAR_COUNT", "NUMBER", None),
    ("PAGE_COUNT", "NUMBER", None),
    ("TRUNCATED", "BOOLEAN", None),
    ("INPUT_TOKENS", "NUMBER", None),
    ("OUTPUT_TOKENS", "NUMBER", None),
    ("ERROR", "VARCHAR", None),
]


def _build_create_table_sql(table_name: str, schema: list[tuple[str, str, str | None]]) -> str:
    """Build CREATE TABLE statement from schema definition."""
    columns = []
    for col_name, col_type, default in schema:
        col_def = f"    {col_name} {col_type}"
        if default:
            col_def += f" DEFAULT {default}"
        columns.append(col_def)
    return f"CREATE TABLE IF NOT EXISTS {table_name} (\n" + ",\n".join(columns) + "\n)"

class SnowflakeDestination:
    """Destination connector for Snowflake.

    Stores extractions in a table using the VARIANT type for JSON data.

    Config:
        account: Snowflake account (e.g. 'xy12345.us-east-2')
        user: Username
        password: Password (not required if using authenticator)
        warehouse: Warehouse name
        database: Database name
        schema: Schema name
        role: Role (optional)
        authenticator: Auth method (optional) - use 'externalbrowser' for SSO
        table: Table for extractions (default: EXTRACTIONS)
        metadata_table: Table for metadata (default: EXTRACTION_METADATA)

    Authentication options:
        1. Password: Set 'password' field (supports ${ENV_VAR} syntax)
        2. Browser SSO: Set 'authenticator: externalbrowser' (opens browser)
        3. Other authenticators: 'snowflake_jwt', 'oauth', etc.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config

        # Determine auth method
        self.authenticator = config.get("authenticator")  # e.g., "externalbrowser"

        # Required config - password not required if using SSO
        required_fields = ["account", "user", "warehouse", "database", "schema"]
        if not self.authenticator:
            required_fields.append("password")

        for field in required_fields:
            if not config.get(field):
                raise ValueError(f"SnowflakeDestination requires '{field}'")
                
        self.table = config.get("table", DEFAULT_TABLE).upper()
        self.metadata_table = config.get("metadata_table", DEFAULT_METADATA_TABLE).upper()
        self.auto_create = config.get("auto_create", True)
        self.batch_size = config.get("batch_size", 100)
        
        self._conn = None
        self._cursor = None
        self._extraction_buffer = []
        self._metadata_buffer = []
        # Map source_file -> extraction_id for linking metadata
        self._extraction_ids: dict[str, int] = {}

    def connect(self) -> None:
        """Connect to Snowflake."""
        try:
            import snowflake.connector
        except ImportError:
            raise ImportError(
                "Snowflake connector requires snowflake-connector-python.\n"
                "Install with: pip install doc2json[snowflake]"
            )

        connect_params = {
            "account": self.config["account"],
            "user": self.config["user"],
            "warehouse": self.config["warehouse"],
            "database": self.config["database"],
            "schema": self.config["schema"],
            "role": self.config.get("role"),
        }

        if self.authenticator:
            connect_params["authenticator"] = self.authenticator
            logger.info(f"Using Snowflake authenticator: {self.authenticator}")
        else:
            connect_params["password"] = self.config["password"]

        self._conn = snowflake.connector.connect(**connect_params)
        self._cursor = self._conn.cursor()
        
        if self.auto_create:
            self._create_tables()
            
        logger.info(f"Connected to Snowflake: {self.config['database']}.{self.config['schema']}")

    def _create_tables(self) -> None:
        """Create tables if they don't exist, and migrate existing tables if needed."""
        # Create or migrate extractions table
        self._ensure_table(self.table, EXTRACTIONS_SCHEMA)
        # Create or migrate metadata table
        self._ensure_table(self.metadata_table, METADATA_SCHEMA)

    def _ensure_table(
        self, table_name: str, schema: list[tuple[str, str, str | None]]
    ) -> None:
        """Ensure table exists with all required columns, adding missing ones."""
        # First, try to create the table (will no-op if exists)
        create_sql = _build_create_table_sql(table_name, schema)
        self._cursor.execute(create_sql)

        # Get existing columns
        self._cursor.execute(f"""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        """, (self.config["schema"].upper(), table_name.upper()))

        existing_cols = {row[0].upper() for row in self._cursor.fetchall()}

        # Add any missing columns
        for col_name, col_type, default in schema:
            if col_name.upper() not in existing_cols:
                # Skip IDENTITY columns - can't add those after table creation
                if "IDENTITY" in col_type.upper():
                    continue
                # Strip NOT NULL for ALTER TABLE ADD (can't add NOT NULL to existing table easily)
                add_type = col_type.replace(" NOT NULL", "")
                alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {add_type}"
                if default:
                    alter_sql += f" DEFAULT {default}"
                logger.info(f"Adding column {col_name} to {table_name}")
                self._cursor.execute(alter_sql)

    def write_record(self, record: dict[str, Any]) -> None:
        """Buffer record for batch insert."""
        if not self._conn:
            raise RuntimeError("Not connected")
            
        self._extraction_buffer.append(record)
        if len(self._extraction_buffer) >= self.batch_size:
            self._flush_extractions()

    def write_metadata(self, metadata: dict[str, Any]) -> None:
        """Buffer metadata for batch insert."""
        if not self._conn:
            raise RuntimeError("Not connected")
            
        self._metadata_buffer.append(metadata)
        if len(self._metadata_buffer) >= self.batch_size:
            self._flush_metadata()

    def flush(self) -> None:
        """Flush all buffers."""
        self._flush_extractions()
        self._flush_metadata()

    def _flush_extractions(self) -> None:
        """Flush extraction buffer."""
        if not self._extraction_buffer:
            return

        # Insert rows one at a time using SELECT with PARSE_JSON
        # and capture the inserted ID for linking metadata
        for r in self._extraction_buffer:
            data = {k: v for k, v in r.items() if not k.startswith("_")}
            data_json = json.dumps(data)
            source_file = r.get("_source_file")

            # Use parameterized query for JSON to avoid issues with % characters in data
            query = f"""
            INSERT INTO {self.table}
            (SOURCE_FILE, SCHEMA_NAME, SCHEMA_VERSION, DATA, ERROR, TRUNCATED)
            SELECT %s, %s, %s, PARSE_JSON(%s), %s, %s
            """

            self._cursor.execute(query, (
                source_file,
                r.get("_schema"),
                r.get("_schema_version"),
                data_json,
                r.get("_error"),
                r.get("_truncated", False)
            ))

            # Get the inserted ID for linking metadata
            self._cursor.execute(f"SELECT MAX(ID) FROM {self.table} WHERE SOURCE_FILE = %s", (source_file,))
            result = self._cursor.fetchone()
            if result and result[0]:
                self._extraction_ids[source_file] = result[0]

        self._conn.commit()
        self._extraction_buffer = []

    def _flush_metadata(self) -> None:
        """Flush metadata buffer."""
        if not self._metadata_buffer:
            return

        values = []
        for m in self._metadata_buffer:
            if m.get("_type") != "extraction":
                continue

            source_file = m.get("source_file")
            # Look up the extraction_id we captured during _flush_extractions
            extraction_id = self._extraction_ids.pop(source_file, None)

            extract_tokens = m.get("extract_tokens", {})
            assess_tokens = m.get("assess_tokens", {})
            input_tokens = extract_tokens.get("input", 0) + assess_tokens.get("input", 0)
            output_tokens = extract_tokens.get("output", 0) + assess_tokens.get("output", 0)

            values.append((
                extraction_id,
                source_file,
                m.get("started_at"),
                m.get("completed_at"),
                m.get("duration_ms"),
                m.get("success", True),
                m.get("provider"),
                m.get("model"),
                m.get("char_count"),
                m.get("page_count"),
                m.get("truncated", False),
                input_tokens,
                output_tokens,
                m.get("error")
            ))

        query = f"""
        INSERT INTO {self.metadata_table}
        (EXTRACTION_ID, SOURCE_FILE, STARTED_AT, COMPLETED_AT, DURATION_MS, SUCCESS,
         PROVIDER, MODEL, CHAR_COUNT, PAGE_COUNT, TRUNCATED, INPUT_TOKENS, OUTPUT_TOKENS, ERROR)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        self._cursor.executemany(query, values)
        self._conn.commit()
        self._metadata_buffer = []

    def close(self) -> None:
        """Close connection."""
        self.flush()
        if self._cursor:
            self._cursor.close()
        if self._conn:
            self._conn.close()
        self._extraction_ids = {}
            
    def __enter__(self) -> "SnowflakeDestination":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
