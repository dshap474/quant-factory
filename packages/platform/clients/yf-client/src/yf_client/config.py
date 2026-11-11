"""Load and validate yf-client settings without filesystem side effects.

USAGE::

    from yf_client.config import settings

    print(settings.default_period)
    print(settings.output_dir)
"""

import os
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# --------------------------------------------------------------------------- #
# Settings model
# --------------------------------------------------------------------------- #


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Pydantic v2 settings configuration
    model_config = SettingsConfigDict(
        env_prefix="YF_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # Default data retrieval settings
    default_period: str = Field(
        default="1mo", description="Default time period for historical data"
    )
    default_interval: str = Field(
        default="1d", description="Default data interval for historical data"
    )

    # Export settings
    export_format: str = Field(default="json", description="Default export format")
    output_dir: Path = Field(
        default=Path("./exports"), description="Default output directory for exports"
    )

    # API settings
    user_agent: str = Field(
        default="yf-client/0.1.0", description="User agent string for requests"
    )
    timeout: int = Field(default=30, description="Request timeout in seconds", gt=0)
    max_retries: int = Field(
        default=3, description="Maximum number of retries for failed requests", ge=0
    )

    # CLI settings
    progress_bar: bool = Field(
        default=True, description="Show progress bar in CLI operations"
    )
    verbose: bool = Field(default=False, description="Enable verbose logging")

    # Cache settings
    cache_enabled: bool = Field(
        default=True, description="Enable caching of API responses"
    )
    cache_dir: Optional[Path] = Field(
        default=None, description="Cache directory (defaults to ~/.cache/yf-client)"
    )
    cache_ttl: int = Field(
        default=3600, description="Cache TTL in seconds (1 hour)", gt=0
    )

    # Validation settings
    validate_symbols: bool = Field(
        default=True, description="Validate symbols before API calls"
    )

    @field_validator("default_period")
    @classmethod
    def validate_default_period(cls, v):
        """Validate default period value."""
        valid_periods = [
            "1d",
            "5d",
            "1mo",
            "3mo",
            "6mo",
            "1y",
            "2y",
            "5y",
            "10y",
            "ytd",
            "max",
        ]
        if v not in valid_periods:
            raise ValueError(
                f"Invalid period '{v}'. Must be one of: {', '.join(valid_periods)}"
            )
        return v

    @field_validator("default_interval")
    @classmethod
    def validate_default_interval(cls, v):
        """Validate default interval value."""
        valid_intervals = [
            "1m",
            "2m",
            "5m",
            "15m",
            "30m",
            "60m",
            "90m",
            "1h",
            "1d",
            "5d",
            "1wk",
            "1mo",
            "3mo",
        ]
        if v not in valid_intervals:
            raise ValueError(
                f"Invalid interval '{v}'. Must be one of: {', '.join(valid_intervals)}"
            )
        return v

    @field_validator("export_format")
    @classmethod
    def validate_export_format(cls, v):
        """Validate export format value."""
        valid_formats = ["json", "csv", "xlsx"]
        if v not in valid_formats:
            raise ValueError(
                f"Invalid export format '{v}'. Must be one of: {', '.join(valid_formats)}"
            )
        return v

    @field_validator("cache_dir", mode="before")
    @classmethod
    def validate_cache_dir(cls, v):
        """Set default cache directory if not provided."""
        if v is None:
            cache_home = os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")
            return Path(cache_home) / "yf-client"
        if isinstance(v, str):
            return Path(v)
        return v

    # Removed legacy Config because Pydantic v2 forbids using both with model_config

    @property
    def valid_periods(self) -> list[str]:
        """Get list of valid periods."""
        return ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]

    @property
    def valid_intervals(self) -> list[str]:
        """Get list of valid intervals."""
        return [
            "1m",
            "2m",
            "5m",
            "15m",
            "30m",
            "60m",
            "90m",
            "1h",
            "1d",
            "5d",
            "1wk",
            "1mo",
            "3mo",
        ]

    @property
    def valid_export_formats(self) -> list[str]:
        """Get list of valid export formats."""
        return ["json", "csv", "xlsx"]


# --------------------------------------------------------------------------- #
# Shared settings
# --------------------------------------------------------------------------- #


settings = Settings()
