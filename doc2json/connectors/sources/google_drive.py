"""Google Drive source connector."""

import io
import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

from doc2json.connectors import DocumentRef

logger = logging.getLogger(__name__)

# Supported Google Workspace export formats
GOOGLE_WORKSPACE_EXPORTS = {
    "application/vnd.google-apps.document": {
        "mime_type": "application/pdf",
        "extension": ".pdf",
    },
    "application/vnd.google-apps.spreadsheet": {
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "extension": ".xlsx",
    },
    "application/vnd.google-apps.presentation": {
        "mime_type": "application/pdf",
        "extension": ".pdf",
    },
}

# Skip these Google Workspace types (not exportable as documents)
SKIP_MIME_TYPES = {
    "application/vnd.google-apps.folder",
    "application/vnd.google-apps.shortcut",
    "application/vnd.google-apps.form",
}


class GoogleDriveSource:
    """Source connector for Google Drive.

    Authenticates using a service account credentials file and lists/downloads
    documents from a specified folder.

    Config:
        folder_id: Google Drive folder ID (required)
        credentials_file: Path to service account JSON (optional, defaults to
                          GOOGLE_APPLICATION_CREDENTIALS env var)
        recursive: Whether to include subfolders (default: True)
    """

    def __init__(self, config: dict[str, Any]):
        """Initialize Google Drive source.

        Config:
            folder_id: Google Drive folder ID (required)
            credentials_file: Path to service account JSON credentials
            recursive: Include subfolders (default: True)
        """
        self.folder_id = config.get("folder_id")
        if not self.folder_id:
            raise ValueError("GoogleDriveSource requires 'folder_id' in config")

        self.credentials_file = config.get("credentials_file")
        self.recursive = config.get("recursive", True)

        self._service = None
        self._temp_dir: Optional[tempfile.TemporaryDirectory] = None
        self._downloaded_files: dict[str, Path] = {}

    def connect(self) -> None:
        """Authenticate and connect to Google Drive API."""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError(
                "Google Drive connector requires google-api-python-client.\n"
                "Install with: pip install doc2json[google-drive]"
            )

        # Load credentials
        if self.credentials_file:
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_file,
                scopes=["https://www.googleapis.com/auth/drive.readonly"],
            )
        else:
            # Fall back to default credentials (GOOGLE_APPLICATION_CREDENTIALS)
            from google.auth import default

            credentials, _ = default(
                scopes=["https://www.googleapis.com/auth/drive.readonly"]
            )

        # Build Drive API service
        self._service = build("drive", "v3", credentials=credentials)

        # Create temp directory for downloads
        self._temp_dir = tempfile.TemporaryDirectory(prefix="doc2json_gdrive_")

        # Verify folder access
        try:
            self._service.files().get(fileId=self.folder_id).execute()
        except Exception as e:
            raise ValueError(
                f"Cannot access Google Drive folder '{self.folder_id}': {e}"
            )

        logger.info(f"Connected to Google Drive folder: {self.folder_id}")

    def list_documents(self) -> list[DocumentRef]:
        """List all documents in the Google Drive folder."""
        # For backward compatibility
        return list(self.iter_documents())

    def iter_documents(self):
        """Yield all documents in the Google Drive folder."""
        if not self._service:
            raise RuntimeError("Not connected. Call connect() first.")

        yield from self._iter_folder(self.folder_id)

    def _iter_folder(
        self, folder_id: str, path_prefix: str = ""
    ):
        """Yield documents in a folder, optionally recursing into subfolders."""
        page_token = None

        while True:
            # Query for files in folder
            query = f"'{folder_id}' in parents and trashed = false"
            results = (
                self._service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType, size)",
                    pageToken=page_token,
                    pageSize=100,
                )
                .execute()
            )

            for file in results.get("files", []):
                mime_type = file.get("mimeType", "")
                file_name = file.get("name", "")
                file_id = file["id"]

                # Skip unsupported types
                if mime_type in SKIP_MIME_TYPES:
                    continue

                # Handle folders (recurse if enabled)
                if mime_type == "application/vnd.google-apps.folder":
                    if self.recursive:
                        subfolder_path = (
                            f"{path_prefix}{file_name}/" if path_prefix else f"{file_name}/"
                        )
                        yield from self._iter_folder(file_id, subfolder_path)
                    continue

                # For Google Workspace docs, we'll export them
                if mime_type in GOOGLE_WORKSPACE_EXPORTS:
                    export_config = GOOGLE_WORKSPACE_EXPORTS[mime_type]
                    # Append appropriate extension
                    if not file_name.endswith(export_config["extension"]):
                        file_name = file_name + export_config["extension"]

                # Get file size (not available for Google Workspace docs)
                size_bytes = int(file.get("size", 0)) if file.get("size") else None

                yield DocumentRef(
                    id=file_id,
                    name=file_name,
                    mime_type=mime_type,
                    size_bytes=size_bytes,
                    metadata={
                        "relative_path": f"{path_prefix}{file_name}",
                        "google_drive_id": file_id,
                    },
                )

            # Handle pagination
            page_token = results.get("nextPageToken")
            if not page_token:
                break

    def get_document_path(self, doc_ref: DocumentRef) -> Path:
        """Download document to temp file and return local path."""
        if not self._service:
            raise RuntimeError("Not connected. Call connect() first.")
        if not self._temp_dir:
            raise RuntimeError("Temp directory not initialized.")

        file_id = doc_ref.id

        # Return cached path if already downloaded
        if file_id in self._downloaded_files:
            return self._downloaded_files[file_id]

        # Determine download method
        mime_type = doc_ref.mime_type or ""
        local_path = Path(self._temp_dir.name) / doc_ref.name

        if mime_type in GOOGLE_WORKSPACE_EXPORTS:
            # Export Google Workspace document
            export_config = GOOGLE_WORKSPACE_EXPORTS[mime_type]
            self._export_file(file_id, export_config["mime_type"], local_path)
        else:
            # Direct download for regular files
            self._download_file(file_id, local_path)

        self._downloaded_files[file_id] = local_path
        logger.debug(f"Downloaded {doc_ref.name} to {local_path}")
        return local_path

    def _download_file(self, file_id: str, local_path: Path) -> None:
        """Download a regular file from Google Drive."""
        from googleapiclient.http import MediaIoBaseDownload

        request = self._service.files().get_media(fileId=file_id)
        with open(local_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

    def _export_file(self, file_id: str, export_mime_type: str, local_path: Path) -> None:
        """Export a Google Workspace document to a downloadable format."""
        from googleapiclient.http import MediaIoBaseDownload

        request = self._service.files().export_media(
            fileId=file_id, mimeType=export_mime_type
        )
        with open(local_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

    def close(self) -> None:
        """Clean up temp directory and resources."""
        if self._temp_dir:
            self._temp_dir.cleanup()
            self._temp_dir = None
        self._downloaded_files.clear()
        self._service = None
        logger.debug("Google Drive source closed")

    def __enter__(self) -> "GoogleDriveSource":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
