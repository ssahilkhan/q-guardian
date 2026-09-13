"""ASGI entry point for Vercel deployment.

This file creates the FastAPI app for Vercel's entry point detection by
delegating to the single application factory, so the deployment surface
always matches the locally served application.
"""

import os
import sys

# Add src to path for direct import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from q_guardian.api.app import create_app

app = create_app()
