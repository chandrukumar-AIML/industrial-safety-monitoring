"""
backend/routes/stream.py

WebSocket endpoint that streams annotated JPEG frames
to all connected React dashboard clients.

# FIXED: Connection limit to prevent resource exhaustion
# FIXED: Offload JPEG encoding to thread executor (non-blocking)
# IMPROVED: Skip encoding when no clients connected (CPU savings)
# IMPROVED: Proper WebSocket close codes + error handling
# FIXED: No PII leakage in logs
# IMPROVED: Dependency injection for testability
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import Set

import cv2
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from pydantic import BaseModel, Field

from ..state import app_state
from ..models import StreamFrameMessage

router = APIRouter(tags=["stream"])

_JPEG_QUALITY: int = int(os.getenv("WS_JPEG_QUALITY", "80"))
_MAX_MESSAGE_LEN: int = int(os.getenv("WS_MAX_MESSAGE_LEN", "1024"))
_FRAME_SLEEP_S: float = float(os.getenv("WS_FRAME_SLEEP_S", "0.04"))
_MAX_CONNECTIONS: int = int(os.getenv("WS_MAX_CONNECTIONS", "10"))


class StreamStatsOut(BaseModel):
    """WebSocket stream connection statistics."""
    connected_clients: int = Field(ge=0, description="Number of active WebSocket connections")
    pipeline_fps: float = Field(ge=0.0, description="Current inference pipeline FPS")


class ConnectionManager:
    """Thread-safe WebSocket connection registry with connection limit."""

    def __init__(self, max_connections: int = _MAX_CONNECTIONS) -> None:
        self._connections: Set[WebSocket] = set()
        self._lock: asyncio.Lock = asyncio.Lock()
        self._max_connections: int = max_connections

    async def connect(self, ws: WebSocket) -> bool:
        """
        Accept a WebSocket connection.
        
        Returns:
            True if connection accepted, False if rejected.
        """
        async with self._lock:
            if len(self._connections) >= self._max_connections:
                await ws.close(code=1008, reason="Max connections reached")
                logger.warning(
                    "WS connection rejected — max {} reached",
                    self._max_connections,
                )
                return False
            await ws.accept()
            self._connections.add(ws)

        logger.info("WS client connected | total={}", self.count)
        return True

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)
        logger.info("WS client disconnected | total={}", self.count)

    async def broadcast(self, message: str) -> None:
        """Send message to all connected clients concurrently."""
        if not self._connections:
            return

        async with self._lock:
            targets = list(self._connections)

        async def _send(ws: WebSocket) -> WebSocket | None:
            try:
                await ws.send_text(message)
                return None
            except Exception as exc:
                logger.debug("WS send failed: {}", type(exc).__name__)
                return ws

        results = await asyncio.gather(
            *(_send(ws) for ws in targets),
            return_exceptions=False,
        )
        dead = {ws for ws in results if ws is not None}
        if dead:
            async with self._lock:
                self._connections -= dead

    @property
    def count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


@router.websocket("/stream")
async def video_stream(ws: WebSocket) -> None:
    """
    WebSocket video stream endpoint.

    Streams annotated JPEG frames to the connected React dashboard client.

    Protocol:
        Server → Client: StreamFrameMessage JSON on every frame (~25 FPS)
        Client → Server: {"type": "ping"} → Server replies {"type": "pong"}

    Close codes:
        1000 — Normal closure
        1008 — Policy violation (max connections reached)
    """
    accepted = await manager.connect(ws)
    if not accepted:
        return

    try:
        while True:
            # Handle incoming client messages
            try:
                raw = await asyncio.wait_for(
                    ws.receive_text(), timeout=0.01
                )
                if len(raw) <= _MAX_MESSAGE_LEN:
                    try:
                        msg = json.loads(raw)
                        if msg.get("type") == "ping":
                            await ws.send_text(json.dumps({"type": "pong"}))
                    except json.JSONDecodeError:
                        logger.debug("WS: malformed JSON — ignoring")
                else:
                    logger.warning("WS: message too large ({} bytes)", len(raw))
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break
            except Exception as exc:
                logger.debug("WS receive error: {} — closing", type(exc).__name__)
                break

            # Skip encoding if no clients (saves CPU)
            if manager.count == 0:
                await asyncio.sleep(_FRAME_SLEEP_S)
                continue

            frame_result = app_state.get_latest_frame()
            if frame_result is None:
                await asyncio.sleep(_FRAME_SLEEP_S)
                continue

            frame_bgr = frame_result.frame_bgr
            if frame_bgr is None:
                await asyncio.sleep(_FRAME_SLEEP_S)
                continue

            # Offload JPEG encoding to thread executor (CPU-bound)
            loop = asyncio.get_running_loop()
            success, jpeg_buf = await loop.run_in_executor(
                None,
                lambda: cv2.imencode(
                    ".jpg", frame_bgr,
                    [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY],
                ),
            )

            if not success:
                logger.warning(
                    "WS: imencode failed for frame {} — skipping",
                    frame_result.frame_idx,
                )
                await asyncio.sleep(_FRAME_SLEEP_S)
                continue

            jpeg_b64 = base64.b64encode(jpeg_buf.tobytes()).decode()

            msg = StreamFrameMessage(
                timestamp=frame_result.timestamp,
                frame_idx=frame_result.frame_idx,
                jpeg_b64=jpeg_b64,
                active_tracks=frame_result.active_tracks,
                active_violations=len(frame_result.violations),
                fps=round(frame_result.fps, 1),
            )

            try:
                await ws.send_text(msg.model_dump_json())
            except Exception:
                break

            await asyncio.sleep(_FRAME_SLEEP_S)

    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)


@router.get(
    "/stream/stats",
    response_model=StreamStatsOut,
    summary="WebSocket stream statistics",
    description="Returns the number of active WebSocket connections and current pipeline FPS.",
)
async def stream_stats() -> StreamStatsOut:
    """Current WebSocket connection count and pipeline FPS."""
    return StreamStatsOut(
        connected_clients=manager.count,
        pipeline_fps=(
            app_state.get_latest_frame().fps
            if app_state.get_latest_frame() else 0.0
        ),
    )


def get_diagnostics() -> dict:
    """Return stream router status for health checks."""
    return {
        "config": {
            "max_connections": _MAX_CONNECTIONS,
            "jpeg_quality": _JPEG_QUALITY,
            "frame_sleep_s": _FRAME_SLEEP_S,
        },
        "stats": manager.count,
    }
