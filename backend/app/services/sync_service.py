"""Sync content indexes from The Kai Project GitHub repository.

Uses the GitHub Git Trees API to fetch the full repo structure in a single call,
then fetches _category_.json files for Japanese labels and Markdown files for
frontmatter (tags, sidebar_label, title).
"""

import asyncio
import json
import logging
import re
from pathlib import Path

import httpx

from app.config.settings import settings
from app.services.content_index import content_index

logger = logging.getLogger(__name__)

GITHUB_REPO = "Myyura/the_kai_project"
GITHUB_BRANCH = "main"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"
GITHUB_BLOB_BASE = f"https://github.com/{GITHUB_REPO}/blob/{GITHUB_BRANCH}"
GITHUB_API_BASE = "https://api.github.com"

YEAR_PATTERN = re.compile(r"^\d{4}$")
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)

MAX_CONCURRENT_FETCHES = 20


def _parse_frontmatter_text(text: str) -> dict:
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}

    fm: dict = {"sidebar_label": None, "tags": []}
    raw = match.group(1)
    current_key = None

    for line in raw.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped and not stripped.startswith("-"):
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip("'\"")
            current_key = key
            if value:
                fm[key] = value
            else:
                fm.setdefault(key, [])
        elif stripped.startswith("-") and current_key:
            item = stripped.lstrip("-").strip().strip("'\"")
            if isinstance(fm.get(current_key), list):
                fm[current_key].append(item)
            else:
                fm[current_key] = [item]
    return fm


def _extract_title(text: str) -> str | None:
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return None


async def _fetch_raw(client: httpx.AsyncClient, path: str) -> str | None:
    url = f"{GITHUB_RAW_BASE}/{path}"
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", url, e)
        return None


async def _fetch_batch(client: httpx.AsyncClient, paths: list[str], semaphore: asyncio.Semaphore) -> dict[str, str]:
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

    schools, questions = _build_index(docs_paths, categories, md_texts)

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


def _build_index(
    docs_paths: list[str],
    categories: dict[str, dict],
    md_texts: dict[str, str],
) -> tuple[list[dict], list[dict]]:

    dir_set: set[str] = set()
    md_by_dir: dict[str, list[str]] = {}
    for p in docs_paths:
        parts = p.split("/")
        for i in range(2, len(parts)):
            dir_set.add("/".join(parts[:i]))
        if p.endswith(".md") and not parts[-1].startswith("_"):
            parent = "/".join(parts[:-1])
            md_by_dir.setdefault(parent, []).append(p)

    def get_label(dir_path: str) -> str:
        cat_path = f"{dir_path}/_category_.json"
        cat = categories.get(cat_path)
        if cat and "label" in cat:
            return cat["label"]
        return dir_path.rsplit("/", 1)[-1]

    def is_year(name: str) -> bool:
        return YEAR_PATTERN.match(name) is not None

    school_dirs = sorted({
        p.split("/")[1]
        for p in dir_set
        if p.count("/") == 1
    })

    schools: list[dict] = []
    questions: list[dict] = []

    for school_id in school_dirs:
        school_path = f"docs/{school_id}"
        school_label = get_label(school_path)

        school_entry = {
            "id": school_id,
            "name_ja": school_label,
            "departments": [],
        }

        dept_ids = sorted({
            p.split("/")[2]
            for p in dir_set
            if p.startswith(f"docs/{school_id}/") and p.count("/") == 2
        })

        for dept_id in dept_ids:
            if dept_id.startswith("_"):
                continue
            dept_path = f"docs/{school_id}/{dept_id}"
            dept_label = get_label(dept_path)

            dept_entry = {
                "id": dept_id,
                "name_ja": dept_label,
                "programs": [],
            }

            sub_ids = sorted({
                p.split("/")[3]
                for p in dir_set
                if p.startswith(f"{dept_path}/") and p.count("/") == 3
            })

            if sub_ids and all(is_year(s) for s in sub_ids):
                _process_years(
                    sub_ids, school_id, dept_id, None,
                    dept_path, md_by_dir, md_texts, questions,
                )
            else:
                for prog_id in sub_ids:
                    if prog_id.startswith("_"):
                        continue
                    prog_path = f"{dept_path}/{prog_id}"
                    prog_label = get_label(prog_path)

                    dept_entry["programs"].append({
                        "id": prog_id,
                        "name_ja": prog_label,
                    })

                    year_ids = sorted({
                        p.split("/")[4]
                        for p in dir_set
                        if p.startswith(f"{prog_path}/") and p.count("/") == 4
                        and is_year(p.split("/")[4])
                    })

                    _process_years(
                        year_ids, school_id, dept_id, prog_id,
                        prog_path, md_by_dir, md_texts, questions,
                    )

            school_entry["departments"].append(dept_entry)

        schools.append(school_entry)

    return schools, questions


def _process_years(
    year_ids: list[str],
    school_id: str,
    dept_id: str,
    program_id: str | None,
    parent_path: str,
    md_by_dir: dict[str, list[str]],
    md_texts: dict[str, str],
    questions: list[dict],
) -> None:
    for year_str in year_ids:
        year = int(year_str)
        year_path = f"{parent_path}/{year_str}"

        for md_path in sorted(md_by_dir.get(year_path, [])):
            filename = md_path.rsplit("/", 1)[-1]
            stem = filename.removesuffix(".md")

            rel = md_path.removeprefix("docs/")

            fm = {}
            title = stem
            md_text = md_texts.get(md_path)
            if md_text:
                fm = _parse_frontmatter_text(md_text)
                extracted_title = _extract_title(md_text)
                if extracted_title:
                    title = extracted_title
                elif fm.get("sidebar_label"):
                    title = fm["sidebar_label"]

            sidebar_label = fm.get("sidebar_label")
            tags = fm.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]
            tags = [t for t in tags if t != school_id.replace("-", " ").title().replace(" ", "-")]

            qid_parts = [school_id, dept_id]
            if program_id:
                qid_parts.append(program_id)
            qid_parts.extend([year_str, stem])
            question_id = "/".join(qid_parts)

            questions.append({
                "id": question_id,
                "school_id": school_id,
                "department_id": dept_id,
                "program_id": program_id,
                "year": year,
                "filename": stem,
                "title": title,
                "sidebar_label": sidebar_label,
                "tags": tags,
                "kai_project_path": rel,
                "kai_project_raw_url": f"{GITHUB_RAW_BASE}/docs/{rel}",
                "kai_project_url": f"{GITHUB_BLOB_BASE}/docs/{rel}",
            })
