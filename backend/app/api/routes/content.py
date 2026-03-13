import logging

from fastapi import APIRouter, HTTPException

from app.services.content_index import content_index
from app.services.domain_config import domain_config
from app.services.sync_service import sync_from_github

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/domain")
async def get_domain() -> dict:
    return {
        "profile": domain_config.profile,
        "sources_count": len(domain_config.sources),
    }


@router.get("/sources")
async def list_sources(
    query: str | None = None,
    school_id: str | None = None,
    category: str | None = None,
) -> dict:
    results = domain_config.search_sources(
        query=query, school_id=school_id, category=category,
    )
    return {"sources": results, "count": len(results)}


@router.get("/schools")
async def list_schools() -> dict:
    schools = content_index.search_schools()
    return {"schools": schools, "count": len(schools)}


@router.get("/questions")
async def list_questions(
    school_id: str | None = None,
    department_id: str | None = None,
    program_id: str | None = None,
    year: int | None = None,
    keyword: str | None = None,
    limit: int = 20,
) -> dict:
    results = content_index.search_questions(
        school_id=school_id,
        department_id=department_id,
        program_id=program_id,
        year=year,
        keyword=keyword,
        limit=limit,
    )
    return {"questions": results, "count": len(results)}


@router.get("/stats")
async def content_stats() -> dict:
    return {
        "loaded": content_index.is_loaded,
        "schools_count": len(content_index.schools),
        "questions_count": len(content_index.questions),
        "domain_id": domain_config.profile.get("id", "unknown"),
        "domain_name": domain_config.domain_name,
        "sources_count": len(domain_config.sources),
    }


@router.post("/sync")
async def sync_content() -> dict:
    try:
        result = await sync_from_github()
        return result
    except Exception as e:
        logger.exception("Sync failed")
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")
