"""Unit tests for the analysis history repository.

Covers the in-memory test double and shared repository semantics that
do not require a MongoDB server: bounded retention, newest-first
ordering, ID lookup, and protocol conformance. Real-MongoDB persistence
is covered by tests/integration/test_history_persistence.py.
"""

from __future__ import annotations

import pytest

from q_guardian.database.repositories import (
    MAX_HISTORY,
    AnalysisHistoryRepository,
    InMemoryAnalysisHistoryRepository,
)


def _record(analysis_id: str, decision: str = "ALLOW") -> dict[str, object]:
    return {
        "analysis_id": analysis_id,
        "decision": decision,
        "risk_score": 0.0,
        "findings": [],
        "processing_time_ms": 1.0,
        "timestamp": "2026-01-01T00:00:00+00:00",
    }


@pytest.mark.asyncio
class TestInMemoryRepositoryBasics:
    """Behavior of the in-memory double (mirrors the original deque)."""

    async def test_empty_history(self) -> None:
        repo = InMemoryAnalysisHistoryRepository()
        assert await repo.list_recent() == []

    async def test_add_and_read_back(self) -> None:
        repo = InMemoryAnalysisHistoryRepository()
        record = _record("id-1")
        await repo.add(record)
        history = await repo.list_recent()
        assert len(history) == 1
        assert history[0]["analysis_id"] == "id-1"

    async def test_multiple_records_newest_first(self) -> None:
        repo = InMemoryAnalysisHistoryRepository()
        for index in range(5):
            await repo.add(_record(f"id-{index}"))
        history = await repo.list_recent()
        assert [r["analysis_id"] for r in history] == [f"id-{index}" for index in range(4, -1, -1)]

    async def test_get_by_id_hit(self) -> None:
        repo = InMemoryAnalysisHistoryRepository()
        await repo.add(_record("target"))
        await repo.add(_record("other"))
        found = await repo.get_by_id("target")
        assert found is not None
        assert found["analysis_id"] == "target"

    async def test_get_by_id_miss_returns_none(self) -> None:
        repo = InMemoryAnalysisHistoryRepository()
        await repo.add(_record("id-1"))
        assert await repo.get_by_id("missing") is None


@pytest.mark.asyncio
class TestInMemoryRetention:
    """Bounded retention matches the historical deque(maxlen=200)."""

    async def test_default_limit_is_max_history(self) -> None:
        repo = InMemoryAnalysisHistoryRepository()
        for index in range(MAX_HISTORY + 25):
            await repo.add(_record(f"id-{index}"))

        history = await repo.list_recent()
        assert len(history) == MAX_HISTORY
        # Newest kept, oldest evicted.
        assert history[0]["analysis_id"] == f"id-{MAX_HISTORY + 24}"
        assert history[-1]["analysis_id"] == f"id-{MAX_HISTORY + 25 - MAX_HISTORY}"
        assert "id-0" not in [r["analysis_id"] for r in history]

    async def test_custom_limit(self) -> None:
        repo = InMemoryAnalysisHistoryRepository(history_limit=3)
        for index in range(10):
            await repo.add(_record(f"id-{index}"))
        history = await repo.list_recent()
        assert [r["analysis_id"] for r in history] == ["id-9", "id-8", "id-7"]

    async def test_records_are_copies(self) -> None:
        """Mutating a returned record must not corrupt stored state."""
        repo = InMemoryAnalysisHistoryRepository()
        await repo.add(_record("id-1"))
        history = await repo.list_recent()
        history[0]["decision"] = "TAMPERED"
        again = await repo.list_recent()
        assert again[0]["decision"] == "ALLOW"


def test_repository_protocol_conformance() -> None:
    """The in-memory double satisfies the repository Protocol."""
    assert isinstance(InMemoryAnalysisHistoryRepository(), AnalysisHistoryRepository)
