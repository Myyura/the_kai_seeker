import json

from app.services.index_builder import build_index, collect_local_docs_data


def test_collect_local_docs_data_and_build_index(tmp_path) -> None:
    docs_root = tmp_path / "docs"
    year_dir = docs_root / "tokyo-university" / "IST" / "ci" / "2025"
    year_dir.mkdir(parents=True)

    (docs_root / "tokyo-university" / "_category_.json").write_text(
        json.dumps({"label": "東京大学"}),
        encoding="utf-8",
    )
    (docs_root / "tokyo-university" / "IST" / "_category_.json").write_text(
        json.dumps({"label": "情報理工"}),
        encoding="utf-8",
    )
    (docs_root / "tokyo-university" / "IST" / "ci" / "_category_.json").write_text(
        json.dumps({"label": "知能情報"}),
        encoding="utf-8",
    )
    (year_dir / "sample.md").write_text(
        "---\n"
        "sidebar_label: Sample Sidebar\n"
        "tags:\n"
        "  - Linear-Algebra\n"
        "---\n\n"
        "# Sample Question\n\n"
        "body",
        encoding="utf-8",
    )

    docs_paths, categories, md_texts = collect_local_docs_data(docs_root)
    schools, questions = build_index(
        docs_paths,
        categories,
        md_texts,
        github_raw_base="https://raw.example.com/repo/main",
        github_blob_base="https://github.example.com/repo/blob/main",
    )

    assert schools == [
        {
            "id": "tokyo-university",
            "name_ja": "東京大学",
            "departments": [
                {
                    "id": "IST",
                    "name_ja": "情報理工",
                    "programs": [{"id": "ci", "name_ja": "知能情報"}],
                }
            ],
        }
    ]
    assert questions == [
        {
            "id": "tokyo-university/IST/ci/2025/sample",
            "school_id": "tokyo-university",
            "department_id": "IST",
            "program_id": "ci",
            "year": 2025,
            "filename": "sample",
            "title": "Sample Question",
            "sidebar_label": "Sample Sidebar",
            "tags": ["Linear-Algebra"],
            "kai_project_path": "tokyo-university/IST/ci/2025/sample.md",
            "kai_project_raw_url": "https://raw.example.com/repo/main/docs/tokyo-university/IST/ci/2025/sample.md",
            "kai_project_url": "https://github.example.com/repo/blob/main/docs/tokyo-university/IST/ci/2025/sample.md",
        }
    ]
