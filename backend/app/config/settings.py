"""Application settings for The Kai Seeker (解を求める者).

This file is part of The Kai Seeker, licensed under AGPL-3.0.
Source: https://github.com/Myyura/the_kai_seeker
"""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "The Kai Seeker"
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False

    database_url: str = "sqlite+aiosqlite:///./data/kai_seeker.db"

    content_dir: str = "./data/content"

    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    static_dir: str = "../frontend/out"

    llm_provider: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def content_path(self) -> Path:
        return Path(self.content_dir).resolve()

    @property
    def static_path(self) -> Path:
        return Path(self.static_dir).resolve()


settings = Settings()
