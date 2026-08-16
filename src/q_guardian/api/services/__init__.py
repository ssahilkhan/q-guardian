"""API service layer for Q-Guardian.

Services provide thin, stateless-or-singleton facades over the framework's
existing pipeline components so API endpoints can reuse detection logic
without reimplementing it.
"""

from q_guardian.api.services.analysis import AnalysisService

__all__ = ["AnalysisService"]
