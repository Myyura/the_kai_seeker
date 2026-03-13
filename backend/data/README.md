# Data Directory

This directory holds local runtime data for The Kai Seeker.

## Structure

```
data/
  content/              Content indexes and domain configuration
    domain.json         Domain profile (agent identity, role, knowledge base)
    sources.json        Predefined URLs tied to the domain (school sites, etc.)
    schools.json        School, department, and program metadata
    questions.json      Past exam question index with links to full content
  kai_seeker.db         SQLite database (auto-created on first run)
```

## Content Indexes

The index files ship with the repository (pre-built, ~400 KB total).
Users can sync the latest data from GitHub in two ways:

### Via the UI (recommended)

Go to **Settings → Content Database → Sync from GitHub**.
This fetches the latest data from The Kai Project GitHub repository.

### Via command line (for maintainers)

If you have a local clone of The Kai Project:

```bash
python scripts/generate_index.py /path/to/the_kai_project
```

## Domain Configuration

`domain.json` defines the current learning domain profile. All hardcoded references
to "Japanese graduate exams" have been abstracted into this config. The system prompt,
skills, and tools read from it dynamically.

`sources.json` provides a curated set of URLs (official school sites, admission pages,
scholarship resources) that the `lookup_source` tool can search. This saves LLM tokens
by providing accurate URLs instead of requiring the model to guess or hallucinate them.

To adapt the project to a different domain, replace these two files and the
corresponding builtin skills in `app/skills/builtin/`.

## Notes

- The SQLite database is auto-created by the backend on startup.
- Full question content is fetched on-demand from GitHub via the `fetch_question` tool.
- Future: sqlite-vss may be added for vector search over question embeddings.
