"""Identifier helpers local to the strategies package."""

from __future__ import annotations

from datetime import datetime


def generate_run_id() -> str:
    """Generate a unique run ID based on timestamp."""
    now = datetime.now()
    return f"run-{now.strftime('%Y%m%d-%H%M%S-%f')}"
