"""BigQuery destination connector."""

import json
import logging
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Declarative schema definitions for auto-migration
# Format: (field_name, bq_type, mode)
EXTRACTIONS_SCHEMA: list[tuple[str, str, str]] = [
    ("extraction_id", "STRING", "REQUIRED"),  # Client-generated UUID
    ("source_file", "STRING", "REQUIRED"),
    ("schema_name", "STRING", "REQUIRED"),
    ("schema_version", "STRING", "NULLABLE"),
    ("extracted_at", "TIMESTAMP", "NULLABLE"),
    ("data", "JSON", "REQUIRED"),
    ("error", "STRING", "NULLABLE"),
    ("truncated", "BOOLEAN", "NULLABLE"),
]

METADATA_SCHEMA: list[tuple[str, str, str]] = [
    ("extraction_id", "STRING", "NULLABLE"),  # FK to extractions.extraction_id
    ("source_file", "STRING", "REQUIRED"),
    ("started_at", "TIMESTAMP", "NULLABLE"),
    ("completed_at", "TIMESTAMP", "NULLABLE"),
    ("duration_ms", "INTEGER", "NULLABLE"),
    ("success", "BOOLEAN", "NULLABLE"),
    ("provider", "STRING", "NULLABLE"),
    ("model", "STRING", "NULLABLE"),
    ("char_count", "INTEGER", "NULLABLE"),
    ("page_count", "INTEGER", "NULLABLE"),
    ("truncated", "BOOLEAN", "NULLABLE"),
    ("input_tokens", "INTEGER", "NULLABLE"),
    ("output_tokens", "INTEGER", "NULLABLE"),
    ("error", "STRING", "NULLABLE"),
]

