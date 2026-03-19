from app.content_sync.base import ContentSyncSource


class ContentSyncRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, ContentSyncSource] = {}

    def register(self, source: ContentSyncSource) -> None:
        self._sources[source.id] = source

    def get(self, source_id: str) -> ContentSyncSource | None:
        return self._sources.get(source_id)

    def list_all(self) -> list[ContentSyncSource]:
        return list(self._sources.values())

    def get_default(self) -> ContentSyncSource | None:
        for source in self._sources.values():
            if source.is_default:
                return source
        return next(iter(self._sources.values()), None)
