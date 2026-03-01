"""
Upstox real-time market data pipeline.

Architecture
------------
The Upstox SDK runs its WebSocket in a **background thread** managed by the SDK
internally.  FastAPI / uvicorn runs on an **asyncio event loop**.

Bridge:
  SDK thread  -->  loop.call_soon_threadsafe(queue.put_nowait, tick)
                       |
                       v
               asyncio.Queue   <--  drained by broadcast_task (coroutine)
                       |
                       v
               ConnectionManager.broadcast()  -->  all WS clients

The OHLC candle is built here by accumulating raw LTP ticks into rolling
1-minute buckets.  A complete candle is pushed to the queue when the minute
rolls over.
"""

from __future__ import annotations

import asyncio
import logging
import time
import threading
import webbrowser
from dataclasses import dataclass
from typing import Any

import upstox_client
from fastapi import WebSocket

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

INSTRUMENT_KEYS: list[str] = ["NSE_INDEX|Nifty 50"]
SUBSCRIPTION_MODE: str = "full"
RECONNECT_BASE_DELAY: float = 2.0   # seconds
RECONNECT_MAX_DELAY: float = 60.0   # seconds
CANDLE_INTERVAL_SECONDS: int = 60   # 1-minute candles


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class OHLCCandle:
    time: int        # Unix epoch seconds (candle open time)
    open: float
    high: float
    low: float
    close: float
    volume: int

    def to_dict(self) -> dict:
        return {
            "time": self.time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass
class _CandleAccumulator:
    """Accumulates LTP ticks into a rolling 1-minute OHLC candle."""
    candle_open_ts: int = 0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    active: bool = False

    def _bucket(self, ts: int) -> int:
        """Floor ts to the nearest minute bucket."""
        return ts - (ts % CANDLE_INTERVAL_SECONDS)

    def update(self, ltp: float, volume: int, ts: int) -> OHLCCandle | None:
        """
        Feed a new tick.  Returns a completed OHLCCandle when the minute rolls
        over, otherwise returns None.
        """
        bucket = self._bucket(ts)
        completed: OHLCCandle | None = None

        if not self.active:
            # First tick ever
            self._open_new(ltp, volume, bucket)
        elif bucket > self.candle_open_ts:
            # Minute rolled over — emit the completed candle, open a new one
            completed = OHLCCandle(
                time=self.candle_open_ts,
                open=self.open,
                high=self.high,
                low=self.low,
                close=self.close,
                volume=self.volume,
            )
            self._open_new(ltp, volume, bucket)
        else:
            # Same minute — update running candle
            self.high = max(self.high, ltp)
            self.low = min(self.low, ltp)
            self.close = ltp
            self.volume += volume

        return completed

    def _open_new(self, ltp: float, volume: int, bucket: int) -> None:
        self.candle_open_ts = bucket
        self.open = self.high = self.low = self.close = ltp
        self.volume = volume
        self.active = True


# ---------------------------------------------------------------------------
# Connection manager — keeps track of all live WebSocket clients
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        logger.info("WS client connected. Total: %d", len(self._clients))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        logger.info("WS client disconnected. Total: %d", len(self._clients))

    async def broadcast(self, message: str) -> None:
        if not self._clients:
            return
        dead: list[WebSocket] = []
        async with self._lock:
            clients = list(self._clients)
        for ws in clients:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)


# ---------------------------------------------------------------------------
# Upstox streamer
# ---------------------------------------------------------------------------

