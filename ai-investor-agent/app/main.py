from __future__ import annotations

from fastapi import FastAPI, Query
from pydantic import BaseModel

from app.config import get_settings
from app.data_sources import MarketDataService
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
    exit_reason: str | None = None
    is_stop_loss_hit: bool = False


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


@app.get("/signals")
def get_signals() -> list[dict[str, object]]:
    return [
        {
            "id": "sig_tatasteel_pattern_start_20260326_1",
            "symbol": "TATASTEEL",
            "category": "technical",
            "signal_type": "pattern_start",
            "title": "Breakout setup forming",
            "description": "Price is near prior 20-day high with rising volume.",
            "confidence_pct": 72,
            "detected_at": "2026-03-26T10:15:00+05:30",
            "source": "yfinance / demo",
            "is_demo": True
        },
        {
            "id": "sig_infy_volume_breakout_20260326_1",
            "symbol": "INFY",
            "category": "technical",
            "signal_type": "volume_breakout",
            "title": "Delivery volume spike",
            "description": "Delivery volume spiked 400% above 20-day average. Institutional accumulation pattern detected ahead of macro cycle shift.",
            "confidence_pct": 85,
            "detected_at": "2026-03-26T10:05:00+05:30",
            "source": "nsepython / demo",
            "is_demo": True
        },
        {
            "id": "sig_reliance_oi_buildup_20260326_1",
            "symbol": "RELIANCE",
            "category": "derivatives",
            "signal_type": "oi_buildup",
            "title": "Aggressive put writing",
            "description": "Aggressive put writing at current strike indicating strong structural floor. Correlates with historical multi-month bottoms.",
            "confidence_pct": 68,
            "detected_at": "2026-03-26T09:45:00+05:30",
            "source": "nsepython / demo",
            "is_demo": True
        }
    ]


@app.get("/symbols/{symbol}/technicals")
def get_technicals(symbol: str) -> dict[str, object]:
    market = MarketDataService()
    history = market.get_price_history(symbol).data
    indicators = market.compute_pattern_indicators(history)
    return {
        "symbol": symbol.upper(),
        "indicators": indicators,
        "source": "yfinance" if not history.empty else "demo"
    }


@app.get("/memory/{symbol}")
def memory(
    symbol: str, 
    pattern_name: str, 
    market_condition: str = "neutral",
    signal_stack: list[str] = Query(default=[])
) -> dict[str, object]:
    repo = Repository()
    memory_snapshot = repo.get_setup_memory(symbol, pattern_name, market_condition, signal_stack)
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
