"""
backend/api/websocket.py
─────────────────────────
WebSocket endpoint  —  /ws/{session_id}

Automation worker threads write JSON messages into a per-session
asyncio.Queue; this endpoint reads and forwards them to the browser.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.shared_state import _sessions, _sessions_lock

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(ws: WebSocket, session_id: str) -> None:
    await ws.accept()

    q: asyncio.Queue = asyncio.Queue()
    with _sessions_lock:
        _sessions[session_id] = q

    try:
        while True:
            try:
                message = await asyncio.wait_for(q.get(), timeout=1.0)
                await ws.send_text(message)

                parsed = json.loads(message)
                if parsed.get("type") in ("completed", "error"):
                    break

            except asyncio.TimeoutError:
                try:
                    await ws.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    finally:
        with _sessions_lock:
            _sessions.pop(session_id, None)