class UpstoxStreamer:
    """
    Manages the Upstox MarketDataStreamerV3 lifecycle in a background thread
    and bridges ticks to an asyncio.Queue.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[OHLCCandle] = asyncio.Queue(maxsize=1000)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._streamer: Any = None
        self._accumulator = _CandleAccumulator()
        self._stop_event = threading.Event()
        self._reconnect_delay = RECONNECT_BASE_DELAY
        self._browser_opened = False  # prevent opening multiple tabs

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def queue(self) -> asyncio.Queue[OHLCCandle]:
        return self._queue

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called once from the FastAPI lifespan. Spawns the reconnect thread."""
        self._loop = loop
        t = threading.Thread(target=self._reconnect_loop, daemon=True, name="upstox-streamer")
        t.start()
        logger.info("Upstox streamer thread started.")

    def stop(self) -> None:
        self._stop_event.set()
        if self._streamer:
            try:
                self._streamer.disconnect()
            except Exception:
                pass

    def restart(self) -> None:
        """Stop the current connection and reconnect with the latest token."""
        logger.info("Restarting Upstox streamer with fresh token…")
        self._browser_opened = False
        if self._streamer:
            try:
                self._streamer.disconnect()
            except Exception:
                pass
        # Reset back-off so reconnect is immediate
        self._reconnect_delay = RECONNECT_BASE_DELAY

    # ------------------------------------------------------------------
    # Background thread — reconnect loop
    # ------------------------------------------------------------------

    def _reconnect_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                logger.info("Connecting to Upstox market feed…")
                self._connect()
                # _connect() blocks until the streamer disconnects
                if not self._stop_event.is_set():
                    logger.warning(
                        "Upstox feed disconnected. Reconnecting in %.0fs…",
                        self._reconnect_delay,
                    )
            except Exception as exc:
                logger.error("Upstox streamer error: %s", exc)

            if not self._stop_event.is_set():
                self._stop_event.wait(timeout=self._reconnect_delay)
                # Exponential back-off
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, RECONNECT_MAX_DELAY
                )

    def _open_login(self) -> None:
        """Open the Upstox OAuth login page in the default browser (once)."""
        if self._browser_opened:
            return
        self._browser_opened = True
        login_url = "http://localhost:8000/auth/upstox/login"
        logger.info("Opening Upstox login in browser: %s", login_url)
        webbrowser.open(login_url)

    def _connect(self) -> None:
        access_token = settings.UPSTOX_ACCESS_TOKEN
        if not access_token:
            logger.warning("UPSTOX_ACCESS_TOKEN is not set. Opening browser for OAuth…")
            self._open_login()
            # Wait for the callback to set the token
            self._stop_event.wait(timeout=60)
            return

        configuration = upstox_client.Configuration()
        configuration.access_token = access_token
        api_client = upstox_client.ApiClient(configuration)

        done_event = threading.Event()

        streamer = upstox_client.MarketDataStreamerV3(
            api_client, INSTRUMENT_KEYS, SUBSCRIPTION_MODE
        )
        self._streamer = streamer

        def on_open(*_args: Any) -> None:
            logger.info("Upstox WebSocket open. Subscribed to %s", INSTRUMENT_KEYS)
            self._reconnect_delay = RECONNECT_BASE_DELAY  # reset back-off

        def on_message(msg: Any) -> None:
            self._handle_message(msg)

        def on_close(*_args: Any) -> None:
            logger.info("Upstox WebSocket closed.")
            done_event.set()

        def on_error(err: Any) -> None:
            err_str = str(err)
            if "401" in err_str or "Unauthorized" in err_str:
                logger.warning("Upstox token expired. Opening browser for re-auth…")
                self._open_login()
            else:
                logger.error("Upstox WebSocket error: %s", err)
            done_event.set()

        streamer.on("open", on_open)
        streamer.on("message", on_message)
        streamer.on("close", on_close)
        streamer.on("error", on_error)

        streamer.connect()
        # Block this thread until the connection closes or an error fires
        done_event.wait()

    # ------------------------------------------------------------------
    # Message processing  (runs in SDK background thread)
    # ------------------------------------------------------------------

    def _handle_message(self, msg: Any) -> None:
        """
        Decode the protobuf message from the SDK.

        The SDK returns a decoded dict-like object. We navigate to the
        feeds -> instrument -> ff -> marketFF -> marketOHLC -> ohlc list
        to find the 1-minute (I1) candle, then push completed candles to
        the asyncio queue via call_soon_threadsafe.
        """
        try:
            feeds = getattr(msg, "feeds", None)
            if not feeds:
                return

            for instrument_key, feed_data in feeds.items():
                ff = getattr(feed_data, "ff", None)
                if not ff:
                    continue

                market_ff = getattr(ff, "marketFF", None)
                if not market_ff:
                    continue

                # ---- LTP from ltpc ----
                ltpc = getattr(market_ff, "ltpc", None)
                ltp = float(getattr(ltpc, "ltp", 0)) if ltpc else 0.0
                if ltp == 0.0:
                    continue

                # ---- Volume from OHLC I1 candle (most accurate source) ----
                market_ohlc = getattr(market_ff, "marketOHLC", None)
                volume = 0
                if market_ohlc:
                    for candle in getattr(market_ohlc, "ohlc", []):
                        if getattr(candle, "interval", "") == "I1":
                            volume = int(getattr(candle, "vol", 0))
                            break

                ts = int(time.time())
                completed = self._accumulator.update(ltp, volume, ts)
                if completed is not None:
                    self._enqueue(completed)

        except Exception as exc:
            logger.debug("Error processing Upstox message: %s", exc)

    def _enqueue(self, candle: OHLCCandle) -> None:
        if self._loop is None:
            return
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, candle)
        except asyncio.QueueFull:
            logger.warning("Tick queue full — dropping oldest candle.")
            try:
                self._queue.get_nowait()
                self._loop.call_soon_threadsafe(self._queue.put_nowait, candle)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Module-level singletons (imported by main.py)
# ---------------------------------------------------------------------------

streamer = UpstoxStreamer()
connection_manager = ConnectionManager()
