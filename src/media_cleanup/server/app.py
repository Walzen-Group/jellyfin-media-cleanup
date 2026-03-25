"""
FastAPI application — entry point for the REST API server.
"""

from __future__ import annotations

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from media_cleanup.config import load_config
from media_cleanup.server import routes
from media_cleanup.server.jobs import JobManager
from media_cleanup.server.websocket import ConnectionManager

logger = logging.getLogger(__name__)

# Static files directory for the frontend SPA (optional)
_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"


def create_app() -> FastAPI:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app = FastAPI(title="Jellyfin Media Cleanup", version="0.1.0")

    # CORS — allow all origins for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Shared instances
    config = load_config()
    manager = JobManager(config=config)
    ws_manager = ConnectionManager()

    # Wire broadcast: job worker -> websocket clients
    manager.set_broadcast(ws_manager.broadcast_sync)

    # Inject manager into routes module
    routes.job_manager = manager
    app.include_router(routes.router)

    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws_manager.connect(ws)
        try:
            # Keep the connection open; client can send pings
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect(ws)

    # Serve frontend static files if the build directory exists
    if _FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")

    return app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    uvicorn.run(create_app(), host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
