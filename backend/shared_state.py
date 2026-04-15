"""
backend/shared_state.py
────────────────────────
Module-level mutable state shared between the WebSocket endpoint
and the automation-start endpoint.
"""
from __future__ import annotations

import asyncio
import threading

# Maps session_id → asyncio.Queue[str]
# WebSocket reads from the queue; automation thread writes to it.
_sessions: dict[str, asyncio.Queue] = {}
_sessions_lock = threading.Lock()
