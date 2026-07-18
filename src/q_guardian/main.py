"""Q-Guardian entry point.

This module provides the ASGI application entry point for uvicorn/gunicorn.
"""

from q_guardian.api.app import create_app

app = create_app()
