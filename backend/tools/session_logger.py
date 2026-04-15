"""
backend/tools/session_logger.py
────────────────────────────────
Thread-safe logger that streams structured JSON events to the
browser via the session's asyncio.Queue (written by worker threads,
consumed by the WebSocket endpoint).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from backend.shared_state import _sessions, _sessions_lock


class SessionLogger:
    def __init__(self, session_id: str, loop: asyncio.AbstractEventLoop) -> None:
        self._sid     = session_id
        self._loop    = loop
        self._counter = 0

    # ── internal ──────────────────────────────────────────────────────────────

    def _enqueue(self, payload: dict) -> None:
        with _sessions_lock:
            q = _sessions.get(self._sid)
        if q is None:
            return
        asyncio.run_coroutine_threadsafe(q.put(json.dumps(payload)), self._loop)

    def _log(self, message: str, log_type: str) -> None:
        self._counter += 1
        self._enqueue({
            "type": "log",
            "payload": {
                "id":        self._counter,
                "message":   message,
                "logType":   log_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })
        print(f"[{log_type.upper():7s}] {message}")

    # ── public helpers ────────────────────────────────────────────────────────

    def info   (self, msg: str) -> None: self._log(msg, "info")
    def found  (self, msg: str) -> None: self._log(msg, "found")
    def success(self, msg: str) -> None: self._log(msg, "success")
    def error  (self, msg: str) -> None: self._log(msg, "error")
    def warning(self, msg: str) -> None: self._log(msg, "warning")

    def progress(self, current: int, total: int) -> None:
        self._enqueue({"type": "progress", "payload": {"current": current, "total": total}})

    def screenshot(self, b64_jpeg: str) -> None:
        self._enqueue({"type": "screenshot", "payload": {"data": b64_jpeg}})

    def company(self, data: dict) -> None:
        self._enqueue({"type": "company", "payload": data})

    def cost(self, data: dict) -> None:
        self._enqueue({"type": "cost", "payload": data})

    def done(self, message: str = "Automation complete!") -> None:
        self._enqueue({"type": "completed", "payload": {"message": message}})

    def fail(self, message: str) -> None:
        self._enqueue({"type": "error", "payload": {"message": message}})
