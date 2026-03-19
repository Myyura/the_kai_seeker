from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContentSyncSource:
    """Definition for a content sync source."""

    id: str
    name: str
    kind: str
    description: str
    enabled: bool = True
    is_default: bool = False
    config_fields: list[dict[str, Any]] = field(default_factory=list)

    def schema(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "description": self.description,
            "enabled": self.enabled,
            "is_default": self.is_default,
            "config_fields": self.config_fields,
        }

    async def sync(self, options: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError
