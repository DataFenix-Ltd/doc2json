"""AWS S3 source connector."""

import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

from doc2json.connectors import DocumentRef

logger = logging.getLogger(__name__)


class S3Source:
    """Source connector for AWS S3.

    Downloads documents from an S3 bucket with optional prefix.

    Config:
        bucket: S3 bucket name (required)
        prefix: Key prefix to filter objects (optional)
        aws_access_key_id: AWS access key (optional, uses env vars/profile if omitted)
        aws_secret_access_key: AWS secret key (optional)
        region_name: AWS region (optional)
    """

    def __init__(self, config: dict[str, Any]):
        self.bucket_name = config.get("bucket")
        if not self.bucket_name:
            raise ValueError("S3Source requires 'bucket' in config")

        self.prefix = config.get("prefix", "")
        
        self.aws_config = {
            "aws_access_key_id": config.get("aws_access_key_id"),
            "aws_secret_access_key": config.get("aws_secret_access_key"),
            "region_name": config.get("region_name"),
        }
        # Filter out None values to let boto3 use defaults
        self.aws_config = {k: v for k, v in self.aws_config.items() if v is not None}

        self._s3_client = None
        self._temp_dir: Optional[tempfile.TemporaryDirectory] = None
        self._downloaded_files: dict[str, Path] = {}

    def connect(self) -> None:
        """Connect to AWS S3."""
        try:
            import boto3
            import botocore.exceptions
        except ImportError:
            raise ImportError(
                "AWS S3 connector requires boto3.\n"
                "Install with: pip install doc2json[s3]"
            )

        self._s3_client = boto3.client("s3", **self.aws_config)
        
        # Verify bucket access
        try:
            self._s3_client.head_bucket(Bucket=self.bucket_name)
        except botocore.exceptions.ClientError as e:
            raise ValueError(f"Cannot access S3 bucket '{self.bucket_name}': {e}")
            
        self._temp_dir = tempfile.TemporaryDirectory(prefix="doc2json_s3_")
        logger.info(f"Connected to S3 bucket: {self.bucket_name}")

    def list_documents(self) -> list[DocumentRef]:
        """List all documents (deprecated)."""
        return list(self.iter_documents())

    def iter_documents(self):
        """Yield documents from S3 bucket."""
        if not self._s3_client:
            raise RuntimeError("Not connected. Call connect() first.")

        paginator = self._s3_client.get_paginator("list_objects_v2")
        
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=self.prefix):
            if "Contents" not in page:
                continue
                
            for obj in page["Contents"]:
                key = obj["Key"]
                
                # Skip folders/prefixes themselves if returned
                if key.endswith("/"):
                    continue
                    
                size = obj["Size"]
                # Rudimentary mime type guess based on extension, 
                # or we could head_object but that's slow for listing.
                # We'll leave mime_type None and let the parser detect it by extension/content.
                
                yield DocumentRef(
                    id=key,
                    name=Path(key).name,
                    size_bytes=size,
                    metadata={
                        "s3_key": key,
                        "s3_bucket": self.bucket_name,
                        "last_modified": obj["LastModified"].isoformat()
                    }
                )

    def get_document_path(self, doc_ref: DocumentRef) -> Path:
        """Download object to temp file."""
        if not self._s3_client:
            raise RuntimeError("Not connected")
        if not self._temp_dir:
            raise RuntimeError("Temp directory not initialized")

        key = doc_ref.id
        if key in self._downloaded_files:
            return self._downloaded_files[key]

        local_path = Path(self._temp_dir.name) / doc_ref.name
        
        # Handle duplicate filenames in flat temp dir
        if local_path.exists():
            # append hash to name to avoid collision if keys have same filename but diff folders
            import hashlib
            name_hash = hashlib.md5(key.encode()).hexdigest()[:8]
            local_path = Path(self._temp_dir.name) / f"{local_path.stem}_{name_hash}{local_path.suffix}"

        self._s3_client.download_file(self.bucket_name, key, str(local_path))
        self._downloaded_files[key] = local_path
        
        return local_path

    def close(self) -> None:
        """Cleanup."""
        if self._temp_dir:
            self._temp_dir.cleanup()
            self._temp_dir = None
        self._downloaded_files.clear()
        self._s3_client = None

    def __enter__(self) -> "S3Source":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
