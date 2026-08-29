"""WebSocket endpoint for live scan-progress events.

Browsers subscribe per scan id at ``/api/v1/ws/scans/{scan_id}`` and
receive the real lifecycle events published by ``AnalysisService.scan``
(``scan.started``, ``scan.completed`` / ``scan.failed``). Because scans
are synchronous the client usually connects after submission; it requests
the retained completed snapshot with a ``__replay__`` control message.

Authentication: the console surface is unauthenticated app-wide (a
pre-existing, documented property — see docs/21_Web_Console_UI.md §9),
so the socket does not require a token and must be exposed only behind
the existing reverse-proxy / network controls.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from q_guardian.api.services.live import get_live_hub

logger = structlog.get_logger("api.live")

router = APIRouter()

hub = get_live_hub()


@router.websocket("/ws/scans/{scan_id}")
async def scan_events(websocket: WebSocket, scan_id: str) -> None:
    """Stream real scan events for a scan id over a WebSocket.

    Live events (``scan.started`` / ``scan.completed`` / ``scan.failed``)
    are fanned out as they are published. Because scans are synchronous,
    the client typically connects *after* submission; it can request the
    retained completed snapshot with a ``__replay__`` control message.
    ``__ping__`` answers with a ``pong`` to keep the socket alive.
    """
    await websocket.accept()
    await hub.subscribe(scan_id, websocket)
    logger.debug("live_subscribed", scan_id=scan_id)
    try:
        while True:
            message: Any = await websocket.receive_text()
            if message == "__ping__":
                await websocket.send_json({"type": "pong", "scan_id": scan_id})
            elif message == "__replay__":
                snapshot = hub.get_snapshot(scan_id)
                if snapshot is not None:
                    await websocket.send_json(snapshot)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("live_connection_closed", scan_id=scan_id, exc_info=True)
    finally:
        await hub.unsubscribe(scan_id, websocket)
        logger.debug("live_unsubscribed", scan_id=scan_id)
