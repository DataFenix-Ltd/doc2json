import os


class TextParser:
    """Parser for plain text files."""

    SUPPORTED_EXTENSIONS = {".txt", ".text", ".md", ".markdown"}

    def can_parse(self, file_path: str) -> bool:
        """Check if this is a plain text file."""
        _, ext = os.path.splitext(file_path)
        return ext.lower() in self.SUPPORTED_EXTENSIONS

    def parse(self, file_path: str) -> str:
        """Read and return the text content."""
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
