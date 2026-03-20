from app.services.content_index import ContentIndex


def test_search_questions_program_filter_excludes_department_level_questions() -> None:
    index = ContentIndex()
    index.questions = [
        {
            "id": "dept-only",
            "school_id": "tokyo-university",
            "department_id": "IST",
            "program_id": None,
            "year": 2025,
            "title": "Department-level question",
            "filename": "dept-only",
            "tags": [],
        },
        {
            "id": "program-specific",
            "school_id": "tokyo-university",
            "department_id": "IST",
            "program_id": "ci",
            "year": 2025,
            "title": "Program-specific question",
            "filename": "program-specific",
            "tags": [],
        },
    ]
    index._loaded = True

    results = index.search_questions(
        school_id="tokyo-university",
        department_id="IST",
        program_id="ci",
    )

    assert [question["id"] for question in results] == ["program-specific"]
