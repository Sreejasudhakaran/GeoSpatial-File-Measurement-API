"""
App-level configuration re-export.
Exposes Settings and settings instance.
"""

from app.core.config import Settings, settings

__all__ = ["Settings", "settings"]
