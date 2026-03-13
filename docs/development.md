# Development Guide

## Prerequisites

- Python 3.11+
- Node.js 20+ (for frontend development only)
- npm or yarn

## Project Structure

```
the_kai_seeker/
├── README.md
├── .gitignore
├── frontend/              Web frontend (Next.js, static export)
│   ├── package.json
│   ├── next.config.ts     Configured for output: 'export'
│   ├── src/
│   │   ├── app/           App Router pages
│   │   ├── components/    Shared UI components
│   │   ├── features/      Feature-specific components & logic
│   │   ├── lib/           Config, API client, utilities
│   │   └── styles/        Global CSS
│   └── public/            Static assets
├── backend/               Python backend (FastAPI)
│   ├── pyproject.toml
│   ├── .env.example
│   ├── app/
│   │   ├── main.py        Application entrypoint
│   │   ├── api/           Route handlers
│   │   ├── config/        Settings module
│   │   ├── db/            Database engine & models base
│   │   ├── models/        SQLAlchemy ORM models
│   │   ├── schemas/       Pydantic schemas
│   │   ├── services/      Application services
│   │   ├── repositories/  Database access layer
│   │   ├── providers/     LLM provider adapters
│   │   ├── skills/        Domain workflow logic
│   │   ├── tools/         Low-level capabilities
│   │   └── content/       Content artifact loaders
│   ├── scripts/           Dev scripts
│   └── data/              Local data (SQLite, content artifacts)
│       └── content/       Prebuilt JSON artifacts
└── docs/                  Project documentation
```

## Getting Started

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate    # macOS/Linux
# .venv\Scripts\activate     # Windows

# Install dependencies
pip install -e ".[dev]"

# Copy environment config
cp .env.example .env

# Start development server
python scripts/run_dev.py
```

The backend will start at `http://127.0.0.1:8000`.

- API docs: http://127.0.0.1:8000/api/docs
- Health check: http://127.0.0.1:8000/api/health

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The frontend dev server will start at `http://localhost:3000`.

### Building for Production

```bash
# Build frontend static export
cd frontend
npm run build
# Output goes to frontend/out/

# Run backend (serves both API and frontend)
cd ../backend
python -m app.main
# Visit http://127.0.0.1:8000
```

## Configuration

### Backend (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | The Kai Seeker | Application name |
| `HOST` | 127.0.0.1 | Server bind address |
| `PORT` | 8000 | Server port |
| `DEBUG` | false | Enable debug mode |
| `DATABASE_URL` | sqlite+aiosqlite:///./data/kai_seeker.db | SQLite connection |
| `CONTENT_DIR` | ./data/content | Content artifacts directory |
| `ALLOWED_ORIGINS` | http://localhost:3000,http://127.0.0.1:3000 | CORS origins |
| `STATIC_DIR` | ../frontend/out | Frontend build directory |

### Frontend (.env.local)

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_BASE_URL` | http://127.0.0.1:8000/api | Backend API URL |
| `NEXT_PUBLIC_APP_TITLE` | The Kai Seeker | App title |

## Adding Content Artifacts

Content artifacts are generated from The Kai Project (separate repository). Place them in `backend/data/content/`:

```
backend/data/content/
├── schools.json
├── questions.json
├── experiences.json
└── search_index.json
```

The artifact generation pipeline is maintained in The Kai Project repository.

## Code Style

- **Backend**: Ruff for linting and formatting (`ruff check`, `ruff format`)
- **Frontend**: ESLint with Next.js config (`npm run lint`)
- Use type hints in Python, TypeScript in frontend
- Prefer explicit over implicit
