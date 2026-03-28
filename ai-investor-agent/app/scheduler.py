"""
APScheduler background job that re-analyzes monitored symbols at their configured interval.
Runs inside the FastAPI process. Started during app lifespan.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler

from app.repository import Repository


def _run_due_scans() -> None:
    repo = Repository()
    due = repo.get_due_monitored_symbols()
    if not due:
        return

    # Import here to avoid circular dependency at module level
    from app.graph import run_recommendation

    for row in due:
        user_id: str = row["user_id"]
        symbol: str = row["symbol"]
        try:
            rec = run_recommendation(symbol, user_id)
            result_json = rec.model_dump(mode="json")
            result_json["summary"] = rec.summary
            repo.update_monitored_result(user_id, symbol, result_json)
            logging.info(f"[scheduler] Scanned {symbol} for {user_id}: {rec.action}")
        except Exception as exc:
            logging.warning(f"[scheduler] Scan failed for {symbol}/{user_id}: {exc}")


_scheduler = BackgroundScheduler(daemon=True)


@asynccontextmanager
async def lifespan(app):  # type: ignore[type-arg]
    """FastAPI lifespan context manager — starts/stops the scheduler."""
    _scheduler.add_job(_run_due_scans, "interval", minutes=1, id="due_scans", replace_existing=True)
    _scheduler.start()
    logging.info("[scheduler] Background scanner started (interval: 1min check).")
    yield
    _scheduler.shutdown(wait=False)
    logging.info("[scheduler] Background scanner stopped.")
