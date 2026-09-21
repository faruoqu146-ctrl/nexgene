"""Vercel / local entrypoint — re-exports the FastAPI app."""
from backend.app.main import app

__all__ = ["app"]
