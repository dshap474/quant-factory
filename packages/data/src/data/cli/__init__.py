"""CLI package facade for the data runtime package."""

import data.api as api

from .main import app, main

__all__ = ["api", "app", "main"]
