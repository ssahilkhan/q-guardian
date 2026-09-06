"""API v1 router configuration for Q-Guardian.

Aggregates all v1 endpoint routers.

Public (no auth):

- ``/api/v1/health`` — liveness/readiness probe for orchestrators

Everything else under ``/api/v1`` requires an authenticated principal
(JWT access token or API key), enforced by the router-level dependency
on :class:`~q_guardian.security.http_auth.get_current_principal`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from q_guardian.api.v1.endpoints import analysis, console, health, system
from q_guardian.security.http_auth import get_current_principal

# Public endpoints (no auth required). Health stays public so load
# balancers and orchestrators can probe readiness without credentials;
# informational system endpoints remain protected.
public_router = APIRouter()
public_router.include_router(
    health.router,
    tags=["Health"],
    prefix="/health",
)

# Protected endpoints (auth required)
# Router-level dependencies propagate to every included sub-router,
# so all v1 endpoints are authenticated by this single declaration.
api_v1_router = APIRouter(
    dependencies=[
        Depends(get_current_principal),
    ],
)

api_v1_router.include_router(
    analysis.router,
    tags=["Analysis"],
    prefix="/analysis",
)
api_v1_router.include_router(
    console.router,
    tags=["Console"],
    prefix="/console",
)
api_v1_router.include_router(
    system.router,
    tags=["System"],
    prefix="/system",
)

# =============================================================================
# Future module routers will be registered here:
#
# from q_guardian.api.v1.endpoints import prompt_injection, jailbreak, threats
# api_v1_router.include_router(
#     prompt_injection.router, tags=["Prompt Injection"], prefix="/prompt-injection"
# )
# api_v1_router.include_router(jailbreak.router, tags=["Jailbreak Detection"], prefix="/jailbreak")
# api_v1_router.include_router(threats.router, tags=["Threat Detection"], prefix="/threats")
# =============================================================================
