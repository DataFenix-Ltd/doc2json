"""MongoDB destination connector."""

import logging
from typing import Any

from doc2json.connectors import DestinationConnector

logger = logging.getLogger(__name__)


class MongoDBDestination:
    """Destination connector for MongoDB.
    
    Stores extractions in a document collection.
    
    Config:
        connection_string: MongoDB connection URI (required)
        database: Database name (required)
        collection: Collection name for extractions (default: extractions)
        metadata_collection: Collection for metadata (default: extraction_metadata)
    """

    def __init__(self, config: dict[str, Any]):
        """Initialize MongoDB destination."""
        self.connection_string = config.get("connection_string")
        if not self.connection_string:
            raise ValueError("MongoDBDestination requires 'connection_string'")
            
        self.db_name = config.get("database")
        if not self.db_name:
            raise ValueError("MongoDBDestination requires 'database'")
            
        self.collection_name = config.get("collection", "extractions")
        self.meta_collection_name = config.get("metadata_collection", "extraction_metadata")
        self.batch_size = config.get("batch_size", 100)

        self._client = None
        self._db = None
        self._collection = None
        self._meta_collection = None

        self._extraction_buffer = []
        self._metadata_buffer = []
        # Map source_file -> extraction ObjectId for linking metadata
        self._extraction_ids: dict[str, Any] = {}

    def connect(self) -> None:
        """Connect to MongoDB."""
        try:
            from pymongo import MongoClient
        except ImportError:
            raise ImportError(
                "MongoDB connector requires pymongo.\n"
                "Install with: pip install doc2json[mongodb]"
            )

        self._client = MongoClient(self.connection_string)
        self._db = self._client[self.db_name]
        
        self._collection = self._db[self.collection_name]
        self._meta_collection = self._db[self.meta_collection_name]
        
        logger.info(f"Connected to MongoDB: {self.db_name}")

    def write_record(self, record: dict[str, Any]) -> None:
        """Buffer a record for writing."""
        if self._collection is None:
            raise RuntimeError("Not connected")
            
        # MongoDB handles nested JSON naturally, so we just write it directly
        self._extraction_buffer.append(record)
        
        if len(self._extraction_buffer) >= self.batch_size:
            self.flush()

    def write_metadata(self, metadata: dict[str, Any]) -> None:
        """Buffer metadata for writing."""
        if self._meta_collection is None:
            raise RuntimeError("Not connected")
            
        self._metadata_buffer.append(metadata)
        
        if len(self._metadata_buffer) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        """Write buffered records to MongoDB."""
        if self._extraction_buffer:
            # Insert and capture the inserted IDs for linking metadata
            result = self._collection.insert_many(self._extraction_buffer)
            for doc, inserted_id in zip(self._extraction_buffer, result.inserted_ids):
                source_file = doc.get("_source_file")
                if source_file:
                    self._extraction_ids[source_file] = inserted_id
            self._extraction_buffer = []

        if self._metadata_buffer:
            # Add extraction_id to metadata documents before inserting
            for meta in self._metadata_buffer:
                if meta.get("_type") == "extraction":
                    source_file = meta.get("source_file")
                    extraction_id = self._extraction_ids.pop(source_file, None)
                    if extraction_id:
                        meta["extraction_id"] = extraction_id
            self._meta_collection.insert_many(self._metadata_buffer)
            self._metadata_buffer = []

    def close(self) -> None:
        """Close connection."""
        self.flush()  # Ensure pending writes are saved
        if self._client is not None:
            self._client.close()
            self._client = None
        self._extraction_ids = {}
            
    def __enter__(self) -> "MongoDBDestination":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
