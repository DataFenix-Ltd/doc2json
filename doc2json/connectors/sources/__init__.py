"""Source connectors for reading documents."""

from doc2json.connectors.sources.local import LocalSource
from doc2json.connectors import register_source

# Register built-in sources
register_source("local", LocalSource)

# Register optional connectors (only if dependencies are available)
try:
    from doc2json.connectors.sources.google_drive import GoogleDriveSource
    register_source("google_drive", GoogleDriveSource)
except ImportError:
    pass  # google-api-python-client not installed
