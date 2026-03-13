<!--
  The Kai Seeker (解を求める者)
  Copyright (c) 2025 The Kai Project Contributors
  Licensed under AGPL-3.0 — https://github.com/Myyura/the_kai_seeker
  Fingerprint: kai-seeker-v0.1.0-2025
-->

<div align="center">

```
  ╔══════════════════════════════════════════════════════╗
  ║                                                      ║
  ║     T H E   K A I   S E E K E R                      ║
  ║                                                      ║
  ║     Countless questions without, one Kai within.     ║
  ║                                                      ║
  ╚══════════════════════════════════════════════════════╝
```

<!-- Project Icon Placeholder: replace with <img src="docs/assets/logo.png" width="120" /> -->

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-green.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![The Kai Project](https://img.shields.io/badge/Powered%20by-The%20Kai%20Project-2e8555)](https://runjp.com)
[![GitHub](https://img.shields.io/badge/GitHub-the__kai__seeker-181717?logo=github)](https://github.com/Myyura/the_kai_seeker)

</div>

**A local-first, open-source study agent for Japanese graduate entrance exam preparation.**

The word **"Kai" (解)** means "answer/solution" — not in the sense of giving you *the* answer, but being the **one Kai within** as you face countless questions along your journey.

The Kai Seeker is the runtime application of [The Kai Project](https://runjp.com) ecosystem. While The Kai Project provides the knowledge source (past exam questions, answers, experience posts), The Kai Seeker is your local study companion that helps you explore, practice, and grow.

## What It Does

- **School Explorer** — Browse Japanese universities, graduate programs, and exam differences
- **Practice Mode** — Work through past exam questions by school, subject, and year
- **Study Chat** — Chat with an AI study assistant powered by your own LLM API key
- **Review Dashboard** — Track mistakes, identify weak areas, and measure progress
- **Study Planning** — Build personalized study plans based on your targets

## Key Principles

- **Local-first** — Everything runs on your machine. No cloud servers.
- **Open-source** — Fully transparent. Contribute and customize freely.
- **BYOK** — Bring Your Own Key. You provide your own LLM API key.
- **Privacy** — Your data, your keys, your study journey. Nothing leaves your machine unless you choose to call an external LLM API.

## Architecture

```
┌─────────────┐   HTTP   ┌──────────────┐  BYOK  ┌──────────────┐
│   Frontend  │ ──/api─▶ │   Backend    │ ─────▶ │ LLM Provider │
│  (Next.js)  │          │  (FastAPI)   │        │ (your key)   │
│  Static HTML│          │  + SQLite    │        └──────────────┘
└─────────────┘          │  + Content   │
                         └──────────────┘
```

- **Frontend**: Next.js static export served by the backend
- **Backend**: FastAPI on localhost — serves both the API and the frontend
- **Database**: SQLite for local persistence
- **Content**: Prebuilt JSON artifacts from The Kai Project

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+ (for frontend development)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python scripts/run_dev.py
```

Backend starts at http://127.0.0.1:8000 (API docs at `/api/docs`).

### Frontend (Development)

```bash
cd frontend
npm install
npm run dev
```

Frontend dev server starts at http://localhost:3000.

### Production (Single Server)

```bash
cd frontend && npm run build && cd ..
cd backend && python -m app.main
# Visit http://127.0.0.1:8000
```

In production, FastAPI serves both the API (`/api/*`) and the frontend static files (`/`).

## Repository Structure

```
the_kai_seeker/
├── frontend/          Web UI (Next.js, static export)
│   ├── src/app/       Pages: home, chat, schools, practice, review, settings
│   ├── src/components/ Shared components
│   ├── src/features/  Feature-specific code
│   ├── src/lib/       Config, API client
│   └── src/styles/    Global styles
├── backend/           Local server (FastAPI, Python)
│   ├── app/api/       Route handlers
│   ├── app/config/    Settings (pydantic-settings)
│   ├── app/models/    SQLAlchemy models
│   ├── app/schemas/   Pydantic schemas
│   ├── app/services/  Application logic
│   ├── app/providers/ LLM provider adapters
│   ├── app/skills/    Domain workflows
│   ├── app/tools/     Low-level capabilities
│   ├── app/content/   Content artifact loaders
│   └── data/          SQLite DB + content artifacts
└── docs/              Architecture & development docs
```

## Configuration

**Backend** (`backend/.env`): app settings, database path, content directory, CORS origins.

**Frontend** (`frontend/.env.local`): backend API URL.

See [docs/development.md](docs/development.md) for full configuration reference.

## Relationship to The Kai Project

| | The Kai Project | The Kai Seeker |
|---|---|---|
| **Role** | Content source | Runtime application |
| **Contains** | Past exams, answers, experience posts | Study agent, practice UI, chat |
| **Format** | Markdown + Docusaurus site | Next.js frontend + FastAPI backend |
| **URL** | [runjp.com](https://runjp.com) | Runs locally on your machine |

The Kai Seeker consumes prebuilt content artifacts (JSON files) generated from The Kai Project. The two repositories maintain a clear boundary.

## Contributing

Contributions are welcome! Please see [docs/development.md](docs/development.md) for setup instructions.

## License

AGPL-3.0 — Same license as The Kai Project.

If you modify and distribute this software (including providing it as a network service), you **must** make the complete source code available under the same license. See [GNU AGPL-3.0](https://www.gnu.org/licenses/agpl-3.0.html) for details.

---

<div align="center">

**The Kai Seeker** · Part of [The Kai Project](https://runjp.com) ecosystem

Built with purpose. Open by principle.

</div>
