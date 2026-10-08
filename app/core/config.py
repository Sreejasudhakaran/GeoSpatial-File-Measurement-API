"""
Application settings.

WHY a separate config module:
Settings (DB path, upload limits) change between environments (dev, test, prod).
Centralising them here means the rest of the code never hard-codes values —
it just imports `settings` and reads an attribute.  This also makes it trivial
to override values via environment variables for testing or deployment.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All app-wide configuration lives here.

    Values can be overridden by setting env vars with the same name,
    e.g. DATABASE_URL=sqlite:///./test.db  overrides the default below.
    """

    # --- Database ---
    DATABASE_URL: str = "sqlite:///./geo.db"

    # --- File storage ---
    # Directory where uploaded files are saved to disk.
    STORAGE_DIR: Path = Path("./storage")

    # --- Upload limits ---
    # Maximum upload size in megabytes.
    MAX_UPLOAD_MB: int = 50

    model_config = SettingsConfigDict(env_file=".env")


# Single shared instance — import this, not the class.
settings = Settings()
