import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class Field:
    name: str
    type: str  # e.g., "string", "integer", "boolean", "array", "object"
    description: Optional[str] = None
    required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "required": self.required
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Field':
        return cls(
            name=data["name"],
            type=data["type"],
            description=data.get("description"),
            required=data.get("required", False)
        )

@dataclass
class Schema:
    name: str
    fields: List[Field] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "fields": [f.to_dict() for f in self.fields],
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Schema':
        return cls(
            name=data["name"],
            fields=[Field.from_dict(f) for f in data.get("fields", [])],
            metadata=data.get("metadata", {})
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> 'Schema':
        return cls.from_dict(json.loads(json_str))