class BigQueryDestination:
    """Destination connector for Google BigQuery.
    
    Streams extractions to a BigQuery table.
    
    Config:
        project_id: GCP Project ID
        dataset_id: Dataset ID
        table_id: Table ID for extractions (default: extractions)
        metadata_table_id: Table ID for metadata (default: extraction_metadata)
        credentials_file: Path to service account JSON (optional)
        location: Dataset location (default: US)
    """

    def __init__(self, config: dict[str, Any]):
        self.project_id = config.get("project_id")
        self.dataset_id = config.get("dataset_id")
        self.location = config.get("location", "US")
        
        if not self.project_id or not self.dataset_id:
            raise ValueError("BigQueryDestination requires 'project_id' and 'dataset_id'")
            
        self.table_id = config.get("table_id", "extractions")
        self.meta_table_id = config.get("metadata_table_id", "extraction_metadata")
        self.credentials_file = config.get("credentials_file")
        self.batch_size = config.get("batch_size", 100)
        
        self._client = None
        self._extraction_buffer = []
        self._metadata_buffer = []
        # Map source_file -> extraction_id (UUID) for linking metadata
        self._extraction_ids: dict[str, str] = {}

    def connect(self) -> None:
        """Connect to BigQuery."""
        try:
            from google.cloud import bigquery
            from google.oauth2 import service_account
        except ImportError:
            raise ImportError(
                "BigQuery connector requires google-cloud-bigquery.\n"
                "Install with: pip install doc2json[bigquery]"
            )

        if self.credentials_file:
            creds = service_account.Credentials.from_service_account_file(self.credentials_file)
            self._client = bigquery.Client(project=self.project_id, credentials=creds)
        else:
            self._client = bigquery.Client(project=self.project_id)
            
        self._ensure_dataset()
        self._ensure_tables()
        
        logger.info(f"Connected to BigQuery: {self.dataset_id}")

    def _ensure_dataset(self) -> None:
        from google.cloud import bigquery
        from google.cloud.exceptions import NotFound
        dataset_ref = self._client.dataset(self.dataset_id)
        try:
            self._client.get_dataset(dataset_ref)
        except NotFound:
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = self.location
            self._client.create_dataset(dataset)

    def _ensure_tables(self) -> None:
        """Create tables if they don't exist, and migrate existing tables if needed."""
        self._ensure_table(
            self.table_id,
            EXTRACTIONS_SCHEMA,
            clustering_fields=["schema_name"],
        )
        self._ensure_table(self.meta_table_id, METADATA_SCHEMA)

    def _ensure_table(
        self,
        table_id: str,
        schema_def: list[tuple[str, str, str]],
        clustering_fields: list[str] | None = None,
    ) -> None:
        """Ensure table exists with all required columns, adding missing ones."""
        from google.cloud import bigquery
        from google.cloud.exceptions import NotFound

        # Build schema from definition
        schema = [
            bigquery.SchemaField(name, bq_type, mode=mode)
            for name, bq_type, mode in schema_def
        ]

        table_ref = self._client.dataset(self.dataset_id).table(table_id)

        try:
            existing_table = self._client.get_table(table_ref)
            # Table exists - check for missing columns
            existing_fields = {f.name.lower() for f in existing_table.schema}
            new_fields = []

            for name, bq_type, mode in schema_def:
                if name.lower() not in existing_fields:
                    # BigQuery only allows adding NULLABLE columns to existing tables
                    new_fields.append(bigquery.SchemaField(name, bq_type, mode="NULLABLE"))
                    logger.info(f"Adding column {name} to {table_id}")

            if new_fields:
                # Update schema with new fields
                updated_schema = list(existing_table.schema) + new_fields
                existing_table.schema = updated_schema
                self._client.update_table(existing_table, ["schema"])

        except NotFound:
            # Create new table
            table = bigquery.Table(table_ref, schema=schema)
            if clustering_fields:
                table.clustering_fields = clustering_fields
            self._client.create_table(table)

    def write_record(self, record: dict[str, Any]) -> None:
        """Buffer for streaming insert."""
        if not self._client:
            raise RuntimeError("Not connected")

        data = {k: v for k, v in record.items() if not k.startswith("_")}
        source_file = record.get("_source_file")

        # Generate UUID for this extraction (used to link metadata)
        extraction_id = str(uuid.uuid4())
        self._extraction_ids[source_file] = extraction_id

        row = {
            "extraction_id": extraction_id,
            "source_file": source_file,
            "schema_name": record.get("_schema"),
            "schema_version": record.get("_schema_version"),
            "extracted_at": datetime.now().isoformat(),
            "data": json.dumps(data),
            "error": record.get("_error"),
            "truncated": record.get("_truncated", False)
        }

        self._extraction_buffer.append(row)
        if len(self._extraction_buffer) >= self.batch_size:
            self._flush_extractions()

    def write_metadata(self, metadata: dict[str, Any]) -> None:
        """Buffer metadata."""
        if not self._client:
            raise RuntimeError("Not connected")

        if metadata.get("_type") != "extraction":
            logger.debug(f"Skipping non-extraction metadata: {metadata.get('_type')}")
            return

        source_file = metadata.get("source_file")
        # Look up the extraction_id we generated in write_record
        extraction_id = self._extraction_ids.pop(source_file, None)

        logger.debug(f"Buffering metadata for: {source_file}")
        extract_tokens = metadata.get("extract_tokens", {})
        assess_tokens = metadata.get("assess_tokens", {})

        row = {
            "extraction_id": extraction_id,
            "source_file": source_file,
            "started_at": self._fmt_date(metadata.get("started_at")),
            "completed_at": self._fmt_date(metadata.get("completed_at")),
            "duration_ms": metadata.get("duration_ms"),
            "success": metadata.get("success", True),
            "provider": metadata.get("provider"),
            "model": metadata.get("model"),
            "char_count": metadata.get("char_count"),
            "page_count": metadata.get("page_count"),
            "truncated": metadata.get("truncated", False),
            "input_tokens": extract_tokens.get("input", 0) + assess_tokens.get("input", 0),
            "output_tokens": extract_tokens.get("output", 0) + assess_tokens.get("output", 0),
            "error": metadata.get("error"),
        }

        self._metadata_buffer.append(row)
        if len(self._metadata_buffer) >= self.batch_size:
            self._flush_metadata()
            
    def _fmt_date(self, dt):
        if dt is None:
            return None
        # Handle both datetime objects and ISO format strings
        if isinstance(dt, str):
            return dt
        return dt.isoformat()

    def flush(self) -> None:
        self._flush_extractions()
        self._flush_metadata()

    def _flush_extractions(self) -> None:
        if not self._extraction_buffer:
            return

        table_ref = self._client.dataset(self.dataset_id).table(self.table_id)
        errors = self._client.insert_rows_json(table_ref, self._extraction_buffer)
        row_count = len(self._extraction_buffer)
        self._extraction_buffer = []
        if errors:
            raise RuntimeError(
                f"BigQuery insert failed for {len(errors)}/{row_count} rows: {errors}"
            )

    def _flush_metadata(self) -> None:
        if not self._metadata_buffer:
            logger.debug("No metadata to flush")
            return

        logger.info(f"Flushing {len(self._metadata_buffer)} metadata rows to BigQuery")
        table_ref = self._client.dataset(self.dataset_id).table(self.meta_table_id)
        errors = self._client.insert_rows_json(table_ref, self._metadata_buffer)
        row_count = len(self._metadata_buffer)
        self._metadata_buffer = []
        if errors:
            raise RuntimeError(
                f"BigQuery metadata insert failed for {len(errors)}/{row_count} rows: {errors}"
            )

    def close(self) -> None:
        self.flush()
        self._client = None
        self._extraction_ids = {}
        
    def __enter__(self) -> "BigQueryDestination":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
