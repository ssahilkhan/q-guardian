"""Integration tests for MongoDB-backed analysis history persistence.

These tests exercise the REAL production repository against a live
MongoDB server (``MONGODB_URL``). They are skipped automatically when
no server answers a ping, but they are the only proof of Phase 3's
success criterion — history surviving repository/application
reinitialization — and therefore require a running MongoDB instance.

No developer database or hardcoded credentials are used: every test
creates a uniquely named database (UUID suffix) and drops it afterwards.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import uuid
from typing import TYPE_CHECKING, Any

import pytest
from pymongo import MongoClient

from q_guardian.config.settings import get_settings
from q_guardian.database.repositories import (
    MAX_HISTORY,
    MongoAnalysisHistoryRepository,
)
from q_guardian.exceptions.base import DatabaseError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable

    from httpx import AsyncClient


MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
SERVER_SELECTION_MS = 3000


def _server_reachable() -> bool:
    """Return True when a MongoDB server answers a quick ping."""
    try:
        probe = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=SERVER_SELECTION_MS)
        probe.admin.command("ping")
        probe.close()
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not _server_reachable(), reason="requires a running MongoDB server"),
]


@pytest.fixture
def mongo_namespace() -> Callable[[], tuple[str, str]]:
    """Return a factory handing out unique (database, collection) pairs."""

    created: list[str] = []

    def _factory() -> tuple[str, str]:
        database_name = f"q_guardian_p3_{uuid.uuid4().hex[:12]}"
        created.append(database_name)
        return database_name, "analysis_history"

    yield _factory

    cleaner = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=SERVER_SELECTION_MS)
    for database_name in created:
        cleaner.drop_database(database_name)
    cleaner.close()


@pytest.fixture
async def make_repository(
    mongo_namespace: Callable[[], tuple[str, str]],
) -> AsyncGenerator[Any, None]:
    """Build repositories against throwaway databases.

    Yields an async factory ``(fresh_client) -> (repo, client)`` where
    ``fresh_client=True`` forces a brand-new Motor client, simulating a
    process restart.
    """
    clients: list[Any] = []
    namespace = mongo_namespace()
    state: dict[str, str] = {"database": namespace[0], "collection": namespace[1]}

    from motor.motor_asyncio import AsyncIOMotorClient

    def _build(fresh_client: bool = False) -> tuple[MongoAnalysisHistoryRepository, Any]:
        if fresh_client or not clients:
            client = AsyncIOMotorClient(MONGODB_URL, serverSelectionTimeoutMS=SERVER_SELECTION_MS)
            clients.append(client)
        else:
            client = clients[0]
        collection = client[state["database"]][state["collection"]]
        return (
            MongoAnalysisHistoryRepository(collection),
            client,
        )

    yield _build

    for client in clients:
        client.close()


def _record(analysis_id: str, decision: str = "ALLOW") -> dict[str, Any]:
    return {
        "analysis_id": analysis_id,
        "decision": decision,
        "risk_score": 0.0,
        "is_valid": True,
        "findings": [],
        "processing_time_ms": 1.5,
        "timestamp": "2026-01-01T00:00:00+00:00",
    }


class TestRepositoryCrud:
    """Basic CRUD against real MongoDB."""

    async def test_empty_history(self, make_repository) -> None:
        repo, _client = make_repository()
        assert await repo.list_recent() == []

    async def test_add_and_read_back_identical(self, make_repository) -> None:
        repo, _client = make_repository()
        original = _record("persist-1", decision="WARN")
        await repo.add(original)

        history = await repo.list_recent()
        assert len(history) == 1
        stored = history[0]
        assert stored["analysis_id"] == original["analysis_id"]
        assert stored["decision"] == original["decision"]
        assert stored["risk_score"] == original["risk_score"]
        assert stored["timestamp"] == original["timestamp"]

    async def test_multiple_records_newest_first(self, make_repository) -> None:
        repo, _client = make_repository()
        for index in range(10):
            await repo.add(_record(f"id-{index}"))

        history = await repo.list_recent()
        assert [r["analysis_id"] for r in history] == [f"id-{i}" for i in range(9, -1, -1)]

    async def test_get_by_id_hit(self, make_repository) -> None:
        repo, _client = make_repository()
        await repo.add(_record("lookup-me"))
        found = await repo.get_by_id("lookup-me")
        assert found is not None
        assert found["decision"] == "ALLOW"

    async def test_get_by_id_miss(self, make_repository) -> None:
        repo, _client = make_repository()
        await repo.add(_record("present"))
        assert await repo.get_by_id("absent") is None

    async def test_internal_fields_never_leak(self, make_repository) -> None:
        repo, _client = make_repository()
        await repo.add(_record("clean"))

        history = await repo.list_recent()
        assert "_id" not in history[0]
        assert "created_at" not in history[0]

        found = await repo.get_by_id("clean")
        assert found is not None
        assert "_id" not in found
        assert "created_at" not in found

    async def test_retention_cap_matches_deque_behavior(self, make_repository) -> None:
        """Only the newest MAX_HISTORY records survive, oldest evicted."""
        repo, _client = make_repository()
        total = MAX_HISTORY + 25
        for index in range(total):
            await repo.add(_record(f"id-{index}"))

        history = await repo.list_recent()
        ids = [r["analysis_id"] for r in history]
        assert len(history) == MAX_HISTORY
        assert ids[0] == f"id-{total - 1}"
        assert ids[-1] == f"id-{total - MAX_HISTORY}"
        assert "id-0" not in ids


class TestPersistenceAcrossReinitialization:
    """THE Phase 3 success criterion: history survives restarts."""

    async def test_survives_full_client_and_repository_reinit(self, make_repository) -> None:
        # 1. Write records through repository instance A (client X).
        writer, _client_a = make_repository()
        written_ids = [f"survive-{index}" for index in range(5)]
        for index, analysis_id in enumerate(written_ids):
            await writer.add(_record(analysis_id, decision="ALLOW" if index % 2 else "BLOCK"))

        # 2. Reinitialize: brand-new Motor client AND repository object
        #    (the closest in-process simulation of an application restart;
        #    the true cross-process case is covered below).
        reader, _client_b = make_repository(fresh_client=True)

        # 3. Read the same records back.
        history = await reader.list_recent()
        returned_ids = [r["analysis_id"] for r in history]
        assert returned_ids == list(reversed(written_ids))

        single = await reader.get_by_id(written_ids[0])
        assert single is not None
        assert single["decision"] == "BLOCK"

    async def test_survives_real_process_restart(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A child process scans via AnalysisService, exits; the record
        must still be readable here — a genuine application restart."""
        database_name = f"q_guardian_p3_restart_{uuid.uuid4().hex[:10]}"

        child_env = {
            **os.environ,
            "MONGODB_URL": MONGODB_URL,
            "MONGODB_DATABASE": database_name,
            "MONGODB_HISTORY_COLLECTION": "analysis_history",
            "ENVIRONMENT": "testing",
        }
        script = (
            "import asyncio\n"
            "from q_guardian.api.services.analysis import AnalysisService\n"
            "from q_guardian.database.client import get_db_client\n"
            "async def main():\n"
            "    await get_db_client().connect()  # as the app lifespan does\n"
            "    service = AnalysisService()\n"
            "    result = await service.scan(\n"
            "        'What is the weather like in Paris today?'\n"
            "    )\n"
            "    print(result['analysis_id'])\n"
            "    await get_db_client().disconnect()\n"
            "asyncio.run(main())\n"
        )

        completed = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env=child_env,
            timeout=180,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        # The child's stdout interleaves structured logs with the bare
        # analysis ID; extract the UUID line explicitly.
        id_matches = re.findall(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            completed.stdout,
        )
        assert id_matches, completed.stdout[-2000:]
        analysis_id = id_matches[-1]

        # Parent reads back through a completely independent stack.
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(MONGODB_URL, serverSelectionTimeoutMS=SERVER_SELECTION_MS)
        try:
            repo = MongoAnalysisHistoryRepository(client[database_name]["analysis_history"])
            restored = await repo.get_by_id(analysis_id)
            assert restored is not None, "history did not survive process restart"
            assert restored["decision"].upper() == "ALLOW"

            history = await repo.list_recent()
            assert [r["analysis_id"] for r in history] == [analysis_id]
        finally:
            client.close()
            MongoClient(MONGODB_URL, serverSelectionTimeoutMS=SERVER_SELECTION_MS).drop_database(
                database_name
            )


