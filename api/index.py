"""Vercel entry point for Q-Guardian FastAPI application.

This file exists to satisfy Vercel's auto-detection of FastAPI entrypoints.
The actual application is in src/q_guardian/main.py.
"""

import sys
import os

# Add src to path for direct import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from q_guardian.main import app

# Re-export for Vercel auto-detection
__all__ = ["app"]