"""
WebSocket connection manager for broadcasting job progress.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts messages."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active_connections.append(ws)
        # Capture the event loop so sync code can schedule broadcasts
        if self._loop is None:
            self._loop = asyncio.get_event_loop()

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active_connections:
            self.active_connections.remove(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to all connected clients."""
        data = json.dumps(message)
        disconnected: list[WebSocket] = []
        for ws in self.active_connections:
            try:
                await ws.send_text(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

    def broadcast_sync(self, message: dict[str, Any]) -> None:
        """
        Thread-safe broadcast — called from the job worker thread.

        Schedules the async broadcast on the event loop.
        """
        if self._loop is None or not self.active_connections:
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(message), self._loop)

    async def send_to(self, ws: WebSocket, message: dict[str, Any]) -> None:
        """Send a JSON message to a single WebSocket client."""
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            self.disconnect(ws)

    def send_to_sync(self, ws: WebSocket, message: dict[str, Any]) -> None:
        """Thread-safe single-client send - schedules send_to on the event loop."""
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self.send_to(ws, message), self._loop)
