"""API module for Q-Guardian.

Provides versioned API routing and endpoint management.
"""

from q_guardian.api.v1.router import api_v1_router

__all__ = ["api_v1_router"]
