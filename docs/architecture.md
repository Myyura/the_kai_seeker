# Architecture

## Overview

The Kai Seeker is a **local-first, open-source study agent** for Japanese graduate entrance exam preparation. It runs entirely on the user's machine with no centralized backend or cloud dependency.

## System Diagram

```
┌──────────────────────────────────────────────┐
│                User's Machine                │
│                                              │
│  ┌──────────────┐      ┌──────────────────┐  │
│  │   Frontend    │ HTTP │     Backend      │  │
│  │  (Next.js)   │─────▶│    (FastAPI)     │  │
│  │  Static HTML  │ /api │                  │  │
│  └──────────────┘      │  ┌────────────┐  │  │
│                        │  │  SQLite DB  │  │  │
│                        │  └────────────┘  │  │
│                        │  ┌────────────┐  │  │
│                        │  │  Content    │  │  │
│                        │  │  Artifacts  │  │  │
│                        │  └────────────┘  │  │
│                        └────────┬─────────┘  │
│                                 │ BYOK       │
│                                 ▼            │
│                        ┌──────────────────┐  │
│                        │  LLM Provider    │  │
│                        │  (user's key)    │  │
│                        └──────────────────┘  │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│          The Kai Project (separate repo)     │
│  Past exams, answers, experience posts       │
│  → Prebuilt into JSON artifacts              │
└──────────────────────────────────────────────┘
```

## Key Principles

- **Local-first**: Everything runs on localhost. No remote servers.
- **BYOK (Bring Your Own Key)**: Users provide their own LLM API keys.
- **Content decoupled**: The Kai Project is the knowledge source; The Kai Seeker consumes prebuilt artifacts.
- **Simple and modular**: Prefer clarity over abstraction.

## Frontend

- **Framework**: Next.js with static HTML export (`output: 'export'`)
- **Output**: `frontend/out/` — pure static HTML/CSS/JS
- **Styling**: CSS Modules aligned with The Kai Project's "Liquid Glass" design system
- **API calls**: All data fetched from the local backend at `/api/*`
- **No SSR**: Static export means no server-side rendering; all dynamic data comes from API calls

## Backend

- **Framework**: FastAPI (Python)
- **Database**: SQLite via SQLAlchemy (async with aiosqlite)
- **Serves frontend**: In production, FastAPI mounts the static export at `/`
- **Serves API**: All endpoints under `/api/*`

### Backend Layers

| Layer | Directory | Responsibility |
|-------|-----------|----------------|
| API | `app/api/` | FastAPI route handlers |
| Schemas | `app/schemas/` | Pydantic request/response models |
| Services | `app/services/` | Application & domain logic |
| Repositories | `app/repositories/` | Database access |
| Providers | `app/providers/` | LLM provider adapters |
| Skills | `app/skills/` | High-level domain workflows |
| Tools | `app/tools/` | Low-level callable capabilities |
| Content | `app/content/` | Content artifact loaders & queries |
| DB | `app/db/` | Database engine & session management |
| Config | `app/config/` | Settings via pydantic-settings |

### Skills vs Tools

- **Skills** are workflow-level: "run a practice session", "generate a study plan", "find schools matching criteria"
- **Tools** are function-level: "search content", "call LLM", "filter questions"
- Skills compose tools. Tools don't know about skills.

## Content Artifacts

Prebuilt JSON files generated from The Kai Project:

| File | Description |
|------|-------------|
| `schools.json` | School & program metadata |
| `questions.json` | Past exam questions with answers |
| `experiences.json` | Experience posts |
| `search_index.json` | Prebuilt full-text search index |
| `school_profiles.json` | Detailed school profiles (future) |
| `question_similarity_map.json` | Question similarity data (future) |

## Local Persistence

SQLite stores user-specific data:

- LLM provider settings (encrypted API keys)
- Study targets (school + program selections)
- Study plans
- Practice sessions & answers
- Mistakes / wrong questions
- Conversation history
- User preferences

## Future: Vector DB

ChromaDB (or similar) for local RAG embeddings:
- Stored in `backend/data/chroma/`
- Used for semantic search over content artifacts
- Enables context-aware chat responses
