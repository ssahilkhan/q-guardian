"""ASGI entry point for Vercel deployment.

This file creates the FastAPI app directly for Vercel's entry point detection.
"""

import sys
import os

# Add src to path for direct import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Create the FastAPI app directly
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from q_guardian.api.v1.router import api_router
from q_guardian.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Q-Guardian: A Hybrid Quantum-Classical Framework for Runtime Security of Autonomous AI Agents",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api/v1")

# Health check endpoint
@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy", "version": settings.APP_VERSION}

# Root endpoint
@app.get("/", tags=["root"])
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "description": "Q-Guardian: A Hybrid Quantum-Classical Framework for Runtime Security of Autonomous AI Agents",
    }