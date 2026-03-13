#!/usr/bin/env python3
"""Start the development server with auto-reload."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn

from app.config.settings import settings


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
