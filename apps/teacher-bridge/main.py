"""Deployment entry point for uvicorn."""

from apps.teacher_bridge.api import app

__all__ = ["app"]