class TestFailureHandling:
    """Connection/database failures surface as structured errors."""

    @pytest.fixture
    def unreachable_repo(self) -> Any:
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(
            "mongodb://127.0.0.1:27099",
            serverSelectionTimeoutMS=250,
        )
        return MongoAnalysisHistoryRepository(client["db"]["coll"]), client

    async def test_add_failure_raises_database_error(self, unreachable_repo) -> None:
        repo, client = unreachable_repo
        with pytest.raises(DatabaseError) as exc_info:
            await repo.add(_record("never"))
        assert exc_info.value.details["operation"] == "insert"
        assert "27099" not in str(exc_info.value)
        client.close()

    async def test_list_failure_raises_database_error(self, unreachable_repo) -> None:
        repo, client = unreachable_repo
        with pytest.raises(DatabaseError) as exc_info:
            await repo.list_recent()
        assert exc_info.value.details["operation"] == "list"
        client.close()

    async def test_get_failure_raises_database_error(self, unreachable_repo) -> None:
        repo, client = unreachable_repo
        with pytest.raises(DatabaseError) as exc_info:
            await repo.get_by_id("anything")
        assert exc_info.value.details["operation"] == "get"
        client.close()


class TestApplicationIntegration:
    """End-to-end: the API persists scans into MongoDB."""

    async def test_api_scan_persists_to_mongodb(
        self,
        authorized_client: AsyncClient,
        mongo_namespace: Callable[[], tuple[str, str]],
    ) -> None:
        response = await authorized_client.post(
            "/api/v1/analysis/scan",
            json={"prompt": "What is the weather like in Paris today?"},
        )
        assert response.status_code == 200
        analysis_id = response.json()["data"]["analysis_id"]

        settings = get_settings()
        from motor.motor_asyncio import AsyncIOMotorClient

        # The API itself serves the persisted record...
        fetch = await authorized_client.get(f"/api/v1/analysis/{analysis_id}")
        assert fetch.status_code == 200
        assert fetch.json()["data"]["analysis_id"] == analysis_id

        client = AsyncIOMotorClient(
            settings.database.url, serverSelectionTimeoutMS=SERVER_SELECTION_MS
        )
        try:
            document = await client[settings.database.database][
                settings.database.history_collection
            ].find_one({"analysis_id": analysis_id})
            assert document is not None, "API scan was not persisted to MongoDB"
            assert document["decision"].upper() == "ALLOW"
            await client[settings.database.database][
                settings.database.history_collection
            ].delete_one({"_id": document["_id"]})
        finally:
            client.close()
