"""SQLAlchemy-based SQL destination connector.

Supports any database with a SQLAlchemy dialect:
- PostgreSQL: postgresql://user:pass@host/db
- MySQL: mysql+pymysql://user:pass@host/db
- SQLite: sqlite:///path/to/db.sqlite
- SQL Server: mssql+pyodbc://user:pass@host/db?driver=ODBC+Driver+17+for+SQL+Server
- Oracle: oracle+cx_oracle://user:pass@host/db
- And more...

See: https://docs.sqlalchemy.org/en/20/core/engines.html
"""

import json
import logging
from datetime import datetime
from typing import Any

from doc2json.connectors.destinations.sql_schema import (
    EXTRACTIONS_COLUMNS,
    EXTRACTIONS_INDEXES,
    METADATA_COLUMNS,
    METADATA_INDEXES,
    Column,
    ColumnType,
    transform_metadata,
    transform_record,
)

logger = logging.getLogger(__name__)

DEFAULT_TABLE = "extractions"
DEFAULT_METADATA_TABLE = "extraction_metadata"
DEFAULT_BATCH_SIZE = 100


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    """Parse datetime from ISO string or return as-is if already datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    # Parse ISO format string
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


class SQLDestination:
    """Generic SQL destination using SQLAlchemy.

    Supports any database with a SQLAlchemy dialect via connection URL.

    Config:
        connection_string: SQLAlchemy connection URL (required)
            Examples:
            - postgresql://user:pass@localhost/mydb
            - mysql+pymysql://user:pass@localhost/mydb
            - sqlite:///extractions.db
            - mssql+pyodbc://user:pass@server/db?driver=ODBC+Driver+17+for+SQL+Server

        table: Table name for extractions (default: extractions)
        metadata_table: Table name for metadata (default: extraction_metadata)
        auto_create: Whether to create tables if missing (default: True)
        batch_size: Records to buffer before committing (default: 100)
        schema: Database schema/namespace (optional, for Postgres/SQL Server)
    """

    def __init__(self, config: dict[str, Any]):
        """Initialize SQL destination."""
        self.connection_string = config.get("connection_string")
        if not self.connection_string:
            raise ValueError("SQLDestination requires 'connection_string'")

        self.table_name = config.get("table", DEFAULT_TABLE)
        self.metadata_table_name = config.get("metadata_table", DEFAULT_METADATA_TABLE)
        self.auto_create = config.get("auto_create", True)
        self.batch_size = config.get("batch_size", DEFAULT_BATCH_SIZE)
        self.db_schema = config.get("schema")  # Optional schema/namespace

        self._engine = None
        self._conn = None
        self._metadata = None
        self._extractions_table = None
        self._metadata_table = None

        self._extraction_buffer: list[dict] = []
        self._metadata_buffer: list[dict] = []
        self._extraction_ids: dict[str, int] = {}

    def connect(self) -> None:
        """Connect to database and set up tables."""
        try:
            from sqlalchemy import (
                Boolean,
                Column as SAColumn,
                DateTime,
                ForeignKey,
                Index,
                Integer,
                MetaData,
                String,
                Table,
                Text,
                create_engine,
                text,
            )
            from sqlalchemy.dialects import mysql, postgresql
        except ImportError:
            raise ImportError(
                "SQL connector requires SQLAlchemy.\n"
                "Install with: pip install doc2json[sql]"
            )

        self._engine = create_engine(self.connection_string)
        self._metadata = MetaData(schema=self.db_schema)

        # Detect dialect for JSON type selection
        dialect_name = self._engine.dialect.name
        logger.info(f"Detected SQL dialect: {dialect_name}")

        # Choose appropriate JSON type
        if dialect_name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB
            json_type = JSONB
        elif dialect_name == "mysql":
            from sqlalchemy import JSON
            json_type = JSON
        else:
            # Fallback: store as TEXT with JSON serialization
            from sqlalchemy import Text
            json_type = Text
            self._json_as_text = True

        if not hasattr(self, '_json_as_text'):
            self._json_as_text = False

        # Build extractions table
        self._extractions_table = Table(
            self.table_name,
            self._metadata,
            SAColumn("id", Integer, primary_key=True, autoincrement=True),
            SAColumn("source_file", Text, nullable=False),
            SAColumn("schema_name", Text, nullable=False),
            SAColumn("schema_version", Text),
            SAColumn("extracted_at", DateTime, server_default=text("CURRENT_TIMESTAMP")),
            SAColumn("data", json_type, nullable=False),
            SAColumn("error", Text),
            SAColumn("truncated", Boolean, server_default=text("false")),
            # Indexes
            Index(f"idx_{self.table_name}_schema_name", "schema_name"),
            Index(f"idx_{self.table_name}_source_file", "source_file"),
            Index(f"idx_{self.table_name}_extracted_at", "extracted_at"),
        )

        # Build metadata table
        self._metadata_table = Table(
            self.metadata_table_name,
            self._metadata,
            SAColumn("id", Integer, primary_key=True, autoincrement=True),
            SAColumn(
                "extraction_id",
                Integer,
                ForeignKey(f"{self.table_name}.id"),
                nullable=True,
            ),
            SAColumn("source_file", Text, nullable=False),
            SAColumn("started_at", DateTime),
            SAColumn("completed_at", DateTime),
            SAColumn("duration_ms", Integer),
            SAColumn("success", Boolean, server_default=text("true")),
            SAColumn("provider", Text),
            SAColumn("model", Text),
            SAColumn("char_count", Integer),
            SAColumn("page_count", Integer),
            SAColumn("truncated", Boolean, server_default=text("false")),
            SAColumn("input_tokens", Integer),
            SAColumn("output_tokens", Integer),
            SAColumn("error", Text),
            # Indexes
            Index(f"idx_{self.metadata_table_name}_extraction_id", "extraction_id"),
            Index(f"idx_{self.metadata_table_name}_source_file", "source_file"),
        )

        # Create tables if needed
        if self.auto_create:
            self._metadata.create_all(self._engine)
            logger.debug(f"Ensured tables exist: {self.table_name}, {self.metadata_table_name}")

        # Open connection
        self._conn = self._engine.connect()
        logger.info(f"Connected to {dialect_name} database")

    def write_record(self, record: dict[str, Any]) -> None:
        """Buffer a record for writing."""
        if self._conn is None:
            raise RuntimeError("Not connected")

        self._extraction_buffer.append(record)

        if len(self._extraction_buffer) >= self.batch_size:
            self._flush_extractions()

    def write_metadata(self, metadata: dict[str, Any]) -> None:
        """Buffer metadata for writing."""
        if self._conn is None:
            raise RuntimeError("Not connected")

        self._metadata_buffer.append(metadata)

        if len(self._metadata_buffer) >= self.batch_size:
            self._flush_metadata()

    def flush(self) -> None:
        """Flush all buffered data."""
        self._flush_extractions()
        self._flush_metadata()

    def _flush_extractions(self) -> None:
        """Flush extraction buffer to database."""
        if not self._extraction_buffer:
            return

        for record in self._extraction_buffer:
            row = transform_record(record)
            source_file = row["source_file"]

            # Serialize JSON if needed
            data = row["data"]
            if self._json_as_text:
                data = json.dumps(data)

            # Insert and get ID
            from sqlalchemy import insert

            stmt = insert(self._extractions_table).values(
                source_file=row["source_file"],
                schema_name=row["schema_name"],
                schema_version=row["schema_version"],
                data=data,
                error=row["error"],
                truncated=row["truncated"],
            )

            # Try to use RETURNING for efficiency
            dialect = self._engine.dialect.name
            if dialect in ("postgresql", "sqlite"):
                stmt = stmt.returning(self._extractions_table.c.id)
                result = self._conn.execute(stmt)
                extraction_id = result.scalar()
            else:
                # Fallback: insert then query for ID
                result = self._conn.execute(stmt)
                extraction_id = result.lastrowid

            if extraction_id:
                self._extraction_ids[source_file] = extraction_id

        self._conn.commit()
        self._extraction_buffer = []

    def _flush_metadata(self) -> None:
        """Flush metadata buffer to database."""
        if not self._metadata_buffer:
            return

        from sqlalchemy import insert

        rows_to_insert = []
        for metadata in self._metadata_buffer:
            row = transform_metadata(metadata)
            if row is None:
                continue

            # Look up extraction_id
            source_file = row["source_file"]
            extraction_id = self._extraction_ids.pop(source_file, None)
            row["extraction_id"] = extraction_id

            row["started_at"] = _parse_datetime(row.get("started_at"))
            row["completed_at"] = _parse_datetime(row.get("completed_at"))

            rows_to_insert.append(row)

        if rows_to_insert:
            stmt = insert(self._metadata_table)
            self._conn.execute(stmt, rows_to_insert)
            self._conn.commit()

        self._metadata_buffer = []

    def close(self) -> None:
        """Close database connection."""
        self.flush()
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
        self._extraction_ids = {}
        logger.debug("SQL connection closed")

    def __enter__(self) -> "SQLDestination":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
