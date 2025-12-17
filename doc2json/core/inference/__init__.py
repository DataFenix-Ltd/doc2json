from typing import Protocol
from doc2json.models.schema import Schema

class InferenceEngine(Protocol):
    def infer(self, file_path: str) -> Schema:
        """
        Analyzes a document and infers its schema.
        
        Args:
            file_path: Absolute path to the source document.
            
        Returns:
            A Schema object representing the inferred structure.
        """
        ...
