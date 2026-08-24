"""Vercel entry point for Q-Guardian FastAPI application.

This file exists to satisfy Vercel's auto-detection of FastAPI entrypoints.
The actual application is in src/q_guardian/main.py.
"""

from q_guardian.main import app

# Re-export for Vercel auto-detection
__all__ = ["app"]