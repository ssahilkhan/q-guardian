"""Live scan event hub for the console WebSocket.

Bridges the synchronous scan pipeline to the browser in real time.
``AnalysisService.scan`` publishes genuine lifecycle events (started,
completed / failed) derived from the *actual* backend execution and
result; this hub fans those events out to every WebSocket subscriber
that is listening on the matching scan id.

Events are never fabricated here: the hub only forwards what the scan
service publishes, and the lifecycle is grounded in the real result
payload (decision, risk, findings, validation status, timing).

The console endpoints are unauthenticated app-wide (a pre-existing,
documented property of the project), so subscriptions do not carry a
token. See: docs/21_Web_Console_UI.md §9 and
docs/22_Backend_to_UI_Integration_Audit.md §7.
"""

from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from typing import Any

import structlog

logger = structlog.get_logger("api.live")


def _to_json_safe(value: Any) -> Any:
    """Convert a payload to a JSON-serializable structure.

    Analysis payloads come from :class:`PromptAnalysis.model_dump`, which
    may retain non-JSON values (``datetime``, ``StrEnum``, …). Round-trip
    through JSON with ``default=str`` so they serialize safely to clients.
    """
    return json.loads(json.dumps(value, default=str))


class LiveScanHub:
    """Fan-out hub that forwards scan events to WebSocket subscribers.

    Subscribers are grouped by scan id. A subscriber on an unknown scan
    id receives nothing new; completion events are retained so the client
    can fetch the final result later by sending an explicit ``__replay__``
    control message (the endpoint reads this snapshot).
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[Any]] = {}
        self._completed: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    @property
    def completed(self) -> dict[str, dict[str, Any]]:
        """Return the published completion snapshots by scan id."""
        return dict(self._completed)

    async def subscribe(self, scan_id: str, websocket: Any) -> None:
        """Register a WebSocket for a scan id (no payload is sent here)."""
        async with self._lock:
            self._subscribers.setdefault(scan_id, set()).add(websocket)

    def get_snapshot(self, scan_id: str) -> dict[str, Any] | None:
        """Return the retained ``scan.completed`` snapshot, JSON-safe."""
        snapshot = self._completed.get(scan_id)
        return _to_json_safe(snapshot) if snapshot is not None else None

    async def unsubscribe(self, scan_id: str, websocket: Any) -> None:
        """Remove a WebSocket from a scan id."""
        async with self._lock:
            subscribers = self._subscribers.get(scan_id)
            if subscribers is None:
                return
            subscribers.discard(websocket)
            if not subscribers:
                self._subscribers.pop(scan_id, None)

    async def publish(self, scan_id: str, event: dict[str, Any]) -> None:
        """Forward an event to every current subscriber for a scan id.

        Completion events are retained (bounded) so late subscribers can
        replay the final result.
        """
        if event.get("type") == "scan.completed":
            async with self._lock:
                self._completed[scan_id] = _to_json_safe(event)
                if len(self._completed) > 500:
                    oldest = next(iter(self._completed))
                    self._completed.pop(oldest)

        async with self._lock:
            subscribers = list(self._subscribers.get(scan_id, set()))
        for websocket in subscribers:
            await self._send(scan_id, websocket, _to_json_safe(event))

    @staticmethod
    async def _send(scan_id: str, websocket: Any, event: dict[str, Any]) -> None:
        try:
            await websocket.send_json(event)
        except Exception:
            logger.debug(
                "live_subscriber_send_failed",
                scan_id=scan_id,
                exc_info=True,
            )


@lru_cache(maxsize=1)
def get_live_hub() -> LiveScanHub:
    """Return the shared LiveScanHub singleton.

    Cached so the analysis service and the WebSocket endpoint observe the
    same fan-out state.
    """
    return LiveScanHub()
