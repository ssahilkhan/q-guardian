"""Persistent repositories for Q-Guardian.

Repositories encapsulate all MongoDB access behind small, testable
interfaces. Production code depends on the protocol; tests may supply
fakes.
"""

from q_guardian.database.repositories.analysis_history import (
    MAX_HISTORY,
    AnalysisHistoryRepository,
    InMemoryAnalysisHistoryRepository,
    MongoAnalysisHistoryRepository,
)

__all__ = [
    "MAX_HISTORY",
    "AnalysisHistoryRepository",
    "InMemoryAnalysisHistoryRepository",
    "MongoAnalysisHistoryRepository",
]
