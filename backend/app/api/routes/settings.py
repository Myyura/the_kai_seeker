import logging
from pathlib import Path

from fastapi import APIRouter

from app.skills.registry import skill_registry
from app.tools.registry import tool_registry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def get_settings() -> dict:
    return {"settings": {}, "_todo": "Implement local preferences"}


@router.get("/extensions")
async def list_extensions() -> dict:
    tools = []
    for t in tool_registry.list_all():
        s = t.schema()
        tools.append({
            "name": s["name"],
            "description": s["description"],
            "type": "tool",
            "parameters": s.get("parameters", []),
        })

    skills = []
    for sk in skill_registry.list_all():
        skills.append({
            "name": sk.name,
            "description": sk.description,
            "type": "skill",
            "source": sk.source,
            "trigger": sk.trigger,
            "allowed_tools": sk.allowed_tools,
        })

    return {
        "tools": tools,
        "skills": skills,
        "tools_count": len(tools),
        "skills_count": len(skills),
    }


@router.post("/extensions/reload")
async def reload_extensions() -> dict:
    from app.extensions import reload_all_extensions

    backend_dir = Path(__file__).resolve().parent.parent.parent.parent
    summary = reload_all_extensions(backend_dir)

    logger.info("Extensions reloaded: %s", summary)

    return {
        "status": "ok",
        "message": (
            f"Reloaded: {summary['builtin_skills']} builtin skills, "
            f"{summary['user_tools']} user tools, "
            f"{summary['user_skills']} user skills"
        ),
        **summary,
    }
