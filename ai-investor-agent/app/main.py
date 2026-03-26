from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import get_settings
from app.graph import run_recommendation
from app.repository import Repository


app = FastAPI(title="AI Investor Agent", version="0.1.0")


class RecommendationRequest(BaseModel):
    symbol: str
    user_id: str


class OutcomeRequest(BaseModel):
    user_id: str
    symbol: str
    pattern_name: str
    action: str
    market_condition: str
    signal_stack: list[str]
    entry_price: float
    target_price: float
    stop_loss: float
    outcome_return_pct: float
    outcome_horizon_days: int
    outcome_label: str


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "env": settings.app_env}


@app.get("/api/users")
def get_users() -> dict[str, object]:
    repo = Repository()
    return {
        "default_user_id": get_settings().default_user_id,
        "user_portfolio": repo.get_user_portfolio(get_settings().default_user_id),
    }


@app.post("/analyze")
def analyze(payload: RecommendationRequest) -> dict[str, object]:
    recommendation = run_recommendation(payload.symbol, payload.user_id)
    body = recommendation.model_dump()
    body["summary"] = recommendation.summary
    return body


@app.get("/memory/{symbol}")
def memory(symbol: str, pattern_name: str, market_condition: str = "neutral") -> dict[str, object]:
    repo = Repository()
    memory_snapshot = repo.get_setup_memory(symbol, pattern_name, market_condition, [])
    return memory_snapshot.model_dump()


@app.post("/outcomes")
def record_outcome(payload: OutcomeRequest) -> dict[str, object]:
    repo = Repository()
    stored = repo.record_outcome(payload.model_dump())
    memory_snapshot = repo.get_setup_memory(
        symbol=payload.symbol,
        pattern_name=payload.pattern_name,
        market_condition=payload.market_condition,
        signal_stack=payload.signal_stack,
    )
    return {
        "stored_outcome": stored,
        "updated_memory": memory_snapshot.model_dump(),
    }
