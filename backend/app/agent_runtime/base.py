from typing import Awaitable, Callable, Protocol

from app.agent_runtime.types import (
    AgentRuntimeHealth,
    AgentRuntimeLink,
    AgentRuntimeSetup,
    AgentRuntimeSnapshot,
    AgentTurnInput,
    AgentTurnOutput,
    HostContextState,
    HostContextSyncResult,
)

AgentEventCallback = Callable[[dict], Awaitable[None]]


class AgentRuntime(Protocol):
    name: str

    async def open_session(
        self,
        link: AgentRuntimeLink | None,
        setup: AgentRuntimeSetup,
    ) -> AgentRuntimeLink:
        ...

    async def sync_host_context(
        self,
        link: AgentRuntimeLink,
        state: HostContextState,
    ) -> HostContextSyncResult:
        ...

    async def run_turn(
        self,
        link: AgentRuntimeLink,
        turn_input: AgentTurnInput,
        emit: AgentEventCallback | None = None,
    ) -> AgentTurnOutput:
        ...

    async def get_snapshot(self, link: AgentRuntimeLink) -> AgentRuntimeSnapshot | None:
        ...

    async def close_session(self, link: AgentRuntimeLink) -> None:
        ...

    async def healthcheck(self) -> AgentRuntimeHealth:
        ...
