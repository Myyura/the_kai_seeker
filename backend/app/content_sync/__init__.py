from app.content_sync.registry import ContentSyncRegistry
from app.content_sync.sources.kai_project import KaiProjectSyncSource

content_sync_registry = ContentSyncRegistry()
content_sync_registry.register(KaiProjectSyncSource())
