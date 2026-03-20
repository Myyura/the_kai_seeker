#!/usr/bin/env python3
"""Generate schools.json + questions.json indexes from a local Kai Project checkout."""

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


GITHUB_REPO = "Myyura/the_kai_project"
GITHUB_BRANCH = "main"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"
GITHUB_BLOB_BASE = f"https://github.com/{GITHUB_REPO}/blob/{GITHUB_BRANCH}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate index files from The Kai Project")
    parser.add_argument("kai_project_path", help="Path to the_kai_project repository root")
    parser.add_argument(
        "--output",
        "-o",
        default="./data/content",
        help="Output directory for JSON files",
    )
    args = parser.parse_args()

    kai_root = Path(args.kai_project_path).resolve()
    docs_root = kai_root / "docs"
    if not docs_root.exists():
        logger.error("docs/ directory not found at %s", docs_root)
        sys.exit(1)

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Scanning %s ...", docs_root)
    from app.services.index_builder import build_index, collect_local_docs_data

    docs_paths, categories, md_texts = collect_local_docs_data(docs_root)
    schools, questions = build_index(
        docs_paths,
        categories,
        md_texts,
        github_raw_base=GITHUB_RAW_BASE,
        github_blob_base=GITHUB_BLOB_BASE,
    )

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
