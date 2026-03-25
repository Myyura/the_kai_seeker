import json

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.db.engine import async_session
from app.models.conversation import ChatToolArtifact
from app.services.request_context import get_active_artifact_ids
from app.tools.base import BaseTool, ToolResult


class ReadArtifactTool(BaseTool):
    name = "read_artifact"
    description = (
        "Read the full stored body of a previously produced artifact in the current chat session. "
        "Use this only when an existing artifact summary is insufficient and you need the complete content."
    )
    display_name = "Read Artifact"
    activity_label = "Reading stored artifact"

    class Args(BaseModel):
        artifact_id: int = Field(description="Artifact id from a prior tool result summary.")

    async def execute(self, args: Args) -> ToolResult:
        active_ids = set(get_active_artifact_ids())
        if args.artifact_id not in active_ids:
            return ToolResult(
                success=False,
                error=(
                    f"Artifact {args.artifact_id} is not available in the current session context. "
                    f"Allowed artifact ids: {sorted(active_ids)}."
                ),
            )

        async with async_session() as session:
            stmt = select(ChatToolArtifact).where(ChatToolArtifact.id == args.artifact_id)
            artifact = (await session.execute(stmt)).scalar_one_or_none()

        if artifact is None:
            return ToolResult(success=False, error=f"Artifact {args.artifact_id} not found.")

        body_json = None
        if artifact.body_json:
            try:
                body_json = json.loads(artifact.body_json)
            except json.JSONDecodeError:
                body_json = artifact.body_json

        data = {
            "artifact_id": artifact.id,
            "kind": artifact.kind,
            "label": artifact.label,
            "summary": artifact.summary,
            "locator": json.loads(artifact.locator_json) if artifact.locator_json else {},
            "body_text": artifact.body_text,
            "body_json": body_json,
        }
        return ToolResult(success=True, data=data)
