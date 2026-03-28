from __future__ import annotations

# Compatibility wrapper so `uvicorn main:app` works when started
# from the `ai-investor-agent` directory. The real FastAPI app lives
# at `ai-investor-agent/app/main.py` and exposes `app`.

from app.main import app  # re-export the FastAPI application
