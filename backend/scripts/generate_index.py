#!/usr/bin/env python3
"""Scan The Kai Project repository and generate schools.json + questions.json indexes.

Usage:
    python scripts/generate_index.py /path/to/the_kai_project
    python scripts/generate_index.py /path/to/the_kai_project --output ./data/content

The script walks the docs/ directory of The Kai Project, reads _category_.json
metadata and Markdown frontmatter, and produces two lightweight JSON index files
that The Kai Seeker uses at runtime.
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

GITHUB_REPO = "Myyura/the_kai_project"
GITHUB_BRANCH = "main"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"
GITHUB_BLOB_BASE = f"https://github.com/{GITHUB_REPO}/blob/{GITHUB_BRANCH}"

YEAR_PATTERN = re.compile(r"^\d{4}$")
FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def read_category(path: Path) -> dict | None:
    cat_file = path / "_category_.json"
    if not cat_file.exists():
        return None
    try:
        return json.loads(cat_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read %s: %s", cat_file, e)
        return None


def parse_frontmatter(md_path: Path) -> dict:
    """Extract YAML-like frontmatter from a Markdown file (simple parser, no PyYAML needed)."""
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return {}

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


def extract_title_from_md(md_path: Path) -> str | None:
    """Extract the first H1 heading from a Markdown file."""
    try:
        for line in md_path.open(encoding="utf-8"):
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        pass
    return None


def is_year_dir(d: Path) -> bool:
    return d.is_dir() and YEAR_PATTERN.match(d.name) is not None


def relative_to_docs(path: Path, docs_root: Path) -> str:
    return str(path.relative_to(docs_root)).replace("\\", "/")


def scan_kai_project(docs_root: Path) -> tuple[list[dict], list[dict]]:
    schools: list[dict] = []
    questions: list[dict] = []

    for school_dir in sorted(docs_root.iterdir()):
        if not school_dir.is_dir() or school_dir.name.startswith("."):
            continue

        school_cat = read_category(school_dir)
        school_id = school_dir.name
        school_label = school_cat.get("label", school_id) if school_cat else school_id

        school_entry = {
            "id": school_id,
            "name_ja": school_label,
            "departments": [],
        }

        for dept_dir in sorted(school_dir.iterdir()):
            if not dept_dir.is_dir() or dept_dir.name.startswith("_"):
                continue

            dept_cat = read_category(dept_dir)
            dept_id = dept_dir.name
            dept_label = dept_cat.get("label", dept_id) if dept_cat else dept_id

            dept_entry = {
                "id": dept_id,
                "name_ja": dept_label,
                "programs": [],
            }

            subdirs = sorted([d for d in dept_dir.iterdir() if d.is_dir() and not d.name.startswith("_")])

            if subdirs and all(is_year_dir(d) for d in subdirs):
                # Pattern: school/department/year/*.md (no program level)
                _scan_years(
                    year_dirs=subdirs,
                    school_id=school_id,
                    dept_id=dept_id,
                    program_id=None,
                    docs_root=docs_root,
                    questions=questions,
                )
            else:
                for prog_dir in subdirs:
                    if not prog_dir.is_dir():
                        continue

                    prog_cat = read_category(prog_dir)
                    prog_id = prog_dir.name
                    prog_label = prog_cat.get("label", prog_id) if prog_cat else prog_id

                    dept_entry["programs"].append({
                        "id": prog_id,
                        "name_ja": prog_label,
                    })

                    year_dirs = sorted([d for d in prog_dir.iterdir() if is_year_dir(d)])
                    _scan_years(
                        year_dirs=year_dirs,
                        school_id=school_id,
                        dept_id=dept_id,
                        program_id=prog_id,
                        docs_root=docs_root,
                        questions=questions,
                    )

            school_entry["departments"].append(dept_entry)

        schools.append(school_entry)

    return schools, questions


def _scan_years(
    year_dirs: list[Path],
    school_id: str,
    dept_id: str,
    program_id: str | None,
    docs_root: Path,
    questions: list[dict],
) -> None:
    for year_dir in year_dirs:
        year = int(year_dir.name)

        for md_file in sorted(year_dir.glob("*.md")):
            if md_file.name.startswith("_"):
                continue

            fm = parse_frontmatter(md_file)
            sidebar_label = fm.get("sidebar_label", "")
            tags = fm.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]
            tags = [t for t in tags if t != school_id.replace("-", " ").title().replace(" ", "-")]

            title = extract_title_from_md(md_file) or sidebar_label or md_file.stem

            rel = relative_to_docs(md_file, docs_root)

            qid_parts = [school_id, dept_id]
            if program_id:
                qid_parts.append(program_id)
            qid_parts.extend([str(year), md_file.stem])
            question_id = "/".join(qid_parts)

            questions.append({
                "id": question_id,
                "school_id": school_id,
                "department_id": dept_id,
                "program_id": program_id,
                "year": year,
                "filename": md_file.stem,
                "title": title,
                "sidebar_label": sidebar_label or None,
                "tags": tags,
                "kai_project_path": rel,
                "kai_project_raw_url": f"{GITHUB_RAW_BASE}/docs/{rel}",
                "kai_project_url": f"{GITHUB_BLOB_BASE}/docs/{rel}",
            })


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate index files from The Kai Project")
    parser.add_argument("kai_project_path", help="Path to the_kai_project repository root")
    parser.add_argument("--output", "-o", default="./data/content", help="Output directory for JSON files")
    args = parser.parse_args()

    kai_root = Path(args.kai_project_path).resolve()
    docs_root = kai_root / "docs"
    if not docs_root.exists():
        logger.error("docs/ directory not found at %s", docs_root)
        sys.exit(1)

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Scanning %s ...", docs_root)
    schools, questions = scan_kai_project(docs_root)

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

    logger.info("Generated %s (%d schools)", schools_file, len(schools))
    logger.info("Generated %s (%d questions)", questions_file, len(questions))


if __name__ == "__main__":
    main()
