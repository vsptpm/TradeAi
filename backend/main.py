from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from auth.dependencies import verify_ws_token
from auth.routes import router as auth_router
from auth.upstox_oauth import router as upstox_router
from market_feed import connection_manager, streamer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan: start/stop the Upstox streamer alongside uvicorn
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_app: FastAPI):
    loop = asyncio.get_event_loop()

    # Start the Upstox background thread
    streamer.start(loop)

    # Start the async broadcast task that drains the queue → all WS clients
    broadcast_task = asyncio.create_task(_broadcast_loop())

    yield  # server is running

    # Shutdown
    streamer.stop()
    broadcast_task.cancel()
    try:
        await broadcast_task
    except asyncio.CancelledError:
        pass


async def _broadcast_loop() -> None:
    """Drain completed OHLC candles from the queue and fan-out to WS clients."""
    while True:
        candle = await streamer.queue.get()
        if connection_manager.client_count == 0:
            streamer.queue.task_done()
            continue
        payload = json.dumps(candle.to_dict())
        await connection_manager.broadcast(payload)
        streamer.queue.task_done()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="AI Trading Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "https://trade-ai-kohl.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(upstox_router)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "ws_clients": connection_manager.client_count,
    }


# ---------------------------------------------------------------------------
# WebSocket endpoint  — token passed as ?token=<jwt>
# ---------------------------------------------------------------------------

@app.websocket("/ws/live-feed")
async def live_feed(
    websocket: WebSocket,
    user: dict = Depends(verify_ws_token),
):
    await connection_manager.connect(websocket)
    logger.info("Live feed client: %s", user.get("username"))
    try:
        # Keep the connection open; incoming messages are ignored (read-only feed)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await connection_manager.disconnect(websocket)
