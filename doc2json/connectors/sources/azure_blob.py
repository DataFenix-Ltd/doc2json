"""Azure Blob Storage source connector."""

import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

from doc2json.connectors import DocumentRef

logger = logging.getLogger(__name__)


class AzureBlobSource:
    """Source connector for Azure Blob Storage.

    Downloads documents from an Azure container.

    Config:
        connection_string: Azure Storage connection string (required)
        container_name: Container name (required)
        prefix: Blob name prefix filter (optional)
    """

    def __init__(self, config: dict[str, Any]):
        self.conn_str = config.get("connection_string")
        if not self.conn_str:
            raise ValueError("AzureBlobSource requires 'connection_string'")
            
        self.container_name = config.get("container_name")
        if not self.container_name:
            raise ValueError("AzureBlobSource requires 'container_name'")
            
        self.prefix = config.get("prefix")
        
        self._service_client = None
        self._container_client = None
        self._temp_dir: Optional[tempfile.TemporaryDirectory] = None
        self._downloaded_files: dict[str, Path] = {}

    def connect(self) -> None:
        """Connect to Azure Blob Storage."""
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError:
            raise ImportError(
                "Azure Blob connector requires azure-storage-blob.\n"
                "Install with: pip install doc2json[azure-blob]"
            )

        self._service_client = BlobServiceClient.from_connection_string(self.conn_str)
        self._container_client = self._service_client.get_container_client(self.container_name)
        
        if not self._container_client.exists():
             raise ValueError(f"Azure container '{self.container_name}' does not exist")
             
        self._temp_dir = tempfile.TemporaryDirectory(prefix="doc2json_az_")
        logger.info(f"Connected to Azure container: {self.container_name}")

    def list_documents(self) -> list[DocumentRef]:
        return list(self.iter_documents())

    def iter_documents(self):
        if not self._container_client:
            raise RuntimeError("Not connected")

        # List blobs
        blobs = self._container_client.list_blobs(name_starts_with=self.prefix)
        
        for blob in blobs:
            yield DocumentRef(
                id=blob.name,
                name=Path(blob.name).name,
                size_bytes=blob.size,
                metadata={
                    "azure_blob_name": blob.name,
                    "container": self.container_name,
                    "last_modified": blob.last_modified.isoformat() if blob.last_modified else None
                }
            )

    def get_document_path(self, doc_ref: DocumentRef) -> Path:
        if not self._container_client:
            raise RuntimeError("Not connected")
        if not self._temp_dir:
            raise RuntimeError("Temp dir not initialized")

        blob_name = doc_ref.id
        if blob_name in self._downloaded_files:
            return self._downloaded_files[blob_name]
            
        local_path = Path(self._temp_dir.name) / doc_ref.name
        
        # Handle collision
        if local_path.exists():
            import hashlib
            name_hash = hashlib.md5(blob_name.encode()).hexdigest()[:8]
            local_path = Path(self._temp_dir.name) / f"{local_path.stem}_{name_hash}{local_path.suffix}"

        with open(local_path, "wb") as f:
            download_stream = self._container_client.download_blob(blob_name)
            f.write(download_stream.readall())
            
        self._downloaded_files[blob_name] = local_path
        return local_path

    def close(self) -> None:
        if self._temp_dir:
            self._temp_dir.cleanup()
            self._temp_dir = None
        self._downloaded_files.clear()
        self._service_client = None
        self._container_client = None

    def __enter__(self) -> "AzureBlobSource":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
