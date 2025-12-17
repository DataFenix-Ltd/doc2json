"""Local file system source connector."""

import mimetypes
from pathlib import Path
from typing import Any

from doc2json.connectors import DocumentRef

# Files to skip (not actual documents)
SKIP_FILES = {".gitkeep", ".gitignore", ".DS_Store"}


class LocalSource:
    """Source connector for local file system."""

    def __init__(self, config: dict[str, Any]):
        """Initialize local source.

        Config:
            path: Directory path to read from (required)
        """
        self.path = Path(config.get("path", ""))
        if not self.path:
            raise ValueError("LocalSource requires 'path' in config")

    def connect(self) -> None:
        """Verify the source directory exists."""
        if not self.path.exists():
            raise FileNotFoundError(
                f"Source directory not found: {self.path}\n"
                f"Create the directory and add documents to extract."
            )
        if not self.path.is_dir():
            raise ValueError(f"Source path is not a directory: {self.path}")

    def list_documents(self) -> list[DocumentRef]:
        """List all documents in the source directory recursively."""
        return list(self.iter_documents())

    def iter_documents(self):
        """Yield all documents in the source directory recursively."""
        if not self.path:
            return

        yield from self._iter_directory(self.path)

    def _iter_directory(self, directory: Path):
        """Recursively yield documents from a directory."""
        for item in directory.iterdir():
            if item.is_file() and item.name not in SKIP_FILES:
                mime_type, _ = mimetypes.guess_type(str(item))
                yield DocumentRef(
                    id=str(item),  # Full path as ID
                    name=item.name,
                    mime_type=mime_type,
                    size_bytes=item.stat().st_size,
                    metadata={"relative_path": str(item.relative_to(self.path))},
                )
            elif item.is_dir():
                yield from self._iter_directory(item)

    def get_document_path(self, doc_ref: DocumentRef) -> Path:
        """Return the local path (already local, no download needed)."""
        return Path(doc_ref.id)

    def close(self) -> None:
        """No cleanup needed for local files."""
        pass

    def __enter__(self) -> "LocalSource":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
