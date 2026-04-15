"""
server.py  —  legacy entry-point shim
──────────────────────────────────────
The real application now lives in backend/main.py.
This file exists so that existing launch commands still work:

    uvicorn server:app --reload --port 8000

"""
from backend.main import app  # noqa: F401

# Re-export for uvicorn's module loader
__all__ = ["app"]
