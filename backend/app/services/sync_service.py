"""Sync content indexes from The Kai Project GitHub repository.

Uses the GitHub Git Trees API to fetch the full repo structure in a single call,
then fetches _category_.json files for Japanese labels and Markdown files for
frontmatter (tags, sidebar_label, title).
"""

import asyncio
import json
import logging

import httpx

from app.config.settings import settings
from app.services.content_index import content_index
from app.services.index_builder import build_index

logger = logging.getLogger(__name__)

GITHUB_REPO = "Myyura/the_kai_project"
GITHUB_BRANCH = "main"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"
GITHUB_BLOB_BASE = f"https://github.com/{GITHUB_REPO}/blob/{GITHUB_BRANCH}"
GITHUB_API_BASE = "https://api.github.com"

MAX_CONCURRENT_FETCHES = 20


async def _fetch_raw(client: httpx.AsyncClient, path: str) -> str | None:
    url = f"{GITHUB_RAW_BASE}/{path}"
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", url, e)
        return None


async def _fetch_batch(
    client: httpx.AsyncClient,
    paths: list[str],
    semaphore: asyncio.Semaphore,
) -> dict[str, str]:
    results: dict[str, str] = {}

    async def _fetch_one(path: str) -> None:
        async with semaphore:
            text = await _fetch_raw(client, path)
            if text is not None:
                results[path] = text

    await asyncio.gather(*[_fetch_one(p) for p in paths])
    return results


async def sync_from_github() -> dict:
    """Fetch the latest index from The Kai Project GitHub repository.

    Returns a summary dict with counts and status.
    """
    logger.info("Starting sync from GitHub: %s", GITHUB_REPO)

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        tree_url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/git/trees/{GITHUB_BRANCH}?recursive=1"
        resp = await client.get(tree_url, headers={"Accept": "application/vnd.github.v3+json"})
        resp.raise_for_status()
        tree_data = resp.json()

    all_paths = [item["path"] for item in tree_data.get("tree", []) if item["type"] == "blob"]

    docs_paths = [p for p in all_paths if p.startswith("docs/")]

    category_paths = [p for p in docs_paths if p.endswith("/_category_.json")]
    md_paths = [p for p in docs_paths if p.endswith(".md") and "/_" not in p.split("/")[-1]]

    logger.info("Found %d category files, %d markdown files", len(category_paths), len(md_paths))

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        category_texts = await _fetch_batch(client, category_paths, semaphore)

    categories: dict[str, dict] = {}
    for path, text in category_texts.items():
        try:
            categories[path] = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in %s", path)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        md_texts = await _fetch_batch(client, md_paths, semaphore)

    schools, questions = build_index(
        docs_paths,
        categories,
        md_texts,
        github_raw_base=GITHUB_RAW_BASE,
        github_blob_base=GITHUB_BLOB_BASE,
    )

    output_dir = settings.content_path
    output_dir.mkdir(parents=True, exist_ok=True)

    schools_file = output_dir / "schools.json"
    questions_file = output_dir / "questions.json"

    schools_file.write_text(
        json.dumps(schools, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    questions_file.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    content_index.load()

    result = {
        "status": "ok",
        "schools_count": len(schools),
        "questions_count": len(questions),
        "message": f"Synced {len(schools)} schools, {len(questions)} questions from GitHub.",
    }
    logger.info("Sync complete: %s", result["message"])
    return result
