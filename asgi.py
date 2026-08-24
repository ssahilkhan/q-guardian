"""ASGI entry point for Vercel deployment.

This file creates the FastAPI app directly for Vercel's entry point detection.
"""

import sys
import os

# Add src to path for direct import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Import and create the app
from q_guardian.api.app import create_app

app = create_app()