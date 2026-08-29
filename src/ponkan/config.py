from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PONKAN_", env_file=".env", extra="ignore")

    app_name: str = "Ponkan"
    environment: str = "production"
    database_url: str = "postgresql+psycopg://ponkan:ponkan@db:5432/ponkan"
    api_token: str = ""
    cors_origins: Annotated[list[str], NoDecode] = []
    mcp_allowed_hosts: Annotated[list[str], NoDecode] = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
    mcp_allowed_origins: Annotated[list[str], NoDecode] = []
    import_allowed_hosts: Annotated[list[str], NoDecode] = ["docs.google.com", "googleusercontent.com"]
    max_import_bytes: int = 10 * 1024 * 1024
    seed_demo: bool = True

    @field_validator(
        "cors_origins", "mcp_allowed_hosts", "mcp_allowed_origins", "import_allowed_hosts", mode="before"
    )
    @classmethod
    def split_csv(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
