"""
WebSocket connection pool manager.

Maintains the set of active browser connections and provides
a thread-safe broadcast primitive. FastAPI WebSocket handlers
are async so this is safe without locks for single-worker uvicorn.
"""

from __future__ import annotations

import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._active: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._active.append(websocket)
        logger.info(
            "WebSocket connected. Active connections: %d", len(self._active)
        )

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._active:
            self._active.remove(websocket)
        logger.info(
            "WebSocket disconnected. Active connections: %d", len(self._active)
        )

    async def broadcast(self, message: str) -> None:
        """Send a text message to all connected clients. Disconnects dead clients."""
        dead: list[WebSocket] = []
        for connection in list(self._active):
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)

        for conn in dead:
            self.disconnect(conn)

    @property
    def connection_count(self) -> int:
        return len(self._active)
