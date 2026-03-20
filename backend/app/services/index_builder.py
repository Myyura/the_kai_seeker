"""Shared helpers for building schools/questions indexes."""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

YEAR_PATTERN = re.compile(r"^\d{4}$")
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def parse_frontmatter_text(text: str) -> dict:
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}

    frontmatter: dict = {"sidebar_label": None, "tags": []}
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
                frontmatter[key] = value
            else:
                frontmatter.setdefault(key, [])
        elif stripped.startswith("-") and current_key:
            item = stripped.lstrip("-").strip().strip("'\"")
            if isinstance(frontmatter.get(current_key), list):
                frontmatter[current_key].append(item)
            else:
                frontmatter[current_key] = [item]

    return frontmatter


def extract_title(text: str) -> str | None:
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return None


def collect_local_docs_data(docs_root: Path) -> tuple[list[str], dict[str, dict], dict[str, str]]:
    docs_paths: list[str] = []
    categories: dict[str, dict] = {}
    md_texts: dict[str, str] = {}

    for path in sorted(docs_root.rglob("*")):
        if not path.is_file():
            continue
        relative = f"docs/{path.relative_to(docs_root).as_posix()}"
        docs_paths.append(relative)

        if path.name == "_category_.json":
            try:
                categories[relative] = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read %s: %s", path, exc)
            continue

        if path.suffix == ".md":
            try:
                md_texts[relative] = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Failed to read %s: %s", path, exc)

    return docs_paths, categories, md_texts


def build_index(
    docs_paths: list[str],
    categories: dict[str, dict],
    md_texts: dict[str, str],
    *,
    github_raw_base: str,
    github_blob_base: str,
) -> tuple[list[dict], list[dict]]:
    dir_set: set[str] = set()
    md_by_dir: dict[str, list[str]] = {}
    for path in docs_paths:
        parts = path.split("/")
        for depth in range(2, len(parts)):
            dir_set.add("/".join(parts[:depth]))
        if path.endswith(".md") and not parts[-1].startswith("_"):
            parent = "/".join(parts[:-1])
            md_by_dir.setdefault(parent, []).append(path)

    def get_label(dir_path: str) -> str:
        category_path = f"{dir_path}/_category_.json"
        category = categories.get(category_path)
        if category and "label" in category:
            return category["label"]
        return dir_path.rsplit("/", 1)[-1]

    school_dirs = sorted({path.split("/")[1] for path in dir_set if path.count("/") == 1})

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

        department_ids = sorted(
            {
                path.split("/")[2]
                for path in dir_set
                if path.startswith(f"docs/{school_id}/") and path.count("/") == 2
            }
        )

        for department_id in department_ids:
            if department_id.startswith("_"):
                continue
            department_path = f"docs/{school_id}/{department_id}"
            department_label = get_label(department_path)
            department_entry = {
                "id": department_id,
                "name_ja": department_label,
                "programs": [],
            }

            sub_ids = sorted(
                {
                    path.split("/")[3]
                    for path in dir_set
                    if path.startswith(f"{department_path}/") and path.count("/") == 3
                }
            )

            if sub_ids and all(_is_year_id(value) for value in sub_ids):
                _append_questions_for_years(
                    year_ids=sub_ids,
                    school_id=school_id,
                    department_id=department_id,
                    program_id=None,
                    parent_path=department_path,
                    md_by_dir=md_by_dir,
                    md_texts=md_texts,
                    questions=questions,
                    github_raw_base=github_raw_base,
                    github_blob_base=github_blob_base,
                )
            else:
                for program_id in sub_ids:
                    if program_id.startswith("_"):
                        continue
                    program_path = f"{department_path}/{program_id}"
                    program_label = get_label(program_path)
                    department_entry["programs"].append(
                        {
                            "id": program_id,
                            "name_ja": program_label,
                        }
                    )

                    year_ids = sorted(
                        {
                            path.split("/")[4]
                            for path in dir_set
                            if path.startswith(f"{program_path}/")
                            and path.count("/") == 4
                            and _is_year_id(path.split("/")[4])
                        }
                    )
                    _append_questions_for_years(
                        year_ids=year_ids,
                        school_id=school_id,
                        department_id=department_id,
                        program_id=program_id,
                        parent_path=program_path,
                        md_by_dir=md_by_dir,
                        md_texts=md_texts,
                        questions=questions,
                        github_raw_base=github_raw_base,
                        github_blob_base=github_blob_base,
                    )

            school_entry["departments"].append(department_entry)

        schools.append(school_entry)

    return schools, questions


def _append_questions_for_years(
    *,
    year_ids: list[str],
    school_id: str,
    department_id: str,
    program_id: str | None,
    parent_path: str,
    md_by_dir: dict[str, list[str]],
    md_texts: dict[str, str],
    questions: list[dict],
    github_raw_base: str,
    github_blob_base: str,
) -> None:
    for year_str in year_ids:
        year = int(year_str)
        year_path = f"{parent_path}/{year_str}"

        for md_path in sorted(md_by_dir.get(year_path, [])):
            filename = md_path.rsplit("/", 1)[-1]
            stem = filename.removesuffix(".md")
            relative = md_path.removeprefix("docs/")

            frontmatter = {}
            title = stem
            md_text = md_texts.get(md_path)
            if md_text:
                frontmatter = parse_frontmatter_text(md_text)
                extracted_title = extract_title(md_text)
                if extracted_title:
                    title = extracted_title
                elif frontmatter.get("sidebar_label"):
                    title = frontmatter["sidebar_label"]

            sidebar_label = frontmatter.get("sidebar_label")
            tags = frontmatter.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]
            tags = _normalize_tags(tags, school_id)

            question_id_parts = [school_id, department_id]
            if program_id:
                question_id_parts.append(program_id)
            question_id_parts.extend([year_str, stem])

            questions.append(
                {
                    "id": "/".join(question_id_parts),
                    "school_id": school_id,
                    "department_id": department_id,
                    "program_id": program_id,
                    "year": year,
                    "filename": stem,
                    "title": title,
                    "sidebar_label": sidebar_label,
                    "tags": tags,
                    "kai_project_path": relative,
                    "kai_project_raw_url": f"{github_raw_base}/docs/{relative}",
                    "kai_project_url": f"{github_blob_base}/docs/{relative}",
                }
            )


def _is_year_id(value: str) -> bool:
    return YEAR_PATTERN.match(value) is not None


def _normalize_tags(tags: list[str], school_id: str) -> list[str]:
    school_tag = school_id.replace("-", " ").title().replace(" ", "-")
    return [tag for tag in tags if tag != school_tag]
