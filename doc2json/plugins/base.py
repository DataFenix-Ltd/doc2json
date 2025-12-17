from typing import Dict, Any, List

class DestinationAdapter:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def connect(self): pass
    def write_records(self, schema_name: str, records: List[Dict[str, Any]]): raise NotImplementedError
    def close(self): pass
