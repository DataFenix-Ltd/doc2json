import os
import logging

logger = logging.getLogger(__name__)

def ensure_directory(path: str) -> bool:
    """Creates a directory if it doesn't exist."""
    if not os.path.exists(path):
        os.makedirs(path)
        logger.info(f"Created directory: {path}")
        return True
    return False

def create_file_if_missing(path: str, content: str) -> bool:
    """Creates a file with content if it doesn't already exist."""
    if not os.path.exists(path):
        with open(path, 'w') as f:
            f.write(content)
        logger.info(f"Created file: {path}")
        return True
    return False
