"""Connector framework for input sources and output destinations."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Any, Optional, runtime_checkable


@dataclass
class DocumentRef:
    """Reference to a document in a source."""

    id: str  # Unique ID in source system
    name: str  # Display name / filename
    mime_type: Optional[str] = None  # e.g., "application/pdf"
    size_bytes: Optional[int] = None  # For progress/filtering
    metadata: dict[str, Any] = field(default_factory=dict)  # Source-specific metadata


@runtime_checkable
class SourceConnector(Protocol):
    """Protocol for input source connectors."""

    def connect(self) -> None:
        """Establish connection (auth, etc.)."""
        ...

    def list_documents(self) -> list[DocumentRef]:
        """List available documents (deprecated, use iter_documents)."""
        ...
    
    def iter_documents(self) -> Any: # Returns Iterator[DocumentRef]
        """Yield available documents one by one."""
        ...

    def get_document_path(self, doc_ref: DocumentRef) -> Path:
        """Get local path for document (download if needed)."""
        ...

    def close(self) -> None:
        """Clean up resources (temp files, connections)."""
        ...
    
    def __enter__(self) -> "SourceConnector":
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


@runtime_checkable
class DestinationConnector(Protocol):
    """Protocol for output destination connectors."""

    def connect(self) -> None:
        """Establish connection."""
        ...

    def write_record(self, record: dict[str, Any]) -> None:
        """Write a single extraction result."""
        ...

    def write_metadata(self, metadata: dict[str, Any]) -> None:
        """Write run metadata."""
        ...
        
    def flush(self) -> None:
        """Force write/commit of buffered data."""
        ...

    def close(self) -> None:
        """Clean up, commit transactions."""
        ...

    def __enter__(self) -> "DestinationConnector":
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


class SourceRegistry:
    """Registry for source connectors."""

    def __init__(self):
        self._sources: dict[str, type] = {}

    def register(self, type_name: str, connector_class: type) -> None:
        """Register a source connector class."""
        self._sources[type_name] = connector_class

    def get(self, type_name: str) -> type:
        """Get a source connector class by type name."""
        if type_name not in self._sources:
            available = ", ".join(self._sources.keys()) or "none"
            raise ValueError(
                f"Unknown source type: '{type_name}'. Available: {available}"
            )
        return self._sources[type_name]

    def create(self, type_name: str, config: dict[str, Any]) -> SourceConnector:
        """Create and return a source connector instance."""
        connector_class = self.get(type_name)
        return connector_class(config)


class DestinationRegistry:
    """Registry for destination connectors."""

    def __init__(self):
        self._destinations: dict[str, type] = {}

    def register(self, type_name: str, connector_class: type) -> None:
        """Register a destination connector class."""
        self._destinations[type_name] = connector_class

    def get(self, type_name: str) -> type:
        """Get a destination connector class by type name."""
        if type_name not in self._destinations:
            available = ", ".join(self._destinations.keys()) or "none"
            raise ValueError(
                f"Unknown destination type: '{type_name}'. Available: {available}"
            )
        return self._destinations[type_name]

    def create(
        self, type_name: str, config: dict[str, Any]
    ) -> DestinationConnector:
        """Create and return a destination connector instance."""
        connector_class = self.get(type_name)
        return connector_class(config)


# Global registries
_source_registry = SourceRegistry()
_destination_registry = DestinationRegistry()


def register_source(type_name: str, connector_class: type) -> None:
    """Register a source connector with the global registry."""
    _source_registry.register(type_name, connector_class)

# Register sources
try:
    from doc2json.connectors.sources.s3 import S3Source
    register_source("s3", S3Source)
except ImportError:
    pass

try:
    from doc2json.connectors.sources.azure_blob import AzureBlobSource
    register_source("azure_blob", AzureBlobSource)
except ImportError:
    pass

def register_destination(type_name: str, connector_class: type) -> None:
    """Register a destination connector with the global registry."""
    _destination_registry.register(type_name, connector_class)


def get_source(type_name: str, config: dict[str, Any]) -> SourceConnector:
    """Get a source connector instance from the global registry."""
    return _source_registry.create(type_name, config)


def get_destination(type_name: str, config: dict[str, Any]) -> DestinationConnector:
    """Get a destination connector instance from the global registry."""
    return _destination_registry.create(type_name, config)
