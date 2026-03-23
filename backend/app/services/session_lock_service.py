import asyncio
from contextlib import asynccontextmanager


class SessionLockService:
    """In-process lock manager for chat sessions."""

    def __init__(self) -> None:
        self._locks: dict[int, asyncio.Lock] = {}

    @asynccontextmanager
    async def lock(self, session_id: int):
        guard = self._locks.setdefault(session_id, asyncio.Lock())
        async with guard:
            yield


session_lock_service = SessionLockService()
