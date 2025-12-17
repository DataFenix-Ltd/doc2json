"""PostgreSQL destination connector."""

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default table schema
DEFAULT_TABLE = "extractions"
DEFAULT_METADATA_TABLE = "extraction_metadata"

DEFAULT_BATCH_SIZE = 100

# Declarative schema definitions for auto-migration
# Format: (column_name, type, default_expr_or_None, is_primary_key)
EXTRACTIONS_SCHEMA: list[tuple[str, str, str | None, bool]] = [
    ("id", "SERIAL", None, True),
    ("source_file", "TEXT NOT NULL", None, False),
    ("schema_name", "TEXT NOT NULL", None, False),
    ("schema_version", "TEXT", None, False),
    ("extracted_at", "TIMESTAMPTZ", "NOW()", False),
    ("data", "JSONB NOT NULL", None, False),
    ("error", "TEXT", None, False),
    ("truncated", "BOOLEAN", "FALSE", False),
]

# For metadata, extraction_id references extractions(id)
METADATA_SCHEMA: list[tuple[str, str, str | None, bool]] = [
    ("id", "SERIAL", None, True),
    ("extraction_id", "INTEGER", None, False),  # FK added separately
    ("source_file", "TEXT NOT NULL", None, False),
    ("started_at", "TIMESTAMPTZ", None, False),
    ("completed_at", "TIMESTAMPTZ", None, False),
    ("duration_ms", "INTEGER", None, False),
    ("success", "BOOLEAN", "TRUE", False),
    ("provider", "TEXT", None, False),
    ("model", "TEXT", None, False),
    ("char_count", "INTEGER", None, False),
    ("page_count", "INTEGER", None, False),
    ("truncated", "BOOLEAN", "FALSE", False),
    ("input_tokens", "INTEGER", None, False),
    ("output_tokens", "INTEGER", None, False),
    ("error", "TEXT", None, False),
]

EXTRACTIONS_INDEXES = ["schema_name", "source_file", "extracted_at"]
METADATA_INDEXES = ["extraction_id", "source_file"]


