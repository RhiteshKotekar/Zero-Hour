"""HTTP + WebSocket API for the control center (``python -m samg.api`` -> http://localhost:8000)."""

from samg.api.app import app, create_app

__all__ = ["app", "create_app"]
