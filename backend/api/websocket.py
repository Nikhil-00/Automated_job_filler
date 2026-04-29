"""
backend/api/websocket.py
─────────────────────────
WebSocket endpoint  —  /ws/{session_id}?token=<JWT>

Automation worker threads write JSON messages into a per-session
asyncio.Queue; this endpoint reads and forwards them to the browser.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.auth.utils import decode_jwt
from backend.shared_state import _sessions, _sessions_lock

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    ws: WebSocket,
    session_id: str,
    token: str | None = None,
) -> None:
    # Reject the connection if no token or token is invalid
    if not token:
        await ws.close(code=4001)
        return
    try:
        decode_jwt(token)
    except Exception:
        await ws.close(code=4001)
        return

    await ws.accept()

    # Snapshot history and grab the queue under the lock, then release immediately.
    # Never hold a threading.Lock across an await — the lock stays owned by the
    # event-loop thread while suspended, blocking every automation thread that
    # needs _sessions_lock (e.g. appending job entries, stopping sessions).
    with _sessions_lock:
        if session_id in _sessions:
            state = _sessions[session_id]
            q = state.queue
            history_snapshot = list(state.history)
        else:
            from backend.shared_state import SessionState
            q = asyncio.Queue()
            _sessions[session_id] = SessionState(queue=q, is_active=False)
            history_snapshot = []

    # Replay history outside the lock so automation threads are never blocked here.
    for old_msg in history_snapshot:
        try:
            await ws.send_text(old_msg)
        except Exception:
            return

    try:
        while True:
            try:
                message = await asyncio.wait_for(q.get(), timeout=30.0)
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