class PostgresDestination:
    """Destination connector for PostgreSQL.

    Stores extraction results as JSONB for maximum flexibility.
    Metadata table has one row per extraction, joinable via extraction_id.

    Config:
        connection_string: Full PostgreSQL connection URI (optional)
        OR individual params:
            host: Database host (default: localhost)
            port: Database port (default: 5432)
            database: Database name (required if no connection_string)
            user: Database user (required if no connection_string)
            password: Database password (optional)
        table: Table name for extractions (default: extractions)
        metadata_table: Table name for metadata (default: extraction_metadata)
        auto_create: Whether to create tables if they don't exist (default: True)
    """

    def __init__(self, config: dict[str, Any]):
        """Initialize PostgreSQL destination."""
        self.connection_string = config.get("connection_string")
        self.host = config.get("host", "localhost")
        self.port = config.get("port", 5432)
        self.database = config.get("database")
        self.user = config.get("user")
        self.password = config.get("password")

        self.table = config.get("table", DEFAULT_TABLE)
        self.metadata_table = config.get("metadata_table", DEFAULT_METADATA_TABLE)
        self.auto_create = config.get("auto_create", True)
        self.batch_size = config.get("batch_size", DEFAULT_BATCH_SIZE)

        self._pending_commits = 0

        # Validate config
        if not self.connection_string:
            if not self.database:
                raise ValueError("PostgresDestination requires 'database' in config")
            if not self.user:
                raise ValueError("PostgresDestination requires 'user' in config")

        self._conn = None
        self._cursor = None
        # Map source_file -> extraction_id for linking metadata
        self._extraction_ids: dict[str, int] = {}

    def connect(self) -> None:
        """Connect to PostgreSQL and optionally create tables."""
        try:
            import psycopg2
            from psycopg2 import sql
            self._sql = sql
        except ImportError:
            raise ImportError(
                "PostgreSQL connector requires psycopg2.\n"
                "Install with: pip install doc2json[postgres]"
            )

        # Connect using connection string or individual params
        if self.connection_string:
            self._conn = psycopg2.connect(self.connection_string)
        else:
            self._conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
            )

        self._cursor = self._conn.cursor()

        # Auto-create tables if enabled
        if self.auto_create:
            self._create_tables()

        self._extraction_ids = {}
        logger.info(f"Connected to PostgreSQL database")

    def _create_tables(self) -> None:
        """Create tables if they don't exist, and migrate existing tables if needed."""
        # Create or migrate extractions table
        self._ensure_table(self.table, EXTRACTIONS_SCHEMA, EXTRACTIONS_INDEXES)
        # Create or migrate metadata table (with FK to extractions)
        self._ensure_table(
            self.metadata_table,
            METADATA_SCHEMA,
            METADATA_INDEXES,
            foreign_keys=[("extraction_id", self.table, "id")],
        )
        self._conn.commit()
        logger.debug(f"Ensured tables exist: {self.table}, {self.metadata_table}")

    def _ensure_table(
        self,
        table_name: str,
        schema: list[tuple[str, str, str | None, bool]],
        indexes: list[str],
        foreign_keys: list[tuple[str, str, str]] | None = None,
    ) -> None:
        """Ensure table exists with all required columns, adding missing ones."""
        table_id = self._sql.Identifier(table_name)

        # Build CREATE TABLE statement
        col_defs = []
        for col_name, col_type, default, is_pk in schema:
            col_def = f"{col_name} {col_type}"
            if is_pk:
                col_def += " PRIMARY KEY"
            elif default:
                col_def += f" DEFAULT {default}"
            col_defs.append(col_def)

        create_sql = f"CREATE TABLE IF NOT EXISTS {{}} ({', '.join(col_defs)})"
        with self._conn.cursor() as cur:
            cur.execute(self._sql.SQL(create_sql).format(table_id))

            # Get existing columns
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s
            """, (table_name,))
            existing_cols = {row[0].lower() for row in cur.fetchall()}

            # Add missing columns
            for col_name, col_type, default, is_pk in schema:
                if col_name.lower() not in existing_cols:
                    # Skip SERIAL/PRIMARY KEY - can't add after creation
                    if is_pk or "SERIAL" in col_type.upper():
                        continue
                    # Strip NOT NULL for ALTER TABLE ADD
                    add_type = col_type.replace(" NOT NULL", "").replace("NOT NULL", "")
                    alter_sql = self._sql.SQL("ALTER TABLE {} ADD COLUMN {} ").format(
                        table_id, self._sql.Identifier(col_name)
                    ) + self._sql.SQL(add_type)
                    logger.info(f"Adding column {col_name} to {table_name}")
                    cur.execute(alter_sql)

            # Create indexes
            for idx_col in indexes:
                idx_name = f"idx_{table_name}_{idx_col}"
                cur.execute(self._sql.SQL(
                    "CREATE INDEX IF NOT EXISTS {} ON {} ({})"
                ).format(
                    self._sql.Identifier(idx_name),
                    table_id,
                    self._sql.Identifier(idx_col),
                ))

            # Add foreign keys (best effort - ignore if already exists)
            if foreign_keys:
                for fk_col, ref_table, ref_col in foreign_keys:
                    fk_name = f"fk_{table_name}_{fk_col}"
                    try:
                        cur.execute(self._sql.SQL(
                            "ALTER TABLE {} ADD CONSTRAINT {} FOREIGN KEY ({}) REFERENCES {}({})"
                        ).format(
                            table_id,
                            self._sql.Identifier(fk_name),
                            self._sql.Identifier(fk_col),
                            self._sql.Identifier(ref_table),
                            self._sql.Identifier(ref_col),
                        ))
                    except Exception:
                        pass  # FK likely already exists

    def write_record(self, record: dict[str, Any]) -> None:
        """Write a single extraction result to PostgreSQL."""
        if not self._conn or not self._cursor:
            raise RuntimeError("Not connected. Call connect() first.")

        # Extract metadata fields (prefixed with underscore in output format)
        source_file = record.get("_source_file", "")
        schema_name = record.get("_schema", "")
        schema_version = record.get("_schema_version")
        error = record.get("_error")
        truncated = record.get("_truncated", False)

        # Extract the actual data (everything except underscore-prefixed fields)
        data = {k: v for k, v in record.items() if not k.startswith("_")}

        # Prepare SQL with safe identifiers
        query = self._sql.SQL("""
            INSERT INTO {}
            (source_file, schema_name, schema_version, data, error, truncated)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """).format(self._sql.Identifier(self.table))

        self._cursor.execute(
            query,
            (
                source_file,
                schema_name,
                schema_version,
                json.dumps(data),
                error,
                truncated,
            ),
        )
        extraction_id = self._cursor.fetchone()[0]
        
        self._pending_commits += 1
        if self._pending_commits >= self.batch_size:
            self._conn.commit()
            self._pending_commits = 0

        # Store extraction ID for linking metadata later
        self._extraction_ids[source_file] = extraction_id

    def write_metadata(self, metadata: dict[str, Any]) -> None:
        """Write metadata to PostgreSQL."""
        if not self._conn or not self._cursor:
            raise RuntimeError("Not connected. Call connect() first.")

        # Skip run summary - we only want per-extraction metadata
        if metadata.get("_type") != "extraction":
            return

        source_file = metadata.get("source_file", "")
        # Pop the ID to free memory (assuming 1:1 metadata:extraction record)
        extraction_id = self._extraction_ids.pop(source_file, None)

        # Extract token counts from nested structure
        extract_tokens = metadata.get("extract_tokens", {})
        assess_tokens = metadata.get("assess_tokens", {})
        input_tokens = extract_tokens.get("input", 0) + assess_tokens.get("input", 0)
        output_tokens = extract_tokens.get("output", 0) + assess_tokens.get("output", 0)

        self._cursor.execute(
            self._sql.SQL("""
            INSERT INTO {}
            (extraction_id, source_file, started_at, completed_at, duration_ms, success,
             provider, model, char_count, page_count, truncated, input_tokens, output_tokens, error)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """).format(self._sql.Identifier(self.metadata_table)),
            (
                extraction_id,
                source_file,
                metadata.get("started_at"),
                metadata.get("completed_at"),
                metadata.get("duration_ms"),
                metadata.get("success", True),
                metadata.get("provider"),
                metadata.get("model"),
                metadata.get("char_count"),
                metadata.get("page_count"),
                metadata.get("truncated", False),
                input_tokens if input_tokens else None,
                output_tokens if output_tokens else None,
                metadata.get("error"),
            ),
        )
        
        self._pending_commits += 1
        if self._pending_commits >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        """Force write/commit of buffered data."""
        if self._conn:
            self._conn.commit()
            self._pending_commits = 0

    def close(self) -> None:
        """Close the database connection."""
        if self._cursor:
            self._cursor.close()
            self._cursor = None
        if self._conn:
            # Final commit for any pending writes
            if self._pending_commits > 0:
                self.flush()
            self._conn.close()
            self._conn = None
        self._extraction_ids = {}
        logger.debug("PostgreSQL connection closed")

    def __enter__(self) -> "PostgresDestination":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
