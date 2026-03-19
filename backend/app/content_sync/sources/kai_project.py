from typing import Any

from app.content_sync.base import ContentSyncSource
from app.services.sync_service import sync_from_github


class KaiProjectSyncSource(ContentSyncSource):
    def __init__(self) -> None:
        super().__init__(
            id="kai-project",
            name="Kai Project",
            kind="github",
            description=(
                "Sync the local exam content index from the default The Kai Project "
                "GitHub repository."
            ),
            enabled=True,
            is_default=True,
            config_fields=[],
        )

    async def sync(self, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return await sync_from_github()
