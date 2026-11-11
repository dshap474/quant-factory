"""Configuration for the read-only DB API."""

from pathlib import Path

from config import QUANT_DB_ROOT, ROOT_QUANT_FACTORY
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """DB API settings with environment variable support."""

    port: int = 8014
    host: str = "127.0.0.1"
    debug: bool = False
    db_root: Path = QUANT_DB_ROOT
    # Repository checkout holding packages/; independent of where the lake lives.
    repo_root: Path = ROOT_QUANT_FACTORY
    cors_origins: list[str] = [
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]

    model_config = {"env_prefix": "DB_API_"}


settings = Settings()
