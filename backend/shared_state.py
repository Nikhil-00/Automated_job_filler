"""
backend/shared_state.py
────────────────────────
Module-level mutable state shared between the WebSocket endpoint
and the automation-start endpoint.
"""
from __future__ import annotations

import asyncio
import threading
import time

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SessionState:
    queue:          asyncio.Queue
    user_id:        Optional[int]   = None
    platform:       Optional[str]   = None
    history:        List[str]       = field(default_factory=list)
    last_screenshot: Optional[str]  = None
    is_active:      bool            = True
    stop_event:     threading.Event = field(default_factory=threading.Event)
    created_at:     float           = field(default_factory=time.monotonic)

    def add_to_history(self, message: str) -> None:
        self.history.append(message)
        if len(self.history) > 500:
            self.history.pop(0)


# Maps session_id → SessionState
_sessions: dict[str, SessionState] = {}
_sessions_lock = threading.Lock()

# Sessions inactive for longer than this are eligible for cleanup
_SESSION_TTL_SECONDS = 4 * 3600  # 4 hours


def cleanup_stale_sessions() -> int:
    """
    Remove sessions that have been inactive for longer than _SESSION_TTL_SECONDS.
    Called by the APScheduler background job in main.py.
    Returns the number of sessions removed.
    """
    cutoff = time.monotonic() - _SESSION_TTL_SECONDS
    to_remove = []
    with _sessions_lock:
        for sid, state in _sessions.items():
            if not state.is_active and state.created_at < cutoff:
                to_remove.append(sid)
        for sid in to_remove:
            del _sessions[sid]
    return len(to_remove)
