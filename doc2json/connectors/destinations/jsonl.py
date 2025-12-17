"""JSONL file destination connector."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


class JSONLDestination:
    """Destination connector for local JSONL files."""

    def __init__(self, config: dict[str, Any]):
        """Initialize JSONL destination.

        Config:
            path: Output file path (required)
            timestamp: Whether to add timestamp suffix to filename (default: True)
        """
        base_path = Path(config.get("path", ""))
        if not base_path:
            raise ValueError("JSONLDestination requires 'path' in config")

        # Add timestamp suffix to avoid overwriting previous runs
        if config.get("timestamp", True):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Insert timestamp before .jsonl extension
            stem = base_path.stem  # e.g., "invoice"
            suffix = base_path.suffix  # e.g., ".jsonl"
            self.path = base_path.parent / f"{stem}_{timestamp}{suffix}"
        else:
            self.path = base_path

        self._file = None
        self._meta_file = None
        # Map source_file -> extraction_id (UUID) for linking metadata
        self._extraction_ids: dict[str, str] = {}

    def connect(self) -> None:
        """Open the output file for writing."""
        # Ensure parent directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Open main output file
        self._file = open(self.path, "w")

        # Open metadata file
        meta_path = Path(str(self.path).replace(".jsonl", ".meta.jsonl"))
        self._meta_file = open(meta_path, "w")

    def write_record(self, record: dict[str, Any]) -> None:
        """Write a single extraction result as a JSON line."""
        if self._file is None:
            raise RuntimeError("Destination not connected. Call connect() first.")

        source_file = record.get("_source_file")

        # Generate UUID for this extraction (used to link metadata)
        extraction_id = str(uuid.uuid4())
        self._extraction_ids[source_file] = extraction_id

        # Add extraction_id to record
        output = {"_extraction_id": extraction_id, **record}
        self._file.write(json.dumps(output) + "\n")

    def write_metadata(self, metadata: dict[str, Any]) -> None:
        """Write metadata to the metadata file."""
        if self._meta_file is None:
            raise RuntimeError("Destination not connected. Call connect() first.")

        # Add extraction_id to per-file metadata
        if metadata.get("_type") == "extraction":
            source_file = metadata.get("source_file")
            extraction_id = self._extraction_ids.pop(source_file, None)
            if extraction_id:
                metadata = {"extraction_id": extraction_id, **metadata}

        self._meta_file.write(json.dumps(metadata) + "\n")

    def flush(self) -> None:
        """Force write/commit of buffered data."""
        if self._file:
            self._file.flush()
        if self._meta_file:
            self._meta_file.flush()

    def close(self) -> None:
        """Close the output files."""
        if self._file:
            self._file.close()
            self._file = None
        if self._meta_file:
            self._meta_file.close()
            self._meta_file = None
        self._extraction_ids = {}

    def __enter__(self) -> "JSONLDestination":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @property
    def output_path(self) -> Path:
        """Return the output path for logging."""
        return self.path

    @property
    def metadata_path(self) -> Path:
        """Return the metadata path for logging."""
        return Path(str(self.path).replace(".jsonl", ".meta.jsonl"))
